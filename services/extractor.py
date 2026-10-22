"""Text extraction for uploaded files, reporting progress through a callback.

progress(percent_within_stage: int, message: str)
"""

import base64
import csv
import html
import io
import logging
import os
import re
import shutil
import struct
import subprocess
import tempfile
from typing import Callable, Optional

from config import Config
from services import ollama_client

log = logging.getLogger(__name__)

Progress = Callable[[int, str], None]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

try:
    from docx import Document as DocxDocument
except Exception:  # pragma: no cover
    DocxDocument = None

_paddle = None


class ExtractionError(RuntimeError):
    pass


class ExtractionResult:
    def __init__(self, text: str, pages: Optional[int] = None, ocr_used: bool = False, ocr_engine: str = ""):
        self.text = text
        self.pages = pages
        self.ocr_used = ocr_used
        self.ocr_engine = ocr_engine


# ---------------------------------------------------------------- plain text
def decode_text(data: bytes) -> str:
    if data.startswith((b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        return data.decode("utf-32")
    if data.startswith((b"\xfe\xff", b"\xff\xfe")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _csv_to_text(data: bytes) -> str:
    decoded = decode_text(data)
    try:
        dialect = csv.Sniffer().sniff(decoded[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = csv.reader(io.StringIO(decoded, newline=""), dialect)
    return "\n".join(" | ".join(cell.strip() for cell in row) for row in rows if any(c.strip() for c in row))


# ---------------------------------------------------------------- OCR engines
_rapid = None


def _ocr_rapid(image_bytes: bytes) -> str:
    """RapidOCR: PaddleOCR models on ONNX Runtime — pip-installable, CPU, Windows/Linux."""
    global _rapid
    from rapidocr_onnxruntime import RapidOCR

    if _rapid is None:
        _rapid = RapidOCR()
    result, _ = _rapid(image_bytes)
    if not result:
        return ""
    # result rows: [box(4 points), text, score]; rebuild reading order line by line.
    items = []
    for box, text, score in result:
        if float(score) < 0.3 or not str(text).strip():
            continue
        ys = [p[1] for p in box]
        items.append((min(ys), max(ys), min(p[0] for p in box), str(text).strip()))
    items.sort(key=lambda i: (i[0], i[2]))
    lines, current, line_bottom = [], [], None
    for top, bottom, left, text in items:
        if current and top > line_bottom - (bottom - top) * 0.5:
            lines.append(" ".join(t for _, t in sorted(current)))
            current = []
        current.append((left, text))
        line_bottom = bottom if len(current) == 1 else max(line_bottom, bottom)
    if current:
        lines.append(" ".join(t for _, t in sorted(current)))
    return "\n".join(lines)


def _ocr_paddle(image_bytes: bytes) -> str:
    global _paddle
    import numpy as np
    import cv2
    from paddleocr import PaddleOCR

    if _paddle is None:
        _paddle = PaddleOCR(lang="en", use_doc_orientation_classify=True, use_doc_unwarping=False,
                            use_textline_orientation=False, device="cpu", enable_mkldnn=False)
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ExtractionError("Image could not be decoded")
    result = _paddle.predict(image)
    lines = []
    for item in result or []:
        data = item if isinstance(item, dict) else getattr(item, "json", {}) or {}
        data = data.get("res", data)
        lines.extend(str(t) for t in data.get("rec_texts", []) if t)
    return "\n".join(lines)


def _ocr_tesseract(image_bytes: bytes) -> str:
    import pytesseract
    from PIL import Image

    if Config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD
    image = Image.open(io.BytesIO(image_bytes))
    return pytesseract.image_to_string(image)


def _ocr_ollama(image_bytes: bytes) -> str:
    if not Config.OLLAMA_VISION_MODEL:
        raise ExtractionError("OLLAMA_VISION_MODEL is not set")
    return ollama_client.vision_ocr(base64.b64encode(image_bytes).decode(), Config.OLLAMA_VISION_MODEL)


_ENGINES = {"rapid": _ocr_rapid, "paddle": _ocr_paddle, "tesseract": _ocr_tesseract, "ollama": _ocr_ollama}


def ocr_image(image_bytes: bytes) -> tuple[str, str]:
    """Run OCR with the configured engine (or first working one in auto mode)."""
    choice = Config.OCR_ENGINE
    if choice == "off":
        raise ExtractionError("OCR is disabled (OCR_ENGINE=off), so images/scanned pages cannot be read.")
    order = [choice] if choice in _ENGINES else ["rapid", "paddle", "tesseract", "ollama"]
    errors = []
    for name in order:
        try:
            text = _ENGINES[name](image_bytes)
            return text.strip(), name
        except Exception as exc:  # engine missing or failed; try the next one
            log.info("OCR engine %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
    raise ExtractionError(
        "No OCR engine is available. Run `pip install rapidocr-onnxruntime` (recommended), install Tesseract, "
        "or set OLLAMA_VISION_MODEL. Details: " + " | ".join(errors)
    )


# ---------------------------------------------------------------- formats
def _pdf(data: bytes, progress: Progress) -> ExtractionResult:
    if fitz is None:
        raise ExtractionError("PyMuPDF is not installed")
    chunks, ocr_used, engine = [], False, ""
    with fitz.open(stream=data, filetype="pdf") as doc:
        total = len(doc)
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                progress(int(i / total * 100), f"Reading page {i} of {total}")
                chunks.append(text)
            else:
                progress(int(i / total * 100), f"Scanning page {i} of {total} with OCR")
                png = page.get_pixmap(dpi=200, alpha=False).tobytes("png")
                ocr_text, engine = ocr_image(png)
                ocr_used = True
                chunks.append(ocr_text)
    return ExtractionResult("\n\n".join(chunks), pages=total, ocr_used=ocr_used, ocr_engine=engine)


def _docx(data: bytes, progress: Progress) -> ExtractionResult:
    if DocxDocument is None:
        raise ExtractionError("python-docx is not installed")
    doc = DocxDocument(io.BytesIO(data))
    parts = []
    paragraphs = doc.paragraphs
    for i, para in enumerate(paragraphs, start=1):
        text = para.text.strip()
        if text:
            style = (para.style.name or "").lower() if para.style is not None else ""
            parts.append(f"## {text}" if style.startswith("heading") else text)
        if i % 50 == 0:
            progress(int(i / max(1, len(paragraphs)) * 80), f"Reading paragraph {i} of {len(paragraphs)}")
    for t_index, table in enumerate(doc.tables, start=1):
        progress(85, f"Reading table {t_index} of {len(doc.tables)}")
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    progress(100, "Document read")
    return ExtractionResult("\n".join(parts))


def _clean_word_text(text: str) -> str:
    text = re.sub(r"\x13[^\x13\x14\x15]*\x14", "", text)       # field instructions (e.g. HYPERLINK "...")
    text = re.sub(r"\x13[^\x13\x14\x15]*\x15", "", text)       # fields without a result
    text = text.replace("\x07\x07", "\n").replace("\x07", " | ").replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    text = re.sub(r"[\x00-\x08\x0e-\x1f\x14\x15]", "", text)
    text = re.sub(r"( \| )+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _doc_piece_table(data: bytes) -> str:
    """Read text from a Word 97-2003 .doc via its piece table (pure Python)."""
    import olefile

    ole = olefile.OleFileIO(io.BytesIO(data))
    try:
        word = ole.openstream("WordDocument").read()
        flags = struct.unpack_from("<H", word, 0x000A)[0]
        if flags & 0x0100:
            raise ExtractionError("This .doc file is password protected.")
        table_name = "1Table" if flags & 0x0200 else "0Table"
        table = ole.openstream(table_name).read()
        fc_clx, lcb_clx = struct.unpack_from("<II", word, 0x01A2)
        clx = table[fc_clx:fc_clx + lcb_clx]
        pos = 0
        while pos < len(clx) and clx[pos] == 0x01:  # skip Prc (property modifiers)
            pos += 3 + struct.unpack_from("<H", clx, pos + 1)[0]
        if pos >= len(clx) or clx[pos] != 0x02:
            raise ExtractionError("Unrecognised .doc structure")
        lcb = struct.unpack_from("<I", clx, pos + 1)[0]
        plc = clx[pos + 5:pos + 5 + lcb]
        n = (lcb - 4) // 12
        cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
        parts = []
        for i in range(n):
            fc = struct.unpack_from("<I", plc, (n + 1) * 4 + i * 8 + 2)[0]
            count = cps[i + 1] - cps[i]
            if fc & 0x40000000:
                start = (fc & ~0x40000000) // 2
                parts.append(word[start:start + count].decode("cp1252", errors="replace"))
            else:
                parts.append(word[fc:fc + count * 2].decode("utf-16-le", errors="replace"))
        return _clean_word_text("".join(parts))
    finally:
        ole.close()


def _doc_external(data: bytes) -> str:
    """Fallback converters for .doc: antiword, then LibreOffice."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "input.doc")
        with open(src, "wb") as fh:
            fh.write(data)
        antiword = shutil.which("antiword")
        if antiword:
            out = subprocess.run([antiword, "-w", "0", src], capture_output=True, timeout=120)
            if out.returncode == 0 and out.stdout.strip():
                return decode_text(out.stdout)
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            subprocess.run([soffice, "--headless", "--convert-to", "txt:Text", "--outdir", tmp, src],
                           capture_output=True, timeout=180)
            txt = os.path.join(tmp, "input.txt")
            if os.path.exists(txt):
                with open(txt, "rb") as fh:
                    return decode_text(fh.read())
    raise ExtractionError("Could not read this .doc file. Install antiword or LibreOffice, or save it as .docx.")


def _doc(data: bytes, progress: Progress) -> ExtractionResult:
    progress(30, "Reading Word 97-2003 document")
    try:
        text = _doc_piece_table(data)
    except Exception as exc:
        log.info("Piece-table .doc parse failed (%s); trying external converters", exc)
        text = ""
    if not text.strip():
        progress(60, "Converting legacy .doc")
        text = _doc_external(data)
    progress(100, "Document read")
    return ExtractionResult(text)


def _svg(data: bytes, progress: Progress) -> ExtractionResult:
    progress(30, "Reading SVG text")
    text = ""
    if fitz is not None:
        try:
            with fitz.open(stream=data, filetype="svg") as doc:
                page = doc[0]
                text = page.get_text("text").strip()
                if not text:
                    progress(60, "SVG has no text layer — rendering for OCR")
                    zoom = max(1.0, 1600 / max(page.rect.width, page.rect.height, 1))
                    png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
                    text, engine = ocr_image(png)
                    progress(100, f"OCR complete ({engine})")
                    return ExtractionResult(text, pages=1, ocr_used=True, ocr_engine=engine)
        except ExtractionError:
            raise
        except Exception as exc:
            log.info("PyMuPDF could not render SVG: %s", exc)
    if not text:  # plain regex fallback: visible <text>/<title>/<desc> content
        markup = decode_text(data)
        chunks = re.findall(r"<(?:text|tspan|title|desc)\b[^>]*>([^<]+)<", markup, re.I)
        text = "\n".join(html.unescape(c).strip() for c in chunks if c.strip())
    progress(100, "SVG read")
    return ExtractionResult(text, pages=1)


def extract(data: bytes, ext: str, progress: Progress) -> ExtractionResult:
    ext = ext.lower()
    if ext == ".doc":
        return _doc(data, progress)
    if ext == ".svg":
        return _svg(data, progress)
    if ext in {".txt", ".md"}:
        progress(100, "Reading text file")
        return ExtractionResult(decode_text(data))
    if ext == ".csv":
        progress(100, "Parsing CSV rows")
        return ExtractionResult(_csv_to_text(data))
    if ext == ".pdf":
        return _pdf(data, progress)
    if ext == ".docx":
        return _docx(data, progress)
    if ext in IMAGE_EXTS:
        progress(30, "Running OCR on image")
        text, engine = ocr_image(data)
        progress(100, f"OCR complete ({engine})")
        return ExtractionResult(text, pages=1, ocr_used=True, ocr_engine=engine)
    raise ExtractionError(f"Unsupported file type: {ext}")

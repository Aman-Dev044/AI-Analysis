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
import threading
import unicodedata
from collections import Counter
from typing import Callable, Optional

from config import Config
from services import image_enhance, ollama_client

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
# Every engine takes a BGR image and returns text pieces as (top, bottom, left, right, text, score), so
# the reading order is rebuilt the same way for all of them and readings of one region can be compared.
_paddle = None
_paddle_lock = threading.Lock()  # PaddleOCR predictors are not safe to share across threads
MIN_PIECE_SCORE = 0.5
SOLO_PIECE_SCORE = 0.8  # a region only one version of the image produced must be read this confidently
ENGINE_LABELS = {"paddle": "PP-OCRv5", "rapid": "RapidOCR", "tesseract": "Tesseract", "ollama": "Ollama vision"}


def _box_piece(box, text, score) -> Optional[tuple]:
    text = unicodedata.normalize("NFKC", str(text)).strip()  # full-width "：２１" -> ":21"
    if not text:
        return None
    xs = [float(p[0]) for p in box]
    ys = [float(p[1]) for p in box]
    return min(ys), max(ys), min(xs), max(xs), text, float(score)


def _line_pieces(lines: list[str], score: float = 1.0) -> list[tuple]:
    """Pieces for text that comes without geometry: one per line, in order."""
    return [(float(i), i + 0.9, 0.0, 1.0, line.strip(), score) for i, line in enumerate(lines) if line.strip()]


_rapid_engines: dict = {}
_rapid_lock = threading.Lock()


def _rapid_engine(lang: str = "ch"):
    """RapidOCR 3 (PP-OCRv5 on ONNX Runtime) for `lang`, or the older rapidocr-onnxruntime package."""
    with _rapid_lock:
        if lang not in _rapid_engines:
            try:
                from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
            except ImportError:
                if lang != "ch":
                    raise
                from rapidocr_onnxruntime import RapidOCR

                _rapid_engines[lang] = RapidOCR()
                return _rapid_engines[lang]
            size = ModelType.SERVER if Config.OCR_RAPID_MODEL == "server" else ModelType.MOBILE
            _rapid_engines[lang] = RapidOCR(params={
                "Global.log_level": "error",
                "Det.ocr_version": OCRVersion.PPOCRV5, "Det.model_type": size,
                "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.lang_type": LangRec(lang),
                # Only the Chinese/English recogniser comes in a server size; the other languages are mobile.
                "Rec.model_type": size if lang == "ch" else ModelType.MOBILE,
            })
        return _rapid_engines[lang]


def _rapid_result(result) -> list[tuple]:
    """(box, text, score) rows from either RapidOCR package's result object."""
    if isinstance(result, tuple):  # rapidocr-onnxruntime: ([[box, text, score], ...], elapsed)
        return [tuple(r) for r in result[0] or []]
    txts = getattr(result, "txts", None) or ()
    boxes = getattr(result, "boxes", None)
    if boxes is None:  # recognition only (no detection): no geometry
        boxes = [None] * len(txts)
    return list(zip(boxes, txts, getattr(result, "scores", None) or ()))


def _rapid_run(engine, image, det: bool = True, cls: bool = True, rec: bool = True):
    # RapidOCR 3 remembers use_det / use_cls / use_rec from the previous call, so always pass all three.
    return engine(image, use_det=det, use_cls=cls, use_rec=rec)


def _ocr_rapid(image) -> list[tuple]:
    """RapidOCR: PaddleOCR's PP-OCRv5 models on ONNX Runtime — pip-installable, fast on CPU, Windows/Linux."""
    rows = _rapid_result(_rapid_run(_rapid_engine(), image))
    pieces = [p for p in (_box_piece(box, text, score) for box, text, score in rows if box is not None) if p]
    if Config.OCR_HINDI:
        pieces = _reread_devanagari(image, pieces)
    return pieces


# The Chinese/English model reads Devanagari as CJK look-alikes ("3319市33"): such a region is Hindi text.
_CJK = re.compile("[⺀-鿿가-힯]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _looks_misread(text: str) -> bool:
    return bool(_CJK.search(text)) or not re.search(r"[A-Za-z0-9]{2}", text)


def _merge_hindi(latin: str, latin_score: float, hindi: str, hindi_score: float) -> Optional[tuple[str, float]]:
    """Combine the two readings of one region. Indian forms print "हिंदी / English" labels: the Devanagari
    model reads the Hindi half, the Latin model the English half (it is better at English and digits)."""
    if not _DEVANAGARI.search(hindi):
        return None
    if "/" in latin and "/" in hindi:
        hindi_part = hindi.split("/", 1)[0].strip()
        latin_part = latin.split("/", 1)[1].strip()
        if _DEVANAGARI.search(hindi_part) and latin_part:
            return f"{hindi_part} / {latin_part}", min(latin_score, hindi_score)
    if not re.search(r"[A-Za-z]", hindi) and (hindi_score > latin_score or _looks_misread(latin)):
        return hindi, hindi_score
    return None


def _reread_devanagari(image, pieces: list[tuple]) -> list[tuple]:
    """Read again, with the Devanagari model, the regions that may hold Hindi: unsure readings, readings
    that make no sense in Latin script, and bilingual "हिंदी / English" labels."""
    suspects = [i for i, p in enumerate(pieces) if p[5] < 0.9 or "/" in p[4] or _looks_misread(p[4])]
    if not suspects:
        return pieces
    try:
        engine = _rapid_engine("devanagari")
    except Exception as exc:  # model not downloadable / old package: keep what we have
        log.info("Devanagari OCR unavailable: %s", exc)
        return pieces
    h, w = image.shape[:2]
    out = list(pieces)
    for i in suspects:
        top, bottom, left, right, text, score = pieces[i]
        pad = (bottom - top) * 0.15
        crop = image[max(0, int(top - pad)):min(h, int(bottom + pad) + 1),
                     max(0, int(left - pad)):min(w, int(right + pad) + 1)]
        if crop.size == 0:
            continue
        rows = _rapid_result(_rapid_run(engine, crop, det=False, cls=False))
        hindi = " ".join(str(r[1]) for r in rows).strip()
        merged = _merge_hindi(text, score, hindi, min((float(r[2]) for r in rows), default=0.0))
        if merged and merged[1] >= MIN_PIECE_SCORE:
            out[i] = (top, bottom, left, right, *merged)
        elif _CJK.search(text):
            out[i] = (top, bottom, left, right, text, 0.0)  # unreadable either way: drop it
    return out


def upright(image):
    """Turn a photo taken sideways (text running vertically) upright. Upside-down text lines are handled
    by the recogniser's own line-orientation classifier."""
    try:
        engine = _rapid_engine()
    except Exception:
        return image
    import cv2

    scale = min(1.0, 960 / max(image.shape[:2]))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else image
    boxes = getattr(_rapid_run(engine, small, cls=False, rec=False), "boxes", None)
    if boxes is None or len(boxes) < 3:
        return image
    tall = sum(1 for b in boxes if (max(p[1] for p in b) - min(p[1] for p in b))
               > 1.5 * (max(p[0] for p in b) - min(p[0] for p in b)))
    if tall < len(boxes) * 0.6:
        return image
    best, best_score = image, -1.0
    for turn in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE):
        turned = cv2.rotate(small, turn)
        rows = _rapid_result(_rapid_run(engine, turned))
        score = sum(len(str(t)) * float(s) for _, t, s in rows)  # confident characters read
        if score > best_score:
            best, best_score = cv2.rotate(image, turn), score
    log.info("OCR: image was sideways, rotated upright")
    return best


def _paddle_engine():
    global _paddle
    if _paddle is None:
        from paddleocr import PaddleOCR

        _paddle = PaddleOCR(
            text_detection_model_name=Config.OCR_PADDLE_DET_MODEL,
            text_recognition_model_name=Config.OCR_PADDLE_REC_MODEL,
            use_doc_orientation_classify=True,  # photos taken sideways / upside down
            use_doc_unwarping=False,            # unwarping redraws the page; keep the real pixels
            use_textline_orientation=True,
            device="cpu", enable_mkldnn=False,
        )
    return _paddle


def _ocr_paddle(image) -> list[tuple]:
    """PaddleOCR 3 with PP-OCRv5 detection + recognition (most accurate open-source OCR on CPU)."""
    with _paddle_lock:
        result = _paddle_engine().predict(image)
    pieces = []
    for item in result or []:
        data = item if isinstance(item, dict) else getattr(item, "json", {}) or {}
        data = data.get("res", data)
        texts, scores = list(data.get("rec_texts") or []), list(data.get("rec_scores") or [])
        boxes = data.get("rec_polys")
        boxes = list(boxes) if boxes is not None else []
        if len(boxes) < len(texts):  # no geometry: keep the engine's own order
            pieces.extend(_line_pieces([str(t) for t in texts], min(scores, default=1.0)))
            continue
        pieces.extend(p for p in (_box_piece(boxes[i], t, scores[i] if i < len(scores) else 1.0)
                                  for i, t in enumerate(texts)) if p)
    return pieces


def _ocr_tesseract(image) -> list[tuple]:
    import pytesseract
    from PIL import Image

    if Config.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_CMD
    data = pytesseract.image_to_data(Image.fromarray(image[:, :, ::-1]), output_type=pytesseract.Output.DICT)
    lines: dict = {}
    for i, word in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not str(word).strip() or conf < 0:
            continue
        top, left, w, h = data["top"][i], data["left"][i], data["width"][i], data["height"][i]
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        line = lines.setdefault(key, {"box": [top, top + h, left, left + w], "words": [], "conf": []})
        box = line["box"]
        line["box"] = [min(box[0], top), max(box[1], top + h), min(box[2], left), max(box[3], left + w)]
        line["words"].append(str(word))
        line["conf"].append(conf / 100)
    return [(*l["box"], " ".join(l["words"]), sum(l["conf"]) / len(l["conf"])) for l in lines.values()]


def _ocr_ollama(image) -> list[tuple]:
    if not Config.OLLAMA_VISION_MODEL:
        raise ExtractionError("OLLAMA_VISION_MODEL is not set")
    if Config.AI_BACKEND == "rules":
        raise ExtractionError("AI_BACKEND=rules, so no model is used")
    text = ollama_client.vision_ocr(base64.b64encode(image_enhance.to_png(image)).decode(),
                                    Config.OLLAMA_VISION_MODEL)
    return _line_pieces(text.splitlines())


_ENGINES = {"paddle": _ocr_paddle, "rapid": _ocr_rapid, "tesseract": _ocr_tesseract, "ollama": _ocr_ollama}
# RapidOCR runs the same PP-OCRv5 models as PaddleOCR on ONNX Runtime: seconds per photo on a laptop CPU,
# where PaddlePaddle on Windows can take minutes or hang. PaddleOCR is used only when chosen explicitly.
_AUTO_ORDER = ["rapid", "tesseract", "ollama"]


def pieces_to_text(pieces: list[tuple], min_score: float = MIN_PIECE_SCORE) -> str:
    """Rebuild reading order: pieces whose vertical centres lie within half a line height of each other form
    one line, read left to right. Centres, not extents: a tall piece (a signature, text printed up the
    margin) would otherwise overlap, and join, several rows."""
    items = sorted((p for p in pieces if p[5] >= min_score), key=lambda p: ((p[0] + p[1]) / 2, p[2]))
    lines, current, centre, height = [], [], 0.0, 0.0

    def join(row: list) -> str:
        # A wide gap is a column boundary (form / table cells): keep it as three spaces so a label's value
        # stops at its own cell instead of running into the next column.
        out, last_right = "", None
        for left, right, text in sorted(row):
            if last_right is not None:
                out += "   " if left - last_right > 1.2 * height else " "
            out += text
            last_right = right
        return out

    for top, bottom, left, right, text, _ in items:
        mid, h = (top + bottom) / 2, max(bottom - top, 1e-6)
        if current and mid - centre > 0.5 * min(h, height):
            lines.append(join(current))
            current = []
        current.append((left, right, text))
        if len(current) == 1:
            centre, height = mid, h
        else:  # running mean, so a slightly slanted line stays one line
            centre += (mid - centre) / len(current)
            height = min(height, h)
    if current:
        lines.append(join(current))
    return "\n".join(lines)


def mean_confidence(pieces: list[tuple], min_score: float = MIN_PIECE_SCORE) -> float:
    """Confidence averaged over the characters read (long pieces count more than stray marks)."""
    kept = [(len(p[4]), p[5]) for p in pieces if p[5] >= min_score]
    chars = sum(n for n, _ in kept)
    return sum(n * s for n, s in kept) / chars if chars else 0.0


def _overlap(a: tuple, b: tuple) -> float:
    """Intersection over the smaller box: 1.0 when one reading's box lies inside the other's."""
    w = min(a[3], b[3]) - max(a[2], b[2])
    h = min(a[1], b[1]) - max(a[0], b[0])
    if w <= 0 or h <= 0:
        return 0.0
    smaller = min((a[3] - a[2]) * (a[1] - a[0]), (b[3] - b[2]) * (b[1] - b[0]))
    return w * h / max(smaller, 1e-6)


def _vote_key(pieces: list[tuple]) -> str:
    """Readings that differ only in spacing or punctuation count as the same vote."""
    return re.sub(r"[\W_]+", "", pieces_to_text(pieces, min_score=0)).lower()


def fuse_passes(passes: list[list[tuple]], min_score: float = MIN_PIECE_SCORE) -> list[tuple]:
    """Region by region, keep the reading most versions of the image agree on.

    Overlapping boxes from different passes form one region (a line one pass reads as one box and
    another as two still matches). Agreement beats confidence: a model can be confidently wrong on one
    version, but rarely the same way on several. Confidence breaks ties, then the earlier pass wins.
    """
    items = sorted(((i, p) for i, pieces in enumerate(passes) for p in pieces if p[5] >= min_score),
                   key=lambda item: item[1][0])
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, (pass_a, piece_a) in enumerate(items):
        for b in range(a + 1, len(items)):
            pass_b, piece_b = items[b]
            if piece_b[0] >= piece_a[1]:  # sorted by top: nothing further down can overlap
                break
            if pass_a != pass_b and _overlap(piece_a, piece_b) > 0.5:
                parent[find(a)] = find(b)

    regions: dict = {}
    for k, (i, piece) in enumerate(items):
        regions.setdefault(find(k), {}).setdefault(i, []).append(piece)
    fused = []
    for by_pass in regions.values():
        if len(passes) > 1 and len(by_pass) == 1 \
                and max(p[5] for p in next(iter(by_pass.values()))) < SOLO_PIECE_SCORE:
            continue  # only one version saw something here, and not confidently: likely noise
        votes = Counter(_vote_key(pieces) for pieces in by_pass.values())
        _, best = max(by_pass.items(), key=lambda kv: (votes[_vote_key(kv[1])],
                                                       round(mean_confidence(kv[1]), 3), -kv[0]))
        fused.extend(best)
    return fused


def _read_versions(engine, image_bytes: bytes) -> tuple[str, int, float]:
    """OCR the image and its OpenCV versions, fuse the readings; returns (text, passes run, confidence)."""
    image = upright(image_enhance.decode(image_bytes))
    if not Config.OCR_ENHANCE:
        pieces = engine(image)
        return respace(pieces_to_text(pieces)), 1, mean_confidence(pieces)
    versions, info = image_enhance.variants(image, max_variants=Config.OCR_MAX_PASSES)
    passes = []
    for label, image, scale in versions:
        pieces = engine(image)
        if scale != 1.0:  # map boxes back onto the original image so regions line up
            pieces = [(t / scale, b / scale, l / scale, r / scale, text, s) for t, b, l, r, text, s in pieces]
        passes.append(pieces)
        log.info("OCR pass %s: %d pieces, confidence %.3f (%s)", label, len(pieces), mean_confidence(pieces), info)
        # A sharp, large image read this confidently will not get meaningfully better.
        if len(passes) == 1 and mean_confidence(pieces) >= Config.OCR_GOOD_CONFIDENCE \
                and not (info["blurry"] or info["low_res"]):
            break
    fused = fuse_passes(passes)
    return respace(pieces_to_text(fused)), len(passes), mean_confidence(fused)


_GLUED = re.compile(r"[A-Za-z]{14,}")


def respace(text: str) -> str:
    """Put back the spaces OCR drops in long printed lines ("PermanentAccountNumber"). A run is split only
    when nearly all of it is common English words, so names and codes stay as read."""
    try:
        import wordninja
    except ImportError:
        return text
    costs = wordninja.DEFAULT_LANGUAGE_MODEL._wordcost

    def split(m):
        run = m.group(0)
        parts = wordninja.split(run)
        common = sum(len(p) for p in parts if len(p) >= 2 and costs.get(p.lower(), 99) <= 12.5)
        return " ".join(parts) if len(parts) > 1 and common >= 0.75 * len(run) else run

    return _GLUED.sub(split, text)


def ocr_image(image_bytes: bytes) -> tuple[str, str]:
    """Run OCR with the configured engine (or the first working one in auto mode)."""
    choice = Config.OCR_ENGINE
    if choice == "off":
        raise ExtractionError("OCR is disabled (OCR_ENGINE=off), so images/scanned pages cannot be read.")
    order = [choice] if choice in _ENGINES else _AUTO_ORDER
    errors = []
    for name in order:
        try:
            text, passes, confidence = _read_versions(_ENGINES[name], image_bytes)
        except Exception as exc:  # engine missing or failed; try the next one
            log.info("OCR engine %s unavailable: %s", name, exc)
            errors.append(f"{name}: {exc}")
            continue
        engine = ENGINE_LABELS.get(name, name)
        if name != "ollama":
            engine += f" · {passes} pass{'es' if passes > 1 else ''} · {round(confidence * 100)}%"
        return text.strip(), engine
    raise ExtractionError(
        "No OCR engine is available. Run `pip install -r requirements-ocr.txt` (PaddleOCR PP-OCRv5, recommended) "
        "or `pip install rapidocr-onnxruntime`, or install Tesseract. Details: " + " | ".join(errors)
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
                png = page.get_pixmap(dpi=300, alpha=False).tobytes("png")
                ocr_text, engine = ocr_image(png)
                ocr_used = True
                chunks.append(ocr_text)
    return ExtractionResult(_strip_page_furniture(chunks), pages=total, ocr_used=ocr_used, ocr_engine=engine)


_PAGE_NUMBER = re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?$|^-\s*\d{1,4}\s*-$", re.I)


def _strip_page_furniture(pages: list[str]) -> str:
    """Drop page numbers and the running header / footer repeated on every page, so neither is read as the
    document's title or content."""
    def norm(line: str) -> str:
        return re.sub(r"\d+", "#", " ".join(line.split()).lower())

    split = [p.splitlines() for p in pages]
    repeated = set()
    if len(split) >= 2:
        edges = Counter()
        for lines in split:
            body = [ln for ln in lines if ln.strip()]
            # Short label-free lines only: two pages both ending in "Total: 500" / "Total: 700" are content.
            edges.update({norm(ln) for ln in body[:3] + body[-3:] if len(ln.split()) <= 8 and ":" not in ln})
        repeated = {line for line, count in edges.items() if count >= max(2, len(split) * 0.6)}
    cleaned = []
    for lines in split:
        body = [ln for ln in lines if not (ln.strip() and (_PAGE_NUMBER.match(ln.strip()) or norm(ln) in repeated))]
        cleaned.append("\n".join(body).strip("\n"))
    return "\n\n".join(c for c in cleaned if c.strip())


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

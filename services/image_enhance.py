"""Classic OpenCV versions of a photo or scan for OCR (no generative or learned model touches the pixels).

Measured on blurry / zoomed-out photos, no single clean-up helps a modern OCR model every time: the
untouched image often reads best, while contrast equalisation or mild sharpening rescues the lines
it misses. So OCR reads a few versions and keeps, region by region, the most confident reading
(services.extractor). Every version keeps the original geometry, or a known scale factor, so the
regions line up. Heavy steps (binarising, strong sharpening, deskewing) measurably hurt and are not used.
"""

import io

import cv2
import numpy as np

ENLARGE_TO = 1600        # long side for the enlarged version of a small / zoomed-out image
MAX_LONG_SIDE = 4000     # larger images are reduced (OCR gains nothing, time grows)
BLURRY_BELOW = 120.0     # Laplacian variance at a normalised size; lower = blurrier


def decode(image_bytes: bytes) -> np.ndarray:
    """Bytes -> BGR array. OpenCV honours EXIF orientation; Pillow covers formats OpenCV cannot read."""
    image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(image_bytes)) as pil:
            pil = ImageOps.exif_transpose(pil).convert("RGB")
            image = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return image


def to_png(image: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("Image could not be encoded")
    return buf.tobytes()


def _gray(image: np.ndarray) -> np.ndarray:
    return image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def sharpness(image: np.ndarray) -> float:
    """Variance of the Laplacian, measured at a fixed size so it is comparable across resolutions."""
    gray = _gray(image)
    scale = 1000 / max(gray.shape[:2])
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def assess(image: np.ndarray) -> dict:
    h, w = image.shape[:2]
    sharp = sharpness(image)
    return {
        "width": w,
        "height": h,
        "sharpness": round(sharp, 1),
        "blurry": sharp < BLURRY_BELOW,
        "low_res": max(h, w) < ENLARGE_TO * 0.75,
        "low_contrast": float(_gray(image).std()) < 40,
    }


def contrast(image: np.ndarray) -> np.ndarray:
    """CLAHE on lightness only: evens out shadows and faded print, keeps colours."""
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def sharpen(image: np.ndarray) -> np.ndarray:
    """Mild unsharp mask; stronger settings create halos that OCR misreads."""
    return cv2.addWeighted(image, 1.5, cv2.GaussianBlur(image, (0, 0), 1.0), -0.5, 0)


def variants(image, max_variants: int = 4) -> tuple[list[tuple[str, np.ndarray, float]], dict]:
    """(label, image, scale) versions to OCR, most reliable first; divide box coordinates by scale to map
    them back onto the original. `image` is encoded bytes or a decoded BGR array. Also returns the quality
    assessment of the original."""
    image = decode(image) if isinstance(image, (bytes, bytearray)) else image
    info = assess(image)
    scale = 1.0
    if max(image.shape[:2]) > MAX_LONG_SIDE:
        scale = MAX_LONG_SIDE / max(image.shape[:2])
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    out = [("original", image, scale), ("contrast", contrast(image), scale), ("sharpened", sharpen(image), scale)]
    if info["low_res"]:
        f = ENLARGE_TO / max(image.shape[:2])
        out.append(("enlarged", cv2.resize(image, None, fx=f, fy=f, interpolation=cv2.INTER_LANCZOS4), scale * f))
    return out[:max(1, max_variants)], info

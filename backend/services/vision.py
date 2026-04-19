"""services/vision.py — Prétraitement image avec OpenCV
Point d'entrée unique pour tout prétraitement image/PDF dans Finalyse.
"""
import io
import logging
from typing import Optional

log = logging.getLogger("vision")


# ── Prétraitement bytes ───────────────────────────────────────────────────────

def preprocess(image_bytes: bytes) -> Optional[bytes]:
    """Prétraite des bytes image (PNG/JPG) pour améliorer l'OCR."""
    try:
        import cv2
        import numpy as np
        from PIL import Image

        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Redimensionner si trop petite (Tesseract aime ≥1200px)
        h, w = gray.shape
        if min(h, w) < 800:
            scale = 1200 / min(h, w)
            gray = cv2.resize(gray, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)

        # Débruitage
        denoised = cv2.fastNlMeansDenoising(gray, h=15)

        # CLAHE (amélioration contraste adaptatif)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        equalized = clahe.apply(denoised)

        # Binarisation Otsu
        _, binary = cv2.threshold(
            equalized, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        ok, buf = cv2.imencode(".png", binary)
        return buf.tobytes() if ok else image_bytes

    except ImportError:
        return image_bytes  # cv2 absent → retourner l'original
    except Exception as e:
        log.warning("[Vision] prétraitement : %s", e)
        return image_bytes


def opencv_boost(image_bytes: bytes) -> bytes:
    """Prétraitement alternatif (filtre bilatéral + seuillage adaptatif)."""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        th = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 2
        )
        _, buf = cv2.imencode(".png", th)
        return buf.tobytes()
    except Exception as e:
        log.warning("[Vision] opencv_boost : %s", e)
        return image_bytes


# ── Prétraitement fichier ─────────────────────────────────────────────────────

def preprocess_file(file_path: str) -> Optional[bytes]:
    """Prétraite un fichier image ou PDF (première page)."""
    import os
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return preprocess_pdf_to_bytes(file_path)
    with open(file_path, "rb") as f:
        raw = f.read()
    return preprocess(raw)


def preprocess_pdf_to_bytes(path: str) -> Optional[bytes]:
    """Convertit la première page d'un PDF en image prétraitée."""
    # Tenter pdf2image (Poppler)
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(path, dpi=200, first_page=1, last_page=1)
        if pages:
            buf = io.BytesIO()
            pages[0].save(buf, format="PNG")
            return preprocess(buf.getvalue())
    except Exception:
        pass

    # Fallback PIL direct
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return preprocess(buf.getvalue())
    except Exception:
        pass

    return None


def to_image_bytes(path: str, max_px: int = 4096) -> bytes:
    """Charge un fichier image en bytes PNG, redimensionné si nécessaire."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        w, h = img.size
        if max(w, h) > max_px:
            ratio = max_px / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)),
                             Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        log.warning("[Vision] to_image_bytes : %s", e)
        return b""

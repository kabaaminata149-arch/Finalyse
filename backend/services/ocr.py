"""services/ocr.py — OCR Finalyse
Tesseract path : auto-détecté (Windows/Linux/Mac) ou via TESSERACT_CMD dans .env
"""
import os
import io
import logging

log = logging.getLogger("ocr")

# ── Résolution du chemin Tesseract ────────────────────────────────────────────
def _resolve_tesseract() -> str:
    """Retourne le chemin Tesseract : .env > PATH > emplacements Windows courants."""
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    load_dotenv(_env, override=True)

    # 1. Variable d'environnement explicite
    cmd = os.getenv("TESSERACT_CMD", "").strip()
    if cmd and os.path.isfile(cmd):
        return cmd

    # 2. Tesseract dans le PATH système
    import shutil
    found = shutil.which("tesseract")
    if found:
        return found

    # 3. Emplacements Windows courants (tous les utilisateurs)
    win_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    # Chercher aussi dans AppData de tous les profils
    appdata_root = os.path.expandvars(r"%LOCALAPPDATA%")
    if appdata_root and os.path.isdir(appdata_root):
        parent = os.path.dirname(appdata_root)
        for user_dir in os.listdir(parent):
            candidate = os.path.join(
                parent, user_dir,
                "AppData", "Local", "Programs", "Tesseract-OCR", "tesseract.exe"
            )
            win_paths.append(candidate)

    for p in win_paths:
        if os.path.isfile(p):
            return p

    # 4. Fallback — laisser pytesseract chercher lui-même
    return "tesseract"


import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = _resolve_tesseract()
log.info("[OCR] Tesseract : %s", pytesseract.pytesseract.tesseract_cmd)


# ── API publique ──────────────────────────────────────────────────────────────

def extract_text(file_path: str) -> str:
    """Extrait le texte d'un PDF ou d'une image."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        text = _pdfplumber(file_path)
        if text and len(text) > 30:
            return text
        return _tesseract_from_pdf(file_path)
    return _tesseract_image(file_path)


def extract_text_bytes(image_bytes: bytes) -> str:
    """OCR sur bytes déjà prétraités par OpenCV."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        conf = r"--oem 3 --psm 6 -l fra+eng"
        return pytesseract.image_to_string(img, config=conf).strip()
    except Exception as e:
        log.warning("[OCR] bytes : %s", e)
        return ""


# ── Méthodes internes ─────────────────────────────────────────────────────────

def _pdfplumber(path: str) -> str:
    try:
        import pdfplumber
        texts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    texts.append(t)
        return "\n".join(texts)
    except Exception as e:
        log.warning("[OCR] pdfplumber : %s", e)
        return ""


def _tesseract_image(path: str) -> str:
    """OCR sur image — passe par vision.py pour le prétraitement."""
    try:
        from services.vision import preprocess_file
        processed = preprocess_file(path)
        if processed:
            return extract_text_bytes(processed)
        # fallback sans prétraitement
        img = Image.open(path)
        return pytesseract.image_to_string(img, config=r"--oem 3 --psm 6 -l fra+eng")
    except Exception as e:
        log.warning("[OCR] image : %s", e)
        return ""


def _tesseract_from_pdf(path: str) -> str:
    """Convertit le PDF en image prétraitée puis applique OCR."""
    try:
        from services.vision import preprocess_pdf_to_bytes
        img_bytes = preprocess_pdf_to_bytes(path)
        if img_bytes:
            return extract_text_bytes(img_bytes)
    except Exception as e:
        log.warning("[OCR] PDF→OCR : %s", e)
    return ""

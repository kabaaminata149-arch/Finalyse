"""config.py — Finalyse Backend Configuration"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# En mode .exe, les données vont dans AppData/Finalyse
_DATA_DIR = Path(os.environ.get("FINALYSE_DATA_DIR", str(BASE_DIR)))

# JWT
JWT_SECRET    = os.getenv("JWT_SECRET", "finalyse-secret-key-CHANGE-IN-PRODUCTION")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_H  = int(os.getenv("JWT_EXPIRE_H", "24"))

# DB
DB_PATH = str(_DATA_DIR / "finalyse.db")

# Files
UPLOAD_DIR  = str(_DATA_DIR / "uploads")
EXPORT_DIR  = str(_DATA_DIR / "exports")
MAX_MB      = int(os.getenv("MAX_MB", "20"))
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}

# Ollama
OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# SMTP
SMTP_HOST = os.getenv("SMTP_HOST",  "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER",  "")
SMTP_PASS = os.getenv("SMTP_PASS",  "")

# Currency
DEVISE = "FCFA"

# Create dirs
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(EXPORT_DIR, exist_ok=True)

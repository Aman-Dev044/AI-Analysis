"""Central configuration, read once from environment / .env."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # Flask
    SECRET_KEY = os.getenv("SECRET_KEY") or "change-me-in-.env"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * _int("SESSION_DAYS", 7)
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 25)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
    DB_NAME = os.getenv("DB_NAME", "AI-Summary-Pro")

    # Ollama (remote VPS or local)
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
    OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")  # optional Bearer token (reverse proxy)
    OLLAMA_TIMEOUT = _int("OLLAMA_TIMEOUT_SECONDS", 600)
    OLLAMA_NUM_CTX = _int("OLLAMA_NUM_CTX", 8192)
    OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "")

    # Google Calendar OAuth
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:5000/google-calendar/callback"
    )
    GOOGLE_TOKEN_ENCRYPTION_KEY = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")

    # Summarisation
    CHUNK_CHARS = _int("CHUNK_CHARS", 12000)  # text per model call before map-reduce
    MAX_CHUNKS = _int("MAX_CHUNKS", 40)

    # OCR: auto | rapid | paddle | tesseract | ollama | off
    OCR_ENGINE = os.getenv("OCR_ENGINE", "auto").strip().lower()
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

    WORKERS = _int("WORKERS", 2)
    EXPIRING_SOON_DAYS = _int("EXPIRING_SOON_DAYS", 30)

    SEED_ADMIN_NAME = os.getenv("SEED_ADMIN_NAME", "Admin")
    SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@aisummary.app")
    # Prefer the hashed form so no plain-text password sits in .env
    SEED_ADMIN_PASSWORD_HASH = os.getenv("SEED_ADMIN_PASSWORD_HASH", "")
    SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "")

    ALLOWED_EXTENSIONS = {
        ".pdf", ".doc", ".docx", ".txt", ".md", ".csv",
        ".png", ".jpg", ".jpeg", ".svg", ".bmp", ".tif", ".tiff", ".webp",
    }

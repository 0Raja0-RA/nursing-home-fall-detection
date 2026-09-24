"""
config.py
=========
Konfigurasi aplikasi menggunakan pydantic-settings.

Semua environment variable didefinisikan di sini dan bisa
di-override melalui file .env atau env var langsung.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings — diambil dari environment variables."""

    # ---- General -------------------------------------------
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ---- Server --------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ---- Database ------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./fall_detection.db"

    # ---- Model Path ----------------------------------------
    # Path relatif ke file .pt hasil training YOLO11
    MODEL_PATH: str = str(
        Path(__file__).resolve().parents[3] / "ml" / "models" / "fall_detection" / "weights" / "best.pt"
    )
    CONFIDENCE_THRESHOLD: float = 0.5

    # ---- Fall Detection State Machine ----------------------
    FALL_DURATION_THRESHOLD: float = 10.0  # detik
    POSSIBLE_FALL_THRESHOLD: float = 2.0   # detik sebelum mulai hitung

    # ---- Camera --------------------------------------------
    CAMERA_SOURCE: str = "0"  # "0" = webcam, atau URL RTSP
    CAMERA_FPS: int = 15

    # ---- Telegram Notification -----------------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ---- CORS ----------------------------------------------
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()

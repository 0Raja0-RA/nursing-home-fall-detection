"""
settings.py
===========
REST endpoints untuk manajemen konfigurasi runtime.

Endpoints:
    GET  /api/settings/            — Ambil konfigurasi aktif
    PUT  /api/settings/threshold   — Update threshold durasi falling
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas import SettingsResponse, ThresholdUpdate

router = APIRouter()


@router.get("/", response_model=SettingsResponse)
async def get_current_settings():
    """Ambil konfigurasi aktif saat ini."""
    settings = get_settings()
    return SettingsResponse(
        fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
        possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
        camera_source=settings.CAMERA_SOURCE,
    )


@router.put("/threshold", response_model=SettingsResponse)
async def update_threshold(payload: ThresholdUpdate):
    """Update threshold durasi falling.

    Perubahan ini berlaku runtime (in-memory) dan tidak
    mengubah file .env. Untuk persistensi, simpan ke .env.

    TODO: Propagate perubahan ke semua state machine instances.
    """
    settings = get_settings()

    # Update in-memory (pydantic-settings cache)
    # Note: Karena lru_cache, kita perlu approach khusus
    # untuk update runtime. Ini adalah placeholder.
    settings.FALL_DURATION_THRESHOLD = payload.fall_duration_threshold

    return SettingsResponse(
        fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
        possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
        camera_source=settings.CAMERA_SOURCE,
    )

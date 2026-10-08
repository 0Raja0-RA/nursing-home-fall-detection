"""
settings.py
===========
REST endpoints untuk manajemen konfigurasi runtime.

Endpoints:
    GET  /api/settings/            — Ambil konfigurasi aktif
    PUT  /api/settings/threshold   — Update threshold durasi falling
    POST /api/settings/test-telegram — Kirim notifikasi uji ke Telegram
"""

from fastapi import APIRouter

from app.core.config import get_settings
from app.models.schemas import SettingsResponse, TestNotificationResponse, ThresholdUpdate

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


@router.post("/test-telegram", response_model=TestNotificationResponse)
async def test_telegram():
    """Kirim satu pesan uji ke Telegram.

    Ada supaya konfigurasi bisa diverifikasi tanpa harus berpura-pura jatuh di
    depan kamera, dan supaya kegagalan kirim ketahuan saat menyiapkan sistem --
    bukan saat ada yang benar-benar jatuh.
    """
    from app.services.notification_service import send_test_notification

    settings = get_settings()
    dikonfigurasi = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)

    if not dikonfigurasi:
        return TestNotificationResponse(
            terkirim=False,
            dikonfigurasi=False,
            pesan="TELEGRAM_BOT_TOKEN atau TELEGRAM_CHAT_ID belum diisi di backend/.env. "
                  "Ambil chat_id dengan: python tools/get_chat_id.py",
        )

    terkirim = await send_test_notification()
    return TestNotificationResponse(
        terkirim=terkirim,
        dikonfigurasi=True,
        pesan=("Pesan uji terkirim. Cek grup Telegram-mu."
               if terkirim else
               "Gagal mengirim setelah beberapa percobaan. Lihat log backend untuk alasannya; "
               "penyebab paling sering adalah tidak ada koneksi internet."),
    )

"""
notification_service.py
=======================
Mengirim notifikasi alert ke Telegram Bot API.

Menggunakan httpx async client untuk mengirim pesan ke chat ID
yang dikonfigurasi di environment variable.

Telegram Bot Setup:
    1. Buka @BotFather di Telegram, buat bot baru.
    2. Simpan token di TELEGRAM_BOT_TOKEN.
    3. Dapatkan chat_id target di TELEGRAM_CHAT_ID.
"""

import httpx

from app.core.config import get_settings

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram_alert(
    camera_id: str,
    fall_duration: float,
    message: str | None = None,
) -> bool:
    """Kirim alert ke Telegram.

    Args:
        camera_id: ID kamera yang mendeteksi jatuh.
        fall_duration: Durasi jatuh dalam detik.
        message: Pesan custom (opsional).

    Returns:
        True jika berhasil terkirim, False jika gagal.
    """
    settings = get_settings()

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        print("⚠️  Telegram not configured, skipping notification")
        return False

    text = message or (
        f"🚨 *FALL DETECTED!*\n\n"
        f"📷 Kamera: `{camera_id}`\n"
        f"⏱️ Durasi: `{fall_duration:.1f}` detik\n\n"
        f"Segera periksa kondisi penghuni!"
    )

    url = TELEGRAM_API_URL.format(token=settings.TELEGRAM_BOT_TOKEN)
    payload = {
        "chat_id": settings.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            print(f"✅ Telegram alert sent for camera {camera_id}")
            return True
    except httpx.HTTPError as e:
        print(f"❌ Failed to send Telegram alert: {e}")
        return False


async def send_test_notification() -> bool:
    """Kirim notifikasi test untuk verifikasi konfigurasi."""
    return await send_telegram_alert(
        camera_id="TEST",
        fall_duration=0.0,
        message="🔔 *Test Notification*\nSistem Fall Detection berhasil terhubung ke Telegram!",
    )

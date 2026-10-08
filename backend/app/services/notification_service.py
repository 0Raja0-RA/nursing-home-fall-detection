"""
notification_service.py
=======================
Mengirim notifikasi alert ke Telegram Bot API.

Setup:
    1. Buka @BotFather di Telegram, buat bot baru, simpan tokennya di
       TELEGRAM_BOT_TOKEN pada backend/.env.
    2. Ajak bot ke grup perawat, lalu kirim /start@NamaBot_bot di grup itu.
       Bot Telegram tidak bisa mengirim pesan ke pihak yang belum menyapanya.
    3. Ambil chat_id-nya:  python tools/get_chat_id.py

Dua hal yang sengaja diperhatikan di sini:

- **Foto, bukan sekadar teks.** Frame terakhir yang sudah digambari bounding box
  tersedia di registry, jadi mengirimkannya praktis tanpa biaya tambahan. Bagi
  perawat, melihat orangnya tergeletak di mana jauh lebih berguna daripada
  membaca "jatuh terdeteksi di cam-01".

- **Token tidak pernah masuk log.** URL Bot API memuat token, jadi pesan
  kesalahan dari httpx disensor dulu sebelum dicatat.
"""

import asyncio
import html
import re
from datetime import datetime
from typing import Optional

import httpx

from app.core.config import get_settings

from app.core.logging import get_logger
log = get_logger("app.services.notification_service")

API_URL = "https://api.telegram.org/bot{token}/{metode}"

# Token berbentuk <angka>:<rahasia>; dipakai untuk menyensornya dari pesan error.
_POLA_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_\-]{20,}")

# Jeda antar percobaan ulang, dalam detik. Percobaan pertama langsung.
JEDA_RETRY = (0.0, 5.0, 20.0)


def _sensor(teks: str) -> str:
    """Hilangkan token dari teks apa pun sebelum dicatat ke log."""
    return _POLA_TOKEN.sub("<TOKEN>", teks)


def susun_pesan(
    camera_name: str,
    fall_duration: float,
    waktu: Optional[datetime] = None,
) -> str:
    """Susun isi notifikasi dalam HTML.

    Memakai HTML, bukan Markdown, karena nama kamar bebas diisi perawat dan
    karakter seperti _ atau * akan membuat Markdown gagal diurai Telegram --
    pesannya ditolak, bukan sekadar tampil aneh.
    """
    waktu = waktu or datetime.now()
    return (
        "🚨 <b>TERDETEKSI JATUH</b>\n\n"
        f"📷 Lokasi : <b>{html.escape(camera_name)}</b>\n"
        f"⏱️ Durasi : {fall_duration:.1f} detik tidak bergerak\n"
        f"🕐 Waktu  : {waktu.strftime('%H:%M:%S, %d %b %Y')}\n\n"
        "Segera periksa kondisi penghuni."
    )


async def _kirim_sekali(
    token: str,
    chat_id: str,
    teks: str,
    foto: Optional[bytes],
) -> tuple[bool, str]:
    """Satu kali percobaan kirim. Pakai sendPhoto kalau ada gambarnya.

    Returns:
        (berhasil, alasan kalau gagal)
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if foto:
                r = await client.post(
                    API_URL.format(token=token, metode="sendPhoto"),
                    data={"chat_id": chat_id, "caption": teks, "parse_mode": "HTML"},
                    files={"photo": ("snapshot.jpg", foto, "image/jpeg")},
                )
            else:
                r = await client.post(
                    API_URL.format(token=token, metode="sendMessage"),
                    json={"chat_id": chat_id, "text": teks, "parse_mode": "HTML"},
                )
        if r.status_code == 200:
            return True, ""
        return False, f"HTTP {r.status_code}: {_sensor(r.text)[:200]}"
    except httpx.HTTPError as e:
        return False, _sensor(str(e))[:200]


async def send_telegram_alert(
    camera_name: str,
    fall_duration: float,
    foto: Optional[bytes] = None,
    waktu: Optional[datetime] = None,
    message: Optional[str] = None,
) -> bool:
    """Kirim alert ke Telegram, dengan percobaan ulang bila gagal.

    Gangguan jaringan sesaat itu lumrah, apalagi kalau laptop sedang berbagi
    koneksi lewat hotspot. Tiga percobaan dengan jeda menutup kasus itu tanpa
    menahan apa pun: fungsi ini dipanggil setelah alert tersimpan dan sudah
    disiarkan ke dashboard, jadi keterlambatannya tidak menunda siapa pun.

    Returns:
        True kalau salah satu percobaan berhasil.
    """
    settings = get_settings()

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        log.info("⚠️  Telegram belum dikonfigurasi (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID kosong)")
        return False

    teks = message or susun_pesan(camera_name, fall_duration, waktu)

    for percobaan, jeda in enumerate(JEDA_RETRY, start=1):
        if jeda:
            await asyncio.sleep(jeda)
        berhasil, alasan = await _kirim_sekali(
            settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_CHAT_ID, teks, foto
        )
        if berhasil:
            jenis = "foto" if foto else "pesan"
            log.info(f"✅ Telegram terkirim ({jenis}) untuk {camera_name}"
                     + (f" pada percobaan ke-{percobaan}" if percobaan > 1 else ""))
            return True
        log.info(f"⚠️  Telegram gagal (percobaan {percobaan}/{len(JEDA_RETRY)}): {alasan}")

    log.info(f"❌ Telegram menyerah setelah {len(JEDA_RETRY)} percobaan untuk {camera_name}")
    return False


async def send_test_notification() -> bool:
    """Kirim notifikasi uji untuk memverifikasi konfigurasi."""
    return await send_telegram_alert(
        camera_name="Uji Koneksi",
        fall_duration=0.0,
        message=(
            "🔔 <b>Uji Koneksi</b>\n\n"
            "Sistem Fall Detection berhasil terhubung ke Telegram.\n"
            "Pesan ini dikirim manual, bukan karena ada yang jatuh."
        ),
    )

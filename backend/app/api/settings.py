"""
settings.py
===========
REST endpoints untuk manajemen konfigurasi runtime.

Endpoints:
    GET  /api/settings/            — Ambil konfigurasi aktif
    PUT  /api/settings/threshold   — Update threshold durasi falling
    PUT  /api/settings/mode        — Ganti model detektor (bbox / pose)
    POST /api/settings/test-telegram — Kirim notifikasi uji ke Telegram

Perubahan dari kedua PUT di atas disimpan ke tabel app_settings, bukan hanya ke
memori. Kalau hanya di memori, satu kali restart backend mengembalikannya ke
bawaan tanpa pemberitahuan -- dan saat demo, yang berjalan bukan pengaturan yang
dikira sedang dipakai.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db
from app.db.repository import SettingRepository
from app.models.schemas import (
    ModeUpdate,
    SettingsResponse,
    TestNotificationResponse,
    ThresholdUpdate,
)
from app.services import inference_service

from app.core.logging import get_logger
log = get_logger("app.api.settings")

router = APIRouter()

# Kunci baris di tabel app_settings.
KUNCI_MODE = "detection_mode"
KUNCI_THRESHOLD = "fall_duration_threshold"


def _jawaban() -> SettingsResponse:
    """Potret konfigurasi aktif. Satu tempat, supaya ketiga endpoint sepakat."""
    settings = get_settings()
    return SettingsResponse(
        fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
        possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
        camera_source=settings.CAMERA_SOURCE,
        detection_mode=inference_service.mode_aktif(),
        available_modes=inference_service.MODE_INFO,
        telegram_configured=bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
    )


async def muat_dari_db(session: AsyncSession) -> None:
    """Terapkan pengaturan yang tersimpan. Dipanggil sekali saat startup."""
    tersimpan = await SettingRepository(session).semua()

    mode = tersimpan.get(KUNCI_MODE)
    if mode in inference_service.MODE_IDS:
        inference_service.set_mode(mode)
        log.info(f"⚙️  Mode deteksi dari database: {mode}")

    nilai = tersimpan.get(KUNCI_THRESHOLD)
    if nilai:
        try:
            get_settings().FALL_DURATION_THRESHOLD = float(nilai)
            log.info(f"⚙️  Threshold durasi jatuh dari database: {nilai} detik")
        except ValueError:
            log.info(f"⚠️  Nilai {KUNCI_THRESHOLD} di database tidak terbaca: {nilai!r}")


@router.get("/", response_model=SettingsResponse)
async def get_current_settings():
    """Ambil konfigurasi aktif saat ini, beserta daftar mode yang tersedia."""
    return _jawaban()


@router.put("/threshold", response_model=SettingsResponse)
async def update_threshold(payload: ThresholdUpdate, db: AsyncSession = Depends(get_db)):
    """Ubah berapa lama orang harus tergeletak sebelum alarm dikirim.

    Nilainya disimpan ke database DAN diteruskan ke state machine setiap kamera
    yang sedang berjalan. Tanpa penerusan itu, kamera yang sudah menyala tetap
    memakai angka lama sampai di-restart -- pengaturannya terlihat tersimpan di
    layar padahal tidak berpengaruh apa-apa.
    """
    from app.runtime.registry import registry

    get_settings().FALL_DURATION_THRESHOLD = payload.fall_duration_threshold
    await SettingRepository(db).simpan(
        KUNCI_THRESHOLD, str(payload.fall_duration_threshold)
    )

    for fsm in registry.state_machines.values():
        fsm.update_thresholds(fall_duration=payload.fall_duration_threshold)

    log.info(
        f"⚙️  Threshold durasi jatuh jadi {payload.fall_duration_threshold} detik "
        f"({len(registry.state_machines)} kamera diperbarui)"
    )
    return _jawaban()


@router.put("/mode", response_model=SettingsResponse)
async def update_mode(payload: ModeUpdate, db: AsyncSession = Depends(get_db)):
    """Ganti model detektor.

    State machine semua kamera direset setelah pergantian. Timer yang sudah
    separuh terkumpul di bawah satu model lalu dinilai model lain tidak bermakna,
    dan alarm yang lahir darinya tidak bisa dipertanggungjawabkan ke model mana
    pun.

    Model mode baru dimuat malas pada frame pertama, jadi permintaan ini kembali
    seketika; jeda pemuatan terasa sekali pada stream, lalu normal lagi.
    """
    from app.runtime.registry import registry

    if payload.detection_mode not in inference_service.MODE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Mode '{payload.detection_mode}' tidak dikenal. "
                   f"Pilihan: {', '.join(sorted(inference_service.MODE_IDS))}.",
        )

    inference_service.set_mode(payload.detection_mode)
    await SettingRepository(db).simpan(KUNCI_MODE, payload.detection_mode)

    for fsm in registry.state_machines.values():
        fsm.reset()

    log.info(
        f"🔀 Mode deteksi jadi '{payload.detection_mode}' "
        f"({len(registry.state_machines)} state machine direset)"
    )
    return _jawaban()


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

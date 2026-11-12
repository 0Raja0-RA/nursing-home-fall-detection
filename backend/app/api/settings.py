"""
settings.py
===========
REST endpoints untuk manajemen konfigurasi runtime.

Endpoints:
    GET  /api/settings/            — Ambil konfigurasi aktif
    PUT  /api/settings/threshold   — Update threshold durasi falling
    PUT  /api/settings/mode        — Ganti model detektor (bbox / pose)
    PUT  /api/settings/telegram    — Foto Telegram, kirim latihan, kabar kamera putus
    PUT  /api/settings/eskalasi    — Menit tanpa respons sebelum alarm dieskalasi
    PUT  /api/settings/shift       — Pola shift untuk ringkasan serah terima
    GET  /api/settings/pratinjau-ambang — Episode berbaring dinilai ulang dengan ambang lain
    GET  /api/settings/riwayat     — Log perubahan pengaturan, terbaru lebih dulu
    POST /api/settings/test-telegram — Kirim notifikasi uji ke Telegram

Semua endpoint wajib login. Perubahan dari ketiga PUT di atas disimpan ke tabel app_settings, bukan hanya ke
memori. Kalau hanya di memori, satu kali restart backend mengembalikannya ke
bawaan tanpa pemberitahuan -- dan saat demo, yang berjalan bukan pengaturan yang
dikira sedang dipakai.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import wajib_login, wajib_tim
from app.core.config import get_settings
from app.db.database import get_db
from app.db.repository import (
    KUNCI_ESKALASI,
    KUNCI_POLA_SHIFT,
    KUNCI_TG_FOTO,
    KUNCI_TG_KAMERA,
    KUNCI_TG_LATIHAN,
    SettingRepository,
)
from app.models.schemas import (
    ALASAN_PALSU,
    LABEL_PUTUSAN,
    MODE_FOTO_TELEGRAM,
    EskalasiUpdate,
    PerubahanPengaturan,
    PolaShiftUpdate,
    PratinjauAmbang,
    ModeUpdate,
    Pilihan,
    SettingsResponse,
    TelegramSettingsUpdate,
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


LABEL_KUNCI = {
    KUNCI_THRESHOLD: "Tunggu sebelum alarm (detik)",
    KUNCI_MODE: "Model deteksi",
    KUNCI_TG_FOTO: "Foto di pesan Telegram",
    KUNCI_TG_LATIHAN: "Latihan ke Telegram",
    KUNCI_TG_KAMERA: "Kabar kamera ke Telegram",
    KUNCI_ESKALASI: "Eskalasi (menit tanpa respons)",
    KUNCI_POLA_SHIFT: "Pola shift",
}


async def _catat(db: AsyncSession, oleh: str, kunci: str, lama, baru) -> None:
    """Simpan satu baris log bila nilainya benar-benar berubah."""
    from app.db.models import LogPengaturan

    lama = None if lama is None else str(lama)
    baru = None if baru is None else str(baru)
    if lama != baru:
        db.add(LogPengaturan(oleh=oleh, kunci=kunci, nilai_lama=lama, nilai_baru=baru))
        await db.commit()


async def _jawaban(db: AsyncSession) -> SettingsResponse:
    """Potret konfigurasi aktif. Satu tempat, supaya semua endpoint sepakat."""
    settings = get_settings()
    return SettingsResponse(
        fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
        possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
        camera_source=settings.CAMERA_SOURCE,
        detection_mode=inference_service.mode_aktif(),
        available_modes=inference_service.MODE_INFO,
        telegram_configured=bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID),
        telegram=await SettingRepository(db).telegram(),
        photo_modes=[Pilihan(id=k, label=v) for k, v in MODE_FOTO_TELEGRAM.items()],
        verdicts=[Pilihan(id=k, label=v) for k, v in LABEL_PUTUSAN.items()],
        false_alarm_reasons=[Pilihan(id=k, label=v) for k, v in ALASAN_PALSU.items()],
        eskalasi_menit=await SettingRepository(db).eskalasi_menit(),
        pola_shift=(await SettingRepository(db).ambil(KUNCI_POLA_SHIFT)) or "3",
        foto_masa_simpan_hari=settings.FOTO_MASA_SIMPAN_HARI,
        klip_masa_simpan_hari=settings.KLIP_MASA_SIMPAN_HARI,
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
async def get_current_settings(db: AsyncSession = Depends(get_db)):
    """Ambil konfigurasi aktif saat ini, beserta daftar mode yang tersedia."""
    return await _jawaban(db)


@router.put("/threshold", response_model=SettingsResponse)
async def update_threshold(payload: ThresholdUpdate, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Ubah berapa lama orang harus tergeletak sebelum alarm dikirim.

    Nilainya disimpan ke database DAN diteruskan ke state machine setiap kamera
    yang sedang berjalan. Tanpa penerusan itu, kamera yang sudah menyala tetap
    memakai angka lama sampai di-restart -- pengaturannya terlihat tersimpan di
    layar padahal tidak berpengaruh apa-apa.
    """
    from app.runtime.registry import registry

    lama = get_settings().FALL_DURATION_THRESHOLD
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
    await _catat(db, user.display_name, KUNCI_THRESHOLD, f"{lama:g}", f"{payload.fall_duration_threshold:g}")
    return await _jawaban(db)


@router.put("/mode", response_model=SettingsResponse)
async def update_mode(payload: ModeUpdate, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
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

    lama = inference_service.mode_aktif()
    inference_service.set_mode(payload.detection_mode)
    await SettingRepository(db).simpan(KUNCI_MODE, payload.detection_mode)

    for fsm in registry.state_machines.values():
        fsm.reset()

    log.info(
        f"🔀 Mode deteksi jadi '{payload.detection_mode}' "
        f"({len(registry.state_machines)} state machine direset)"
    )
    await _catat(db, user.display_name, KUNCI_MODE, lama, payload.detection_mode)
    return await _jawaban(db)


@router.put("/telegram", response_model=SettingsResponse)
async def update_telegram(payload: TelegramSettingsUpdate, user=Depends(wajib_login),
                          db: AsyncSession = Depends(get_db)):
    """Ubah cara pesan Telegram dikirim. Token dan chat id tetap hanya di server."""
    repo = SettingRepository(db)
    lama = await repo.telegram()
    if payload.photo_mode is not None:
        await repo.simpan(KUNCI_TG_FOTO, payload.photo_mode)
    if payload.send_drills is not None:
        await repo.simpan(KUNCI_TG_LATIHAN, "1" if payload.send_drills else "0")
    if payload.camera_offline is not None:
        await repo.simpan(KUNCI_TG_KAMERA, "1" if payload.camera_offline else "0")
    log.info(f"⚙️  Pengaturan Telegram diubah: {payload.model_dump(exclude_none=True)}")
    if payload.photo_mode is not None:
        await _catat(db, user.display_name, KUNCI_TG_FOTO, lama.photo_mode, payload.photo_mode)
    if payload.send_drills is not None:
        await _catat(db, user.display_name, KUNCI_TG_LATIHAN, _ya(lama.send_drills), _ya(payload.send_drills))
    if payload.camera_offline is not None:
        await _catat(db, user.display_name, KUNCI_TG_KAMERA, _ya(lama.camera_offline), _ya(payload.camera_offline))
    return await _jawaban(db)


def _ya(nilai: bool) -> str:
    return "nyala" if nilai else "mati"


@router.get("/riwayat", response_model=list[PerubahanPengaturan])
async def riwayat_perubahan(limit: int = Query(20, ge=1, le=200), _tim=Depends(wajib_tim),
                            db: AsyncSession = Depends(get_db)):
    """Perubahan pengaturan terbaru lebih dulu: siapa, kapan, dari nilai berapa ke berapa."""
    from sqlalchemy import select

    from app.db.models import LogPengaturan

    baris = (await db.execute(
        select(LogPengaturan).order_by(LogPengaturan.waktu.desc(), LogPengaturan.id.desc()).limit(limit)
    )).scalars().all()
    return [PerubahanPengaturan(waktu=b.waktu, oleh=b.oleh, kunci=b.kunci, label=LABEL_KUNCI.get(b.kunci, b.kunci),
                                nilai_lama=b.nilai_lama, nilai_baru=b.nilai_baru) for b in baris]


@router.get("/pratinjau-ambang", response_model=PratinjauAmbang)
async def pratinjau_ambang(
    ambang: float = Query(..., gt=0, le=60, description="Ambang yang ingin dicoba, detik"),
    hari: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Apa yang terjadi pada episode berbaring beberapa hari terakhir dengan ambang lain:
    alarm mana yang hilang (beserta putusannya) dan berapa tambahan yang belum pernah dinilai."""
    from app.services.episode import pratinjau
    return await pratinjau(db, ambang, get_settings().FALL_DURATION_THRESHOLD, hari)


@router.put("/shift", response_model=SettingsResponse)
async def update_pola_shift(payload: PolaShiftUpdate, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Pola shift untuk ringkasan serah terima: 3 shift (07, 14, 21) atau 2 shift (07, 19)."""
    lama = (await SettingRepository(db).ambil(KUNCI_POLA_SHIFT)) or "3"
    await SettingRepository(db).simpan(KUNCI_POLA_SHIFT, payload.pola_shift)
    log.info(f"⚙️  Pola shift jadi {payload.pola_shift} shift")
    await _catat(db, user.display_name, KUNCI_POLA_SHIFT, lama, payload.pola_shift)
    return await _jawaban(db)


@router.put("/eskalasi", response_model=SettingsResponse)
async def update_eskalasi(payload: EskalasiUpdate, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Ubah berapa menit alarm boleh tanpa respons sebelum dieskalasi.

    Angkanya berbeda antarproduk (Ascom memakai 30 detik, 60 detik, dan 5 menit), dan
    belum ada yang teruji untuk panti, jadi nilainya diatur dari dashboard dan diuji
    lewat uji mini.
    """
    lama = await SettingRepository(db).eskalasi_menit()
    await SettingRepository(db).simpan(KUNCI_ESKALASI, str(payload.eskalasi_menit))
    await _catat(db, user.display_name, KUNCI_ESKALASI, lama, payload.eskalasi_menit)
    log.info(f"⚙️  Eskalasi alarm jadi {payload.eskalasi_menit} menit tanpa respons")
    return await _jawaban(db)


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
            pesan="Telegram belum dikonfigurasi di server. Pengelola sistem perlu mengisi "
                  "token bot dan ID grup; lihat bagian Telegram di README.",
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

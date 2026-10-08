"""
camera_manager.py
=================
Menyalakan dan mematikan kamera beserta pipeline-nya saat aplikasi sedang berjalan.

Sebelumnya kamera hanya bisa dinyalakan di `lifespan()` dari satu environment
variable, sehingga mengganti alamat kamera berarti menyunting file dan me-restart
server. Modul ini memindahkan pekerjaan itu ke fungsi yang bisa dipanggil endpoint,
dengan daftar kamera disimpan di database.

Satu kamera terdiri dari tiga hal yang harus hidup dan mati bersama:
    CameraService (thread capture) + FallStateMachine + task pipeline
Ketiganya disimpan di registry dengan kunci camera_id yang sama.
"""

import asyncio

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import CameraRecord
from app.runtime.registry import registry

log = get_logger("app.runtime.camera_manager")


async def mulai_kamera(record: CameraRecord) -> bool:
    """Nyalakan satu kamera beserta state machine dan pipeline-nya.

    Aman dipanggil untuk kamera yang sudah jalan: yang lama dimatikan dulu.

    Returns:
        True kalau kamera berhasil dibuka, False kalau tidak.
    """
    # Import di dalam fungsi untuk menghindari circular import lewat registry.
    from app.runtime.detection_pipeline import camera_pipeline
    from app.services.alert_service import alert_service
    from app.services.camera_service import CameraService
    from app.services.state_machine import FallStateMachine

    await hentikan_kamera(record.id)

    settings = get_settings()
    camera = CameraService(camera_id=record.id, source=record.source, rotate=record.rotate)

    # start() membuka koneksi dan bisa memakan waktu beberapa detik, jadi jangan
    # sampai memblokir event loop -- REST dan WebSocket harus tetap melayani.
    if not await asyncio.to_thread(camera.start):
        log.info(f"❌ {record.id}: gagal membuka sumber {record.source}")
        return False

    # Tunggu frame pertama supaya status yang dilaporkan ke dashboard langsung benar,
    # bukan "Terputus" sesaat padahal kameranya baik-baik saja.
    if not await asyncio.to_thread(camera.tunggu_frame_pertama):
        log.info(f"⚠️  {record.id}: terbuka tapi belum mengirim frame dalam 2 detik")

    def trigger_alert(c_id: str, duration: float) -> None:
        asyncio.create_task(alert_service.process_confirmed_fall(c_id, duration))

    fsm = FallStateMachine(
        camera_id=record.id,
        fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
        possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
        debounce_frames=settings.DEBOUNCE_FRAMES,
        grace_period_sec=settings.GRACE_PERIOD_SEC,
        on_confirmed_fall=trigger_alert,
    )

    registry.cameras[record.id] = camera
    registry.state_machines[record.id] = fsm
    registry.pipeline_tasks[record.id] = asyncio.create_task(camera_pipeline(camera, fsm))
    return True


async def hentikan_kamera(camera_id: str) -> bool:
    """Matikan kamera dan bersihkan seluruh jejaknya di registry.

    Returns:
        True kalau sebelumnya memang ada kamera dengan id itu.
    """
    ada = camera_id in registry.cameras

    task = registry.pipeline_tasks.pop(camera_id, None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    camera = registry.cameras.pop(camera_id, None)
    if camera is not None:
        # stop() menunggu thread capture berhenti, jadi jalankan di luar event loop.
        await asyncio.to_thread(camera.stop)

    registry.state_machines.pop(camera_id, None)
    registry.latest_detection.pop(camera_id, None)
    registry.latest_status.pop(camera_id, None)
    return ada


async def hentikan_semua() -> None:
    """Matikan seluruh kamera. Dipanggil saat shutdown."""
    for camera_id in list(registry.cameras):
        await hentikan_kamera(camera_id)


async def muat_dari_db() -> None:
    """Nyalakan semua kamera yang tersimpan dan berstatus enabled.

    Kalau tabel kamera masih kosong, satu kamera diisikan otomatis dari
    CAMERA_SOURCE di environment. Ini menjaga alur lama tetap bekerja: menjalankan
    run-backend.bat dengan CAMERA_SOURCE tetap langsung menghasilkan satu kamera,
    tanpa harus mendaftarkannya lewat dashboard dulu.
    """
    from app.db.database import get_session_factory
    from app.db.repository import CameraRepository
    from app.models.schemas import CameraCreate

    settings = get_settings()

    async with get_session_factory()() as session:
        repo = CameraRepository(session)
        records = list(await repo.list_cameras())

        if not records:
            bawaan = CameraCreate(
                name="Kamera Utama",
                source=settings.CAMERA_SOURCE,
                rotate=settings.CAMERA_ROTATE,
                enabled=True,
            )
            records = [await repo.create_camera(bawaan, camera_id="cam-01")]
            log.info(f"Tabel kamera kosong, mendaftarkan bawaan dari CAMERA_SOURCE={settings.CAMERA_SOURCE}")

    aktif = 0
    for record in records:
        if not record.enabled:
            log.info(f"⏸️  {record.id} ({record.name}) dilewati: enabled=false")
            continue
        if await mulai_kamera(record):
            aktif += 1

    log.info(f"📷 {aktif} dari {len(records)} kamera terdaftar berhasil dinyalakan")

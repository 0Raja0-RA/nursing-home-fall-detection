"""
cameras.py
==========
REST endpoints untuk status kamera dan video stream.

Endpoints:
    GET    /api/cameras/              — Daftar kamera terdaftar + status terakhirnya
    POST   /api/cameras/              — Daftarkan kamera baru (sumber divalidasi dulu)
    POST   /api/cameras/scan          — Pindai jaringan lokal untuk mencari kamera
    GET    /api/cameras/{id}          — Satu kamera
    PATCH  /api/cameras/{id}          — Ubah nama/sumber/rotasi/enabled
    DELETE /api/cameras/{id}          — Hapus kamera
    GET    /api/cameras/{id}/stream   — Video MJPEG dengan bounding box tergambar

Daftar kamera disimpan di database, bukan environment variable, supaya alamat IP
kamera bisa diganti dari dashboard tanpa menyunting kode dan tanpa me-restart
server — alamat kamera HP berubah setiap kali berpindah jaringan WiFi.
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models import CameraRecord
from app.db.repository import CameraRepository
from app.models.schemas import (
    CameraCreate,
    CameraInfo,
    CameraStatus,
    CameraUpdate,
    LocalDevice,
    ScanResponse,
)
from app.runtime import camera_manager
from app.runtime.registry import registry
from app.services.camera_service import validasi_sumber

log = get_logger("app.api.cameras")

router = APIRouter()

def _gabung(record: CameraRecord) -> CameraInfo:
    """Gabungkan data kamera dari database dengan status runtime-nya.

    Kamera yang terdaftar tapi belum/tidak berjalan tetap dikembalikan, dengan
    is_active=False. Itu disengaja: pengguna harus tetap melihat kamera yang
    alamatnya salah atau yang sedang mati, supaya bisa memperbaikinya.
    """
    runtime = registry.latest_status.get(record.id)
    dasar = runtime.model_dump() if runtime else CameraStatus(camera_id=record.id).model_dump()

    # is_active diambil langsung dari kamera, bukan dari status broadcast terakhir.
    # Status broadcast bisa tertinggal satu putaran loop di belakang -- kamera yang
    # baru dinyalakan sempat terlihat OFFLINE padahal sudah mengalir.
    camera = registry.cameras.get(record.id)
    dasar["is_active"] = bool(camera and camera.sedang_mengalir)

    return CameraInfo(
        **dasar,
        name=record.name,
        source=record.source,
        rotate=record.rotate,
        enabled=record.enabled,
        stream_url=f"/api/cameras/{record.id}/stream",
    )


@router.get("/", response_model=list[CameraInfo])
async def get_cameras(db: AsyncSession = Depends(get_db)):
    """Ambil semua kamera terdaftar beserta status terakhirnya.

    Status runtime diisi oleh detection_pipeline setiap frame. Kamera yang baru
    didaftarkan tapi belum menghasilkan frame tetap muncul, dengan status default.
    """
    repo = CameraRepository(db)
    return [_gabung(r) for r in await repo.list_cameras()]


@router.post("/scan", response_model=ScanResponse)
async def scan_jaringan():
    """Pindai jaringan lokal untuk mencari perangkat yang menyiarkan kamera.

    Berguna karena alamat IP kamera HP berubah setiap kali berpindah WiFi.
    Pemindaian hanya menyentuh subnet /24 privat milik laptop ini, dan hanya
    membuka lalu menutup koneksi TCP pada port kamera yang lazim.
    """
    from app.services import network_scan

    subnets, kandidat, durasi = await asyncio.to_thread(network_scan.pindai)
    return ScanResponse(subnets=subnets, duration_sec=round(durasi, 2), candidates=kandidat)


@router.get("/devices", response_model=list[LocalDevice])
async def perangkat_lokal(db: AsyncSession = Depends(get_db)):
    """Kamera yang terpasang langsung di komputer ini, beserta namanya.

    OpenCV hanya menerima kamera lokal sebagai angka indeks dan tidak bisa
    menyebutkan namanya. Dengan Iriun yang memasang empat perangkat virtual
    sekaligus, menebak indeks jadi tidak mungkin -- endpoint ini memetakan angka
    itu ke nama yang terlihat di aplikasinya (Camera #1 sampai Camera #4).
    """
    from app.services import local_devices

    repo = CameraRepository(db)
    terpakai = {r.source for r in await repo.list_cameras()}
    return await asyncio.to_thread(local_devices.daftar_perangkat, terpakai)


@router.post("/", response_model=CameraInfo, status_code=status.HTTP_201_CREATED)
async def tambah_kamera(payload: CameraCreate, db: AsyncSession = Depends(get_db)):
    """Daftarkan kamera baru, lalu langsung nyalakan kalau enabled.

    Sumbernya divalidasi lebih dulu dan permintaan ditolak kalau tidak bisa
    dihubungi. Ini sengaja: salah ketik alamat jadi ketahuan saat itu juga,
    bukan muncul belakangan sebagai kamera OFFLINE tanpa penjelasan.
    """
    settings = get_settings()
    repo = CameraRepository(db)

    if await repo.count() >= settings.MAX_CAMERAS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Jumlah kamera sudah mencapai batas {settings.MAX_CAMERAS}. "
                   f"Hapus salah satu kamera dulu, atau naikkan MAX_CAMERAS. "
                   f"Batas ini ada karena inference berjalan di CPU: setiap kamera "
                   f"menambah beban secara linear.",
        )

    if await repo.source_dipakai(payload.source):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sumber '{payload.source}' sudah dipakai kamera lain.",
        )

    ok, alasan = await asyncio.to_thread(validasi_sumber, payload.source)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=alasan)

    record = await repo.create_camera(payload)
    if record.enabled and not await camera_manager.mulai_kamera(record):
        # Validasi lolos tapi capture tetap gagal dibuka. Recordnya tetap disimpan
        # supaya pengguna bisa memperbaiki alamatnya lewat PATCH, bukan hilang.
        log.info(f"{record.id}: sumber lolos validasi tapi gagal dibuka")

    return _gabung(record)


@router.get("/{camera_id}", response_model=CameraInfo)
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Ambil satu kamera berdasarkan ID."""
    record = await CameraRepository(db).get_camera(camera_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _gabung(record)


@router.patch("/{camera_id}", response_model=CameraInfo)
async def ubah_kamera(camera_id: str, payload: CameraUpdate, db: AsyncSession = Depends(get_db)):
    """Ubah kamera. Perubahan sumber/rotasi/enabled langsung diterapkan.

    Inilah jalur yang dipakai saat berpindah jaringan WiFi: cukup kirim alamat
    IP yang baru, kamera dinyalakan ulang tanpa me-restart server.
    """
    repo = CameraRepository(db)
    record = await repo.get_camera(camera_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    sumber_baru = payload.source is not None and payload.source != record.source

    if sumber_baru:
        if await repo.source_dipakai(payload.source, kecuali_id=camera_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sumber '{payload.source}' sudah dipakai kamera lain.",
            )
        ok, alasan = await asyncio.to_thread(validasi_sumber, payload.source)
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=alasan)

    record = await repo.update_camera(camera_id, payload)

    # Nyalakan ulang hanya kalau ada yang memengaruhi capture.
    perlu_restart = sumber_baru or payload.rotate is not None or payload.enabled is not None
    if perlu_restart:
        if record.enabled:
            await camera_manager.mulai_kamera(record)
        else:
            await camera_manager.hentikan_kamera(camera_id)

    return _gabung(record)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def hapus_kamera(camera_id: str, db: AsyncSession = Depends(get_db)):
    """Matikan dan hapus kamera dari daftar."""
    repo = CameraRepository(db)
    if await repo.get_camera(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    await camera_manager.hentikan_kamera(camera_id)
    await repo.delete_camera(camera_id)
    return None


async def generate_frames(camera_id: str):
    """Generator MJPEG: frame terbaru dari kamera, dengan kotak deteksi tergambar.

    Frame-nya sudah digambari dan di-encode oleh detection_pipeline, jadi generator
    ini hanya meneruskan byte yang sudah jadi. Sebelumnya tiap penonton menggambar
    dan meng-encode sendiri di event loop, sehingga membuka dua halaman sekaligus
    membuat keduanya berebut CPU dengan REST, WebSocket, dan pipeline deteksi --
    gejalanya satu halaman mengalir sementara yang lain tampak membeku. Sekarang
    penonton tambahan tidak menambah beban sama sekali.
    """
    if camera_id not in registry.cameras:
        return

    terakhir = -1
    while camera_id in registry.cameras:
        seq = registry.frame_seq.get(camera_id, 0)
        jpeg = registry.latest_jpeg.get(camera_id)
        if jpeg is not None and seq != terakhir:
            terakhir = seq
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
        await asyncio.sleep(0.02)


@router.get("/{camera_id}/stream")
async def video_stream(camera_id: str):
    """Endpoint video streaming langsung (MJPEG)."""
    if camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    return StreamingResponse(
        generate_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

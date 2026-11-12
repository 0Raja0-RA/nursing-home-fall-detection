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
    POST   /api/cameras/{id}/simulate-fall — Paksa simulasi jatuh (untuk demo)
    POST   /api/cameras/{id}/buka-asli — Video asli 15 detik saat alarm (kamera berprivasi)
    POST   /api/cameras/{id}/jeda     — Mulai atau perpanjang Mode perawatan
    DELETE /api/cameras/{id}/jeda     — Hentikan Mode perawatan lebih awal
    GET    /api/cameras/{id}/snapshot — Satu gambar terakhir (JPEG), untuk gambar mini
    GET    /api/cameras/{id}/stream   — Video MJPEG dengan bounding box tergambar

Daftar kamera disimpan di database, bukan environment variable, supaya alamat IP
kamera bisa diganti dari dashboard tanpa menyunting kode dan tanpa me-restart
server — alamat kamera HP berubah setiap kali berpindah jaringan WiFi.
"""

import asyncio
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import wajib_login, wajib_tim
from app.core.config import get_settings
from app.core.logging import get_logger, utc_now_naive
from app.db.database import get_db
from app.db.models import CameraRecord
from app.db.repository import CameraRepository
from app.models.schemas import (
    CameraCreate,
    CameraInfo,
    CameraStatus,
    CameraUpdate,
    JedaRequest,
    LocalDevice,
    ScanResponse,
    SimulationResponse,
)
from app.runtime import camera_manager
from app.runtime.registry import registry
from app.services import mode_perawatan
from app.services.camera_service import samarkan_sumber, validasi_sumber

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
    # Jeda dibaca langsung juga, supaya jawaban POST /jeda sudah memuatnya.
    jeda = mode_perawatan.aktif(record.id)
    sisa_asli = registry.asli_sampai.get(record.id, 0.0) - time.monotonic()
    dasar["asli_sampai"] = utc_now_naive() + timedelta(seconds=sisa_asli) if sisa_asli > 0 else None
    dasar["dijeda_sampai"] = jeda.sampai if jeda else None
    dasar["dijeda_oleh"] = jeda.oleh if jeda else None

    return CameraInfo(
        **dasar,
        name=record.name,
        # Kata sandi kamera tidak ikut dikirim ke browser.
        source=samarkan_sumber(record.source),
        rotate=record.rotate,
        enabled=record.enabled,
        privasi=record.privasi or "utuh",
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

    # Alamat tersamar yang dikirim balik apa adanya berarti "tidak diubah", bukan
    # alamat baru berisi kata sandi "***".
    if payload.source is not None and payload.source == samarkan_sumber(record.source):
        payload.source = None
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
    # Tampilan privasi berlaku seketika, tanpa menyalakan ulang kamera.
    if payload.privasi is not None and camera_id in registry.cameras:
        registry.cameras[camera_id].privasi = record.privasi
        if record.privasi == "utuh":
            registry.asli_sampai.pop(camera_id, None)

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
    record = await repo.get_camera(camera_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    await mode_perawatan.akhiri(db, camera_id, record.name, "kamera dihapus", kabari=False)
    await camera_manager.hentikan_kamera(camera_id)
    await repo.delete_camera(camera_id)
    return None


async def generate_frames(camera_id: str, asli: bool = False):
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
        # Video asli hanya selama masih dibuka; sesudahnya kembali ke tampilan privasi.
        if asli and registry.asli_sampai.get(camera_id, 0.0) > time.monotonic():
            jpeg = registry.latest_jpeg_asli.get(camera_id) or jpeg
        if jpeg is not None and seq != terakhir:
            terakhir = seq
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
        await asyncio.sleep(0.02)


@router.post("/{camera_id}/simulate-fall", response_model=SimulationResponse)
async def simulasi_jatuh(camera_id: str):
    """Paksa kamera ini dianggap melaporkan postur pemicu selama beberapa detik.

    Dipakai untuk demo, karena model masih sering membaca orang yang berbaring
    sebagai `transitional` di luar ruangan dataset, sehingga alarm sungguhan sulit
    dipicu dengan tubuh.

    Yang disimulasikan HANYA keluaran detektor. State machine tetap menghitung
    durasinya sendiri, debounce tetap berlaku, cooldown tetap dihormati, dan
    alertnya melewati jalur yang sama persis dengan deteksi sungguhan -- termasuk
    foto frame kamera saat itu juga. Alert yang dihasilkan ditandai `simulated`
    dan diberi awalan [SIMULASI] supaya tidak bisa tertukar dengan kejadian nyata.
    """
    import time

    if camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    if mode_perawatan.aktif(camera_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Kamera ini sedang dalam Mode perawatan. Lanjutkan pemantauan dulu.")

    settings = get_settings()
    # Cukup lama untuk melewati ambang, plus margin supaya tidak terpotong oleh
    # satu-dua frame yang meleset.
    durasi = settings.FALL_DURATION_THRESHOLD + 3.0
    registry.simulasi_sampai[camera_id] = time.monotonic() + durasi

    log.info(f"[{camera_id}] 🧪 Simulasi jatuh dimulai selama {durasi:.1f} detik")
    return SimulationResponse(
        camera_id=camera_id,
        durasi_simulasi=durasi,
        ambang_konfirmasi=settings.FALL_DURATION_THRESHOLD,
        pesan=f"Simulasi berjalan {durasi:.0f} detik. Alert muncul setelah "
              f"{settings.FALL_DURATION_THRESHOLD:.0f} detik.",
    )


DETIK_ASLI = 15


@router.post("/{camera_id}/buka-asli", response_model=CameraInfo)
async def buka_video_asli(camera_id: str, user=Depends(wajib_tim), db: AsyncSession = Depends(get_db)):
    """Buka video asli kamera berprivasi selama DETIK_ASLI detik, hanya saat ada alarm yang
    belum ditangani di ruang itu. Setiap pembukaan dicatat di tabel akses_video."""
    from sqlalchemy import or_, select

    from app.db.models import AksesVideo, AlertRecord

    record = await CameraRepository(db).get_camera(camera_id)
    if record is None or camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    if (record.privasi or "utuh") == "utuh":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kamera ini sudah menampilkan video utuh.")
    alarm = (await db.execute(
        select(AlertRecord).where(AlertRecord.camera_id == camera_id,
                                  or_(AlertRecord.acknowledged.is_(False), AlertRecord.acknowledged.is_(None)))
        .order_by(AlertRecord.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if alarm is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Video asli hanya bisa dibuka saat ada alarm yang belum ditangani di ruang ini.")
    registry.asli_sampai[camera_id] = time.monotonic() + DETIK_ASLI
    db.add(AksesVideo(camera_id=camera_id, alert_id=alarm.id, oleh=user.display_name,
                      sampai=utc_now_naive() + timedelta(seconds=DETIK_ASLI)))
    await db.commit()
    log.info(f"[{camera_id}] 👁 Video asli dibuka {DETIK_ASLI} detik oleh {user.display_name} (alert #{alarm.id})")
    return _gabung(record)


@router.post("/{camera_id}/jeda", response_model=CameraInfo)
async def mulai_jeda(camera_id: str, payload: JedaRequest,
                     user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Mode perawatan: jeda deteksi dan video kamera ini selama `menit`, atau perpanjang
    jeda yang sedang berjalan. Alarm yang sudah terbuka tidak ikut tertutup."""
    record = await CameraRepository(db).get_camera(camera_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    if camera_id not in registry.cameras:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Kamera ini sedang mati, jadi tidak ada yang perlu dijeda.")
    await mode_perawatan.mulai(db, camera_id, record.name, payload.menit, user.display_name)
    return _gabung(record)


@router.delete("/{camera_id}/jeda", response_model=CameraInfo)
async def akhiri_jeda(camera_id: str, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Hentikan Mode perawatan lebih awal. Aman dipanggil bila kamera tidak sedang dijeda."""
    record = await CameraRepository(db).get_camera(camera_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    await mode_perawatan.akhiri(db, camera_id, record.name, user.display_name)
    return _gabung(record)


@router.get("/{camera_id}/snapshot")
async def gambar_terakhir(camera_id: str):
    """Satu gambar terakhir kamera ini (JPEG), untuk gambar mini di Daftar Kamera.

    Gambar diam, bukan stream: daftar kamera tidak perlu ikut membuka koneksi MJPEG
    yang tidak pernah selesai, yang jumlahnya dibatasi browser per alamat.
    """
    from fastapi import Response

    jpeg = registry.latest_jpeg.get(camera_id)
    if jpeg is None:
        raise HTTPException(status_code=404, detail="Kamera ini belum mengirim gambar.")
    return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{camera_id}/stream")
async def video_stream(camera_id: str, asli: bool = False, user=Depends(wajib_login)):
    """Endpoint video streaming langsung (MJPEG). `asli=1` memakai video asli selama sedang
    dibuka sementara lewat POST /buka-asli; pengunjung tidak boleh."""
    if camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    if asli and user.role == "pengunjung":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pengunjung hanya bisa melihat.")
    return StreamingResponse(
        generate_frames(camera_id, asli),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

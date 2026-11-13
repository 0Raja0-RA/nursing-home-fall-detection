"""
alerts.py
=========
REST endpoints untuk insiden (alert jatuh) dan penanganannya. Semua wajib login.

Endpoints:
    GET  /api/alerts/                — Daftar alert, dengan filter antrean
    GET  /api/alerts/ekspor          — Unduh CSV dengan filter yang sama (tim saja)
    GET  /api/alerts/metrik          — Kartu angka untuk rentang waktu (tanpa latihan)
    POST /api/alerts/terlewat        — Catat jatuh yang tidak memicu alarm
    GET  /api/alerts/ringkasan       — Jumlah per kelompok, untuk tab dan lencana
    GET  /api/alerts/count           — Hitung total alert (lama, tetap dipertahankan)
    GET  /api/alerts/{id}            — Detail satu alert
    GET  /api/alerts/{id}/snapshot   — Foto kejadian (JPEG)
    GET  /api/alerts/{id}/klip       — Klip sebelum dan sesudah kejadian (JSON, JPEG base64)
    PUT  /api/alerts/{id}/claim      — "Saya ke sana"
    PUT  /api/alerts/{id}/ack        — "Tandai Ditangani", dengan putusan dan catatan opsional
    PUT  /api/alerts/{id}/verdict    — Isi atau ubah putusan belakangan
    PUT  /api/alerts/{id}/note       — Tambah atau ubah catatan perawat
    POST /api/alerts/{id}/telegram   — Kirim ulang pesan Telegram yang gagal

Status penanganan dan putusan sengaja dua hal terpisah. Penanganan menjawab
"sudah ada yang menolong?", putusan menjawab "apakah ini benar jatuh?". Alarm
yang ditutup tanpa putusan tetap di antrean Perlu tindakan sampai dinilai.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import wajib_login, wajib_tim
from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models import AlertRecord, AlertSnapshot, UserRecord
from app.models.schemas import (
    AckRequest,
    AlertResponse,
    AlertSummary,
    KejadianTerlewat,
    MetrikInsiden,
    NoteUpdate,
    Putusan,
    VerdictUpdate,
)
from app.services import insiden_service as insiden
from app.services import klip
from app.services.ekspor import csv_insiden

router = APIRouter()

log = get_logger("app.api.alerts")

Status = Literal["terbuka", "perlu_tindakan", "selesai", "semua"]
FilterPutusan = Literal["jatuh", "palsu", "belum_yakin", "belum_dinilai"]


def _rapikan_catatan(teks: Optional[str]) -> Optional[str]:
    """Spasi di tepi dibuang; catatan kosong disimpan sebagai NULL, bukan ''."""
    if teks is None:
        return None
    teks = teks.strip()
    return teks or None


async def _ambil_alert(alert_id: int, db: AsyncSession) -> AlertRecord:
    alert = await db.get(AlertRecord, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


# Belum dinilai: sudah ditangani, alarm sungguhan, dan putusannya kosong atau masih ragu.
_BELUM_DINILAI = and_(
    AlertRecord.acknowledged.is_(True),
    AlertRecord.simulated.is_(False),
    or_(AlertRecord.verdict.is_(None), AlertRecord.verdict == Putusan.BELUM_YAKIN.value),
)
_TERBUKA = or_(AlertRecord.acknowledged.is_(False), AlertRecord.acknowledged.is_(None))


@router.get("/", response_model=list[AlertResponse])
async def get_alerts(
    skip: int = Query(0, ge=0, description="Offset pagination"),
    limit: int = Query(20, ge=1, le=200, description="Jumlah item per halaman"),
    acknowledged: Optional[bool] = Query(None, description="Filter berdasarkan status acknowledge"),
    status_: Optional[Status] = Query(
        None, alias="status",
        description="terbuka = belum ditangani; perlu_tindakan = belum ditangani atau belum dinilai; "
                    "selesai = ditangani dan sudah dinilai",
    ),
    camera_id: Optional[str] = Query(None),
    verdict: Optional[FilterPutusan] = Query(None),
    simulated: Optional[bool] = Query(None, description="true = hanya latihan, false = tanpa latihan"),
    sejak: Optional[datetime] = Query(None, description="Batas bawah created_at (UTC)"),
    sampai: Optional[datetime] = Query(None, description="Batas atas created_at (UTC)"),
    db: AsyncSession = Depends(get_db),
):
    """Ambil daftar alert terbaru lebih dulu, dengan filter untuk antrean Riwayat Insiden."""
    query = _saring(
        select(AlertRecord).order_by(AlertRecord.created_at.desc(), AlertRecord.id.desc()),
        acknowledged, status_, camera_id, verdict, simulated, sejak, sampai,
    )
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


def _saring(query, acknowledged, status_, camera_id, verdict, simulated, sejak, sampai):
    """Filter yang sama untuk daftar dan ekspor CSV."""
    if acknowledged is not None:
        query = query.where(AlertRecord.acknowledged == acknowledged)
    if status_ == "terbuka":
        query = query.where(_TERBUKA)
    elif status_ == "perlu_tindakan":
        query = query.where(or_(_TERBUKA, _BELUM_DINILAI))
    elif status_ == "selesai":
        query = query.where(AlertRecord.acknowledged.is_(True), ~_BELUM_DINILAI)
    if camera_id:
        query = query.where(AlertRecord.camera_id == camera_id)
    if verdict == "belum_dinilai":
        query = query.where(AlertRecord.verdict.is_(None))
    elif verdict:
        query = query.where(AlertRecord.verdict == verdict)
    if simulated is not None:
        query = query.where(AlertRecord.simulated.is_(simulated))
    if sejak:
        query = query.where(AlertRecord.created_at >= sejak.replace(tzinfo=None))
    if sampai:
        query = query.where(AlertRecord.created_at <= sampai.replace(tzinfo=None))
    return query


@router.get("/ekspor")
async def ekspor_csv(
    status_: Optional[Status] = Query(None, alias="status"),
    camera_id: Optional[str] = Query(None),
    verdict: Optional[FilterPutusan] = Query(None),
    simulated: Optional[bool] = Query(None),
    sejak: Optional[datetime] = Query(None, description="Batas bawah created_at (UTC)"),
    sampai: Optional[datetime] = Query(None, description="Batas atas created_at (UTC)"),
    _tim=Depends(wajib_tim),
    db: AsyncSession = Depends(get_db),
):
    """Semua alert yang cocok dengan filter, sebagai CSV, urut dari yang terlama.

    Untuk uji mini dan laporan: waktu respons sudah dihitung dalam detik. Pengunjung
    tidak boleh mengunduh, walau boleh melihat daftarnya.
    """
    query = _saring(
        select(AlertRecord).order_by(AlertRecord.created_at.asc(), AlertRecord.id.asc()),
        None, status_, camera_id, verdict, simulated, sejak, sampai,
    )
    alerts = (await db.execute(query)).scalars().all()
    nama = f"insiden-falldetect-{datetime.now():%Y%m%d-%H%M}.csv"
    return Response(content=csv_insiden(alerts), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nama}"',
                             "Cache-Control": "no-store"})


@router.get("/metrik", response_model=MetrikInsiden)
async def metrik(
    sejak: Optional[datetime] = Query(None, description="Batas bawah created_at (UTC)"),
    db: AsyncSession = Depends(get_db),
):
    """Kartu angka Riwayat Insiden untuk rentang waktu yang dipilih. Latihan tidak dihitung."""
    query = select(AlertRecord).where(AlertRecord.simulated.is_(False))
    if sejak:
        query = query.where(AlertRecord.created_at >= sejak.replace(tzinfo=None))
    return insiden.hitung_metrik((await db.execute(query)).scalars().all())


@router.post("/terlewat", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def catat_terlewat(payload: KejadianTerlewat, user=Depends(wajib_login), db: AsyncSession = Depends(get_db)):
    """Catat jatuh yang tidak memicu alarm, misalnya penghuni ditemukan di lantai.

    Tanpa catatan ini, jatuh yang terlewat tidak pernah muncul di riwayat, sehingga
    tidak bisa dihitung berapa jatuh yang benar-benar terdeteksi. Entrinya langsung
    berputusan jatuh sungguhan dan tidak ikut dihitung sebagai alarm.
    """
    from app.core.logging import utc_now_naive
    from app.db.models import CameraRecord

    waktu = payload.waktu.astimezone(timezone.utc).replace(tzinfo=None) if payload.waktu.tzinfo else payload.waktu
    sekarang = utc_now_naive()
    if waktu > sekarang + timedelta(minutes=1):
        raise HTTPException(status_code=422, detail="Waktu kejadian tidak boleh di masa depan.")
    kamera = await db.get(CameraRecord, payload.camera_id)
    if kamera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    alert = AlertRecord(
        camera_id=kamera.id, camera_name=kamera.name, severity="critical",
        message="Jatuh tidak terdeteksi sistem, dicatat manual.", fall_duration=0.0,
        acknowledged=True, acknowledged_at=sekarang, acknowledged_by=user.display_name,
        verdict=Putusan.JATUH.value, verdict_by=user.display_name, verdict_at=sekarang,
        caregiver_note=_rapikan_catatan(payload.catatan), created_at=waktu, terlewat=True,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    log.info(f"[{kamera.id}] jatuh terlewat dicatat {user.display_name} untuk {waktu:%Y-%m-%d %H:%M} UTC")
    return alert


@router.get("/ringkasan", response_model=AlertSummary)
async def ringkasan(db: AsyncSession = Depends(get_db)):
    """Jumlah per kelompok untuk tab Riwayat Insiden dan lencana di menu."""
    async def hitung(*syarat) -> int:
        return await db.scalar(select(func.count(AlertRecord.id)).where(*syarat)) or 0

    # Alarm sungguhan: bukan latihan, dan bukan jatuh terlewat yang dicatat manual.
    sungguhan = and_(AlertRecord.simulated.is_(False), AlertRecord.terlewat.is_(False))
    belum_ditangani = await hitung(_TERBUKA)
    belum_dinilai = await hitung(_BELUM_DINILAI)
    return AlertSummary(
        perlu_tindakan=belum_ditangani + belum_dinilai,
        belum_ditangani=belum_ditangani,
        sedang_ditangani=await hitung(_TERBUKA, AlertRecord.claimed_by.is_not(None)),
        belum_dinilai=belum_dinilai,
        total=await hitung(sungguhan),
        jatuh=await hitung(sungguhan, AlertRecord.verdict == Putusan.JATUH.value),
        palsu=await hitung(sungguhan, AlertRecord.verdict == Putusan.PALSU.value),
        latihan=await hitung(AlertRecord.simulated.is_(True)),
        telegram_gagal=await hitung(AlertRecord.telegram_status == "gagal"),
    )


@router.get("/count")
async def get_alert_count(
    acknowledged: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Hitung total alert."""
    query = select(func.count(AlertRecord.id))
    if acknowledged is not None:
        query = query.where(AlertRecord.acknowledged == acknowledged)
    result = await db.execute(query)
    return {"count": result.scalar()}


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Ambil detail satu alert berdasarkan ID."""
    return await _ambil_alert(alert_id, db)


@router.get("/{alert_id}/snapshot")
async def get_snapshot(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Foto kejadian dalam tampilan privasi kamera (utuh, buram, atau kerangka saja), sama
    dengan video yang dilihat setiap orang yang masuk, termasuk pengunjung pameran. Buram
    tambahan untuk Telegram tidak diterapkan di sini.

    Tidak disimpan di cache browser: foto penghuni yang tergeletak adalah data
    kesehatan, dan hanya boleh dilihat selama sesinya masih sah.
    """
    foto = await db.get(AlertSnapshot, alert_id)
    if foto is None:
        raise HTTPException(status_code=404, detail=await _alasan_tanpa_foto(db, alert_id))
    return Response(content=foto.jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


async def _alasan_tanpa_foto(db: AsyncSession, alert_id: int) -> str:
    from app.core.config import get_settings
    from app.core.logging import utc_now_naive

    alert = await db.get(AlertRecord, alert_id)
    hari = get_settings().FOTO_MASA_SIMPAN_HARI
    if alert is not None and alert.terlewat:
        return "Jatuh ini dicatat manual, jadi tidak ada foto dari kamera."
    if hari <= 0:
        return "Foto kejadian tidak disimpan di server, sesuai pengaturan masa simpan."
    if alert is not None and alert.created_at and alert.created_at < utc_now_naive() - timedelta(days=hari):
        return f"Foto sudah dihapus otomatis karena melewati masa simpan {hari} hari."
    return "Foto kejadian tidak tersimpan untuk alert ini."


_TANPA_KLIP = {
    "merekam": "Klip masih direkam. Coba lagi beberapa detik lagi.",
    "kosong": "Kamera tidak mengirim gambar di sekitar kejadian, jadi tidak ada klip.",
    "gagal": "Klip gagal disimpan di server.",
    "dihapus": "Klip sudah dihapus karena melewati masa simpan.",
}


@router.get("/{alert_id}/klip")
async def get_klip(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Klip sebelum dan sesudah kejadian: waktu tiap frame (detik, relatif terhadap
    alarm) dan JPEG-nya dalam base64. Tidak disimpan di cache browser, sama seperti foto."""
    alert = await _ambil_alert(alert_id, db)
    isi = await asyncio.to_thread(klip.baca_berkas, alert_id)
    if isi is None:
        raise HTTPException(status_code=404, detail=_TANPA_KLIP.get(
            alert.klip_status, "Klip tidak tersimpan untuk kejadian ini."))
    return JSONResponse(isi, headers={"Cache-Control": "no-store"})


def _konflik(e: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put("/{alert_id}/claim", response_model=AlertResponse)
async def claim_alert(
    alert_id: int,
    user: UserRecord = Depends(wajib_login),
    db: AsyncSession = Depends(get_db),
):
    """"Saya ke sana". Banner berubah amber dan bunyi berhenti di semua dashboard."""
    try:
        return await insiden.klaim(db, alert_id, user.display_name)
    except insiden.InsidenTidakAda:
        raise HTTPException(status_code=404, detail="Alert not found")
    except insiden.KonflikInsiden as e:
        raise _konflik(e)


@router.put("/{alert_id}/ack", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    # Annotated, bukan `= Body(None)`: dengan begitu nilai bawaannya benar-benar
    # None saat fungsi dipanggil langsung (di tes), bukan objek penanda FastAPI.
    payload: Annotated[Optional[AckRequest], Body()] = None,
    user: UserRecord = Depends(wajib_login),
    db: AsyncSession = Depends(get_db),
):
    """Tandai alert sebagai sudah ditangani, dengan putusan dan catatan opsional.

    Alert terbaru sebuah kamera sekaligus menutup insiden di kamera itu: state
    machine-nya kembali ke MONITORING. Lalu disiarkan ke semua dashboard yang
    terbuka, supaya banner alarm hilang di layar mana pun, bukan hanya di layar
    tempat tombolnya diklik.

    Catatan yang tidak dikirim atau kosong tidak menghapus catatan yang sudah ada:
    menandai ulang tidak boleh menghapus tulisan perawat.
    """
    try:
        return await insiden.tutup(
            db, alert_id, user.display_name,
            verdict=payload.verdict if payload else None,
            alasan=payload.reason if payload else None,
            catatan=_rapikan_catatan(payload.note if payload else None),
        )
    except insiden.InsidenTidakAda:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.put("/{alert_id}/verdict", response_model=AlertResponse)
async def update_verdict(
    alert_id: int,
    payload: VerdictUpdate,
    user: UserRecord = Depends(wajib_login),
    db: AsyncSession = Depends(get_db),
):
    """Isi atau ubah putusan, mis. alarm yang ditutup dari Telegram tanpa putusan."""
    try:
        return await insiden.putuskan(db, alert_id, user.display_name, payload.verdict, payload.reason)
    except insiden.InsidenTidakAda:
        raise HTTPException(status_code=404, detail="Alert not found")
    except insiden.KonflikInsiden as e:
        raise _konflik(e)


@router.put("/{alert_id}/note", response_model=AlertResponse)
async def update_note(
    alert_id: int,
    payload: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Tambah atau ubah catatan perawat untuk satu alert.

    Terpisah dari /ack karena dalam keadaan darurat perawat menolong dulu dan
    menandai alarm tanpa sempat menulis; catatannya menyusul dari halaman
    Riwayat Insiden. Mengirim teks kosong menghapus catatan.
    """
    alert = await _ambil_alert(alert_id, db)
    alert.caregiver_note = _rapikan_catatan(payload.note)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.post("/{alert_id}/telegram", response_model=AlertResponse, status_code=status.HTTP_202_ACCEPTED)
async def kirim_ulang_telegram(alert_id: int, db: AsyncSession = Depends(get_db)):
    """Kirim ulang pesan Telegram yang gagal. Hasilnya terlihat beberapa detik kemudian."""
    from app.core.config import get_settings
    from app.services.alert_service import alert_service

    alert = await _ambil_alert(alert_id, db)
    settings = get_settings()
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Telegram belum dikonfigurasi di server.")
    if alert.telegram_status in ("mengirim", "terkirim"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Pesan ini sedang dikirim atau sudah terkirim.")
    alert.telegram_status = "mengirim"
    await db.commit()
    await db.refresh(alert)
    asyncio.create_task(alert_service.kirim_telegram(alert.id))
    return alert

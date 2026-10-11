"""
alerts.py
=========
REST endpoints untuk manajemen alert (riwayat notifikasi jatuh).

Endpoints:
    GET  /api/alerts/          — Ambil daftar alert (dengan pagination)
    GET  /api/alerts/{id}      — Detail satu alert
    PUT  /api/alerts/{id}/ack  — Acknowledge (tandai sudah ditangani)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, utc_now_naive
from app.db.database import get_db
from app.db.models import AlertRecord
from app.models.schemas import AlertResponse, FallState, WSMessage
from app.websocket.ws_manager import manager

router = APIRouter()

log = get_logger("app.api.alerts")


async def _tutup_insiden(alert: AlertRecord, db: AsyncSession) -> bool:
    """Alert yang ditangani menutup insiden yang sedang berjalan di kameranya.

    Tanpa ini kamera bisa tersangkut di CONFIRMED_FALL setelah alarm ditangani:
    deteksi yang ragu-ragu (mis. wajah memenuhi frame sehingga bahu dan pinggul
    tidak terlihat) MENAHAN timer, jadi tidak ada observasi yang bisa
    mengembalikannya ke MONITORING. Dashboard tetap merah, dan jatuh berikutnya
    di kamera itu tidak berbunyi karena alarmnya dianggap sudah terkirim.

    Dua pengaman supaya penutupan tidak salah sasaran:
      - hanya kalau kamera memang sedang CONFIRMED_FALL. Jatuh baru yang masih
        dihitung (POSSIBLE_FALL) tidak boleh ikut terhapus timernya;
      - hanya alert TERBARU kamera itu. Menandai alert lama dari halaman Riwayat
        Insiden tidak boleh mereset kejadian yang sedang berlangsung sekarang.

    Kalau orangnya ternyata masih tergeletak, timer mulai lagi dari nol dan alarm
    berbunyi lagi setelah ambang -- itu perilaku yang aman.

    Returns:
        True kalau state machine kamera direset.
    """
    from app.runtime.registry import registry

    fsm = registry.state_machines.get(alert.camera_id)
    if fsm is None or fsm.state != FallState.CONFIRMED_FALL:
        return False

    lebih_baru = await db.scalar(
        select(func.count(AlertRecord.id)).where(
            AlertRecord.camera_id == alert.camera_id,
            AlertRecord.id > alert.id,
        )
    )
    if lebih_baru:
        return False

    fsm.reset()
    # Simulasi yang masih berjalan akan langsung memicu timer lagi, jadi ikut
    # diakhiri: "ditangani" berarti kejadiannya -- simulasi atau bukan -- selesai.
    registry.simulasi_sampai.pop(alert.camera_id, None)
    log.info(f"[{alert.camera_id}] insiden ditutup lewat alert #{alert.id}, kembali ke MONITORING")
    return True


@router.get("/", response_model=list[AlertResponse])
async def get_alerts(
    skip: int = Query(0, ge=0, description="Offset pagination"),
    limit: int = Query(20, ge=1, le=100, description="Jumlah item per halaman"),
    acknowledged: Optional[bool] = Query(None, description="Filter berdasarkan status acknowledge"),
    db: AsyncSession = Depends(get_db),
):
    """Ambil daftar alert dengan pagination dan optional filter."""
    query = select(AlertRecord).order_by(AlertRecord.created_at.desc())

    if acknowledged is not None:
        query = query.where(AlertRecord.acknowledged == acknowledged)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


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
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Ambil detail satu alert berdasarkan ID."""
    result = await db.execute(
        select(AlertRecord).where(AlertRecord.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.put("/{alert_id}/ack", response_model=AlertResponse)
async def acknowledge_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Tandai alert sebagai sudah ditangani (acknowledged).

    Alert terbaru sebuah kamera sekaligus menutup insiden di kamera itu: state
    machine-nya kembali ke MONITORING (lihat _tutup_insiden). Lalu siarkan ke semua dashboard yang terbuka, supaya banner alarm hilang di
    layar mana pun -- bukan hanya di layar tempat tombolnya diklik. Tanpa ini,
    alert yang ditangani dari halaman Riwayat Insiden, atau oleh perawat lain di
    perangkat berbeda, tetap menyala dan berbunyi sampai halamannya dimuat ulang.
    """
    result = await db.execute(
        select(AlertRecord).where(AlertRecord.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_at = utc_now_naive()
    await db.commit()
    await db.refresh(alert)

    await _tutup_insiden(alert, db)
    await manager.broadcast(WSMessage(event="alert_ack", data={"id": alert.id}))
    return alert

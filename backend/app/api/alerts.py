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

from app.db.database import AlertRecord, get_db
from app.models.schemas import AlertResponse

router = APIRouter()


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
    """Tandai alert sebagai sudah ditangani (acknowledged)."""
    result = await db.execute(
        select(AlertRecord).where(AlertRecord.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    alert.acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    await db.commit()
    await db.refresh(alert)
    return alert

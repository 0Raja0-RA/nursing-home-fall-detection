"""
repository.py
=============
Repository layer untuk operasi ke database.
Semua query SQL harus melalui layer ini agar konsisten.
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import utc_now_naive
from app.db.models import AlertRecord
from app.models.schemas import AlertCreate


class AlertRepository:
    """Repository untuk operasi CRUD tabel alerts."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_alert(self, data: AlertCreate) -> AlertRecord:
        """Buat record alert baru."""
        db_obj = AlertRecord(
            camera_id=data.camera_id,
            severity=data.severity.value,
            message=data.message,
            fall_duration=data.fall_duration,
        )
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def get_recent_alerts(self, limit: int = 50) -> Sequence[AlertRecord]:
        """Ambil list alert terbaru (menurun)."""
        stmt = select(AlertRecord).order_by(AlertRecord.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def acknowledge_alert(self, alert_id: int) -> bool:
        """Tandai alert sebagai sudah ditangani (acknowledged)."""
        stmt = (
            update(AlertRecord)
            .where(AlertRecord.id == alert_id)
            .where(AlertRecord.acknowledged == False)
            .values(
                acknowledged=True,
                acknowledged_at=utc_now_naive(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def mark_as_notified(self, alert_id: int, status: bool = True) -> bool:
        """Tandai alert bahwa notifikasi telegram sudah terkirim/gagal."""
        stmt = (
            update(AlertRecord)
            .where(AlertRecord.id == alert_id)
            .values(notified=status)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

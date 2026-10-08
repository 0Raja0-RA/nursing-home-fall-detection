"""
repository.py
=============
Repository layer untuk operasi ke database.
Semua query SQL harus melalui layer ini agar konsisten.
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import utc_now_naive
from app.db.models import AlertRecord, CameraRecord
from app.models.schemas import AlertCreate, CameraCreate, CameraUpdate


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


class CameraRepository:
    """Repository untuk operasi CRUD tabel cameras."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_cameras(self) -> Sequence[CameraRecord]:
        """Ambil semua kamera terdaftar, urut berdasarkan id (cam-01, cam-02, ...)."""
        stmt = select(CameraRecord).order_by(CameraRecord.id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_camera(self, camera_id: str) -> CameraRecord | None:
        """Ambil satu kamera berdasarkan id."""
        return await self.session.get(CameraRecord, camera_id)

    async def count(self) -> int:
        """Jumlah kamera terdaftar."""
        result = await self.session.execute(select(CameraRecord.id))
        return len(result.scalars().all())

    async def next_id(self) -> str:
        """Hasilkan id kamera berikutnya: cam-01, cam-02, dan seterusnya.

        Nomor yang sudah dipakai dilewati, dan slot kosong di tengah dipakai ulang
        supaya id tetap pendek setelah ada kamera yang dihapus.
        """
        result = await self.session.execute(select(CameraRecord.id))
        terpakai = set(result.scalars().all())
        n = 1
        while f"cam-{n:02d}" in terpakai:
            n += 1
        return f"cam-{n:02d}"

    async def create_camera(self, data: CameraCreate, camera_id: str | None = None) -> CameraRecord:
        """Daftarkan kamera baru."""
        db_obj = CameraRecord(
            id=camera_id or await self.next_id(),
            name=data.name,
            source=data.source,
            rotate=data.rotate,
            enabled=data.enabled,
        )
        self.session.add(db_obj)
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update_camera(self, camera_id: str, data: CameraUpdate) -> CameraRecord | None:
        """Ubah sebagian field kamera. Field yang None dibiarkan apa adanya."""
        record = await self.session.get(CameraRecord, camera_id)
        if record is None:
            return None
        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(record, field, value)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def delete_camera(self, camera_id: str) -> bool:
        """Hapus kamera dari daftar."""
        stmt = delete(CameraRecord).where(CameraRecord.id == camera_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def source_dipakai(self, source: str, kecuali_id: str | None = None) -> bool:
        """Cek apakah sumber ini sudah dipakai kamera lain.

        Dua kamera yang menunjuk sumber yang sama akan menjalankan inference dua kali
        untuk gambar yang sama -- membuang CPU tanpa menambah informasi.
        """
        stmt = select(CameraRecord.id).where(CameraRecord.source == source)
        if kecuali_id:
            stmt = stmt.where(CameraRecord.id != kecuali_id)
        result = await self.session.execute(stmt)
        return result.scalars().first() is not None

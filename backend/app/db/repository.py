"""
repository.py
=============
Repository layer untuk operasi ke database.
Semua query SQL harus melalui layer ini agar konsisten.
"""

import re
from datetime import datetime
from typing import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import utc_now_naive
from app.db.models import AlertRecord, AlertSnapshot, AppSetting, CameraRecord
from app.models.schemas import (
    MODE_FOTO_TELEGRAM,
    AlertCreate,
    CameraCreate,
    CameraUpdate,
    TelegramSettings,
)

# Nomor kamera tertinggi yang pernah dipakai. Disimpan di app_settings karena harus
# bertahan walaupun semua kamera dihapus, dan tabel itu sudah ada di setiap database.
KUNCI_NOMOR_KAMERA = "camera_last_number"

# Pengaturan Telegram yang bisa diubah dari dashboard.
KUNCI_TG_FOTO = "telegram_photo_mode"
KUNCI_TG_LATIHAN = "telegram_send_drills"
KUNCI_TG_KAMERA = "telegram_camera_offline"
# Menit tanpa "Saya ke sana" sebelum alarm dieskalasi (banner dan pengingat Telegram).
KUNCI_ESKALASI = "eskalasi_menit"
KUNCI_POLA_SHIFT = "pola_shift"
ESKALASI_BAWAAN = 2


def _nomor_kamera(camera_id: str) -> int:
    """Angka di dalam id seperti cam-07. Id berbentuk lain dihitung 0."""
    cocok = re.fullmatch(r"cam-(\d+)", camera_id)
    return int(cocok.group(1)) if cocok else 0


class AlertRepository:
    """Repository untuk operasi CRUD tabel alerts."""
    
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_alert(self, data: AlertCreate, foto: bytes | None = None) -> AlertRecord:
        """Buat record alert baru, beserta foto kejadiannya bila ada, dalam satu transaksi."""
        db_obj = AlertRecord(
            camera_id=data.camera_id,
            camera_name=data.camera_name,
            severity=data.severity.value,
            message=data.message,
            fall_duration=data.fall_duration,
            simulated=data.simulated,
            threshold_sec=data.threshold_sec,
            detection_mode=data.detection_mode,
            telegram_status=data.telegram_status,
            klip_status=data.klip_status,
        )
        self.session.add(db_obj)
        if foto:
            await self.session.flush()      # butuh id alert untuk baris fotonya
            self.session.add(AlertSnapshot(alert_id=db_obj.id, jpeg=foto))
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
        """Ambil semua kamera terdaftar, urut berdasarkan id (cam-01, cam-02, ...).

        Panjang id dibandingkan lebih dulu, supaya cam-100 tetap sesudah cam-99.
        """
        stmt = select(CameraRecord).order_by(func.length(CameraRecord.id), CameraRecord.id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_camera(self, camera_id: str) -> CameraRecord | None:
        """Ambil satu kamera berdasarkan id."""
        return await self.session.get(CameraRecord, camera_id)

    async def count(self) -> int:
        """Jumlah kamera terdaftar."""
        result = await self.session.execute(select(CameraRecord.id))
        return len(result.scalars().all())

    async def _nomor_tertinggi(self) -> int:
        """Nomor kamera tertinggi yang pernah dipakai.

        Kamera dan alert ikut diperiksa untuk database lama yang belum punya penanda:
        nomor yang masih dirujuk riwayatnya tidak boleh terpakai lagi.
        """
        penanda = await self.session.get(AppSetting, KUNCI_NOMOR_KAMERA)
        kamera = (await self.session.execute(select(CameraRecord.id))).scalars().all()
        alert = (await self.session.execute(select(AlertRecord.camera_id).distinct())).scalars().all()
        return max([
            int(penanda.value) if penanda else 0,
            *map(_nomor_kamera, kamera),
            *map(_nomor_kamera, alert),
        ])

    async def create_camera(self, data: CameraCreate, camera_id: str | None = None) -> CameraRecord:
        """Daftarkan kamera baru. Tanpa camera_id, dipakai nomor berikutnya: cam-01, cam-02, dst.

        Nomor yang pernah dipakai tidak dipakai lagi, walaupun kameranya sudah dihapus.
        Alert merujuk kamera lewat id ini, jadi nomor yang didaur ulang membuat kejadian
        lama seolah terjadi di ruang yang baru.
        """
        tertinggi = await self._nomor_tertinggi()
        camera_id = camera_id or f"cam-{tertinggi + 1:02d}"
        db_obj = CameraRecord(
            id=camera_id,
            name=data.name,
            source=data.source,
            rotate=data.rotate,
            enabled=data.enabled,
            privasi=data.privasi,
        )
        self.session.add(db_obj)
        # Ditulis dalam transaksi yang sama dengan kameranya.
        await self.session.merge(AppSetting(
            key=KUNCI_NOMOR_KAMERA,
            value=str(max(tertinggi, _nomor_kamera(camera_id))),
        ))
        await self.session.commit()
        await self.session.refresh(db_obj)
        return db_obj

    async def update_camera(self, camera_id: str, data: CameraUpdate) -> CameraRecord | None:
        """Ubah sebagian field kamera. Field yang None dibiarkan apa adanya."""
        record = await self.session.get(CameraRecord, camera_id)
        if record is None:
            return None
        for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
            # 0 di letak denah berarti dikeluarkan dari denah.
            if field in ("denah_baris", "denah_kolom") and value == 0:
                value = None
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


class SettingRepository:
    """Pengaturan kunci-nilai yang bertahan setelah backend di-restart."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def semua(self) -> dict[str, str]:
        hasil = await self.session.execute(select(AppSetting))
        return {r.key: r.value for r in hasil.scalars().all()}

    async def ambil(self, key: str) -> str | None:
        baris = await self.session.get(AppSetting, key)
        return baris.value if baris is not None else None

    async def simpan(self, key: str, value: str) -> None:
        """Tulis nilai baru, buat barisnya kalau belum ada."""
        baris = await self.session.get(AppSetting, key)
        if baris is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            baris.value = value
        await self.session.commit()

    async def eskalasi_menit(self) -> int:
        nilai = await self.ambil(KUNCI_ESKALASI)
        try:
            return max(1, int(nilai)) if nilai else ESKALASI_BAWAAN
        except ValueError:
            return ESKALASI_BAWAAN

    async def telegram(self) -> TelegramSettings:
        """Pengaturan Telegram tersimpan, dengan bawaan yang aman bila belum pernah diubah."""
        s = await self.semua()
        foto = s.get(KUNCI_TG_FOTO)
        return TelegramSettings(
            photo_mode=foto if foto in MODE_FOTO_TELEGRAM else "buram",
            send_drills=s.get(KUNCI_TG_LATIHAN) == "1",
            camera_offline=s.get(KUNCI_TG_KAMERA, "1") == "1",
        )

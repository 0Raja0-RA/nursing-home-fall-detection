"""
eskalasi.py
===========
Alarm yang dibiarkan tanpa respons tidak boleh mati diam-diam.

Bila belum ada yang menekan "Saya ke sana" setelah N menit (Pengaturan, bawaan 2),
grup Telegram menerima pengingat sebagai balasan ke pesan alarmnya. Dipakai pesan baru,
bukan suntingan, karena suntingan tidak memunculkan notifikasi di HP. Pengingat diulang
setiap N menit, paling banyak MAKS_PENGINGAT kali. Banner dashboard menulis "Belum ada
yang merespons" beserta lamanya, dihitung sendiri oleh dashboard dari N yang sama.

Hanya alarm yang pesan Telegram-nya terkirim yang diberi pengingat. Tanpa pesan asal,
tidak ada tombol yang bisa ditekan dari Telegram, dan latihan yang tidak dikirim ke grup
juga tidak diingatkan.
"""

import asyncio
import html
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select

from app.core.logging import get_logger, utc_now_naive
from app.db.models import AlertRecord

log = get_logger("app.services.eskalasi")

MAKS_PENGINGAT = 3
JEDA_PERIKSA = 10.0
JEDA_SETELAH_GAGAL = 60.0       # supaya Telegram yang sedang putus tidak dihujani percobaan

_gagal_terakhir: dict[int, float] = {}


def jatuh_tempo(alert: AlertRecord, sekarang: datetime, menit: int) -> bool:
    """Apakah alert ini sudah waktunya menerima pengingat berikutnya."""
    if alert.acknowledged or alert.claimed_by:
        return False
    if alert.telegram_status != "terkirim" or not alert.telegram_message_id:
        return False
    ke = alert.eskalasi_ke or 0
    if ke >= MAKS_PENGINGAT:
        return False
    return sekarang - alert.created_at >= timedelta(minutes=menit * (ke + 1))


def _lama(detik: float) -> str:
    menit = int(detik // 60)
    return f"{menit} mnt" if menit < 60 else f"{menit // 60} jam {menit % 60} mnt"


def susun_pengingat(alert: AlertRecord, sekarang: datetime) -> str:
    from app.services.notification_service import _jam

    nama = html.escape(alert.camera_name or alert.camera_id)
    awalan = "🧪 LATIHAN · " if alert.simulated else ""
    return (f"{awalan}🔴 <b>Belum ada yang merespons · {_lama((sekarang - alert.created_at).total_seconds())}</b>\n"
            f"Kemungkinan jatuh, {nama}, sejak {_jam(alert.created_at)}.\n"
            "Tekan <b>Saya ke sana</b> di pesan alarm yang dibalas ini.")


async def putaran(sekarang: Optional[datetime] = None) -> list[int]:
    """Satu putaran: kirim pengingat yang jatuh tempo. Returns: id alert yang diingatkan."""
    from app.db.database import get_session_factory
    from app.db.repository import SettingRepository
    from app.models.schemas import WSMessage
    from app.services import notification_service as ns
    from app.services.insiden_service import alert_ke_dict
    from app.websocket.ws_manager import manager

    if not ns.dikonfigurasi():
        return []
    sekarang = sekarang or utc_now_naive()
    factory = get_session_factory()
    async with factory() as db:
        menit = await SettingRepository(db).eskalasi_menit()
        kandidat = (await db.execute(
            select(AlertRecord).where(
                or_(AlertRecord.acknowledged.is_(False), AlertRecord.acknowledged.is_(None)),
                AlertRecord.claimed_by.is_(None),
                AlertRecord.telegram_status == "terkirim",
                AlertRecord.telegram_message_id.is_not(None),
                func.coalesce(AlertRecord.eskalasi_ke, 0) < MAKS_PENGINGAT,
                AlertRecord.created_at <= sekarang - timedelta(minutes=menit),
            )
        )).scalars().all()
        tugas = [(a.id, a.telegram_message_id, susun_pengingat(a, sekarang))
                 for a in kandidat if jatuh_tempo(a, sekarang, menit)
                 and time.monotonic() - _gagal_terakhir.get(a.id, float("-inf")) >= JEDA_SETELAH_GAGAL]

    diingatkan = []
    for alert_id, message_id, teks in tugas:
        if not await ns.kirim_teks(teks, label=f"pengingat alert #{alert_id}", balas_ke=message_id):
            _gagal_terakhir[alert_id] = time.monotonic()
            continue
        _gagal_terakhir.pop(alert_id, None)
        async with factory() as db:
            alert = await db.get(AlertRecord, alert_id)
            if alert is None:
                continue
            alert.eskalasi_ke = (alert.eskalasi_ke or 0) + 1
            alert.eskalasi_terakhir = utc_now_naive()
            await db.commit()
            await db.refresh(alert)
            data = alert_ke_dict(alert)
        log.info(f"🔴 Alert #{alert_id} belum direspons, pengingat ke-{data['eskalasi_ke']} terkirim")
        await manager.broadcast(WSMessage(event="alert_update", data=data))
        diingatkan.append(alert_id)
    return diingatkan


async def jalankan_eskalasi() -> None:
    """Pekerja latar. Berhenti hanya saat task-nya dibatalkan (backend dimatikan)."""
    while True:
        await asyncio.sleep(JEDA_PERIKSA)
        try:
            await putaran()
        except asyncio.CancelledError:
            raise
        except Exception as e:      # pekerja yang tersendat tidak boleh menjatuhkan backend
            log.info(f"⚠️  Pemeriksa eskalasi tersendat: {e}")

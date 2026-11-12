"""
mode_perawatan.py
=================
Mode perawatan: jeda deteksi jatuh di satu kamera untuk sementara, misalnya saat
penghuni dimandikan atau kamarnya dibersihkan.

- Selalu manual dan selalu berbatas waktu (paling lama MAKS_MENIT). Sesudah itu
  pemantauan kembali sendiri. Tidak ada jeda otomatis sesudah alarm ditutup.
- Selama jeda, model tidak dijalankan, video tidak ditayangkan, dan tidak ada gambar
  yang masuk ke penyangga klip, karena jeda biasanya dipakai saat perawatan pribadi.
- Alarm yang sudah terbuka tidak ikut tertutup.
- Setiap jeda tercatat di tabel jeda_kamera, dan grup Telegram dikabari bila kabar
  kamera dinyalakan di Pengaturan, supaya tidak ada ruang yang diam-diam tidak dipantau.
- Jeda yang masih berjalan dimuat lagi saat backend menyala.
"""

import asyncio
import html
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, utc_now_naive
from app.db.models import JedaKamera
from app.runtime.registry import registry

log = get_logger("app.services.mode_perawatan")

MAKS_MENIT = 120


@dataclass
class JedaAktif:
    id: int
    sampai: datetime        # UTC tanpa zona, seperti kolom waktu lain
    oleh: str


def aktif(camera_id: str, sekarang: Optional[datetime] = None) -> Optional[JedaAktif]:
    """Jeda yang sedang berjalan di kamera ini, atau None."""
    jeda = registry.jeda.get(camera_id)
    if jeda is None or (sekarang or utc_now_naive()) >= jeda.sampai:
        return None
    return jeda


def kedaluwarsa(camera_id: str) -> bool:
    """Dipanggil pipeline: lepaskan jeda yang waktunya habis. True bila baru saja habis."""
    jeda = registry.jeda.get(camera_id)
    if jeda is not None and utc_now_naive() >= jeda.sampai:
        registry.jeda.pop(camera_id, None)
        return True
    return False


def _hentikan_alur(camera_id: str) -> None:
    """Hitungan berbaring dan latihan yang sedang berjalan tidak dibawa ke masa jeda."""
    fsm = registry.state_machines.get(camera_id)
    if fsm is not None:
        fsm.reset()
    registry.simulasi_sampai.pop(camera_id, None)


async def mulai(db: AsyncSession, camera_id: str, nama_kamera: str, menit: int, oleh: str) -> JedaAktif:
    """Mulai Mode perawatan, atau perpanjang yang sedang berjalan sebanyak `menit`.

    Sisa jeda tidak pernah lebih dari MAKS_MENIT dihitung dari sekarang.
    """
    sekarang = utc_now_naive()
    batas = sekarang + timedelta(minutes=MAKS_MENIT)
    jeda = aktif(camera_id, sekarang)
    if jeda is not None:
        baris = await db.get(JedaKamera, jeda.id)
        jeda.sampai = min(jeda.sampai + timedelta(minutes=menit), batas)
        if baris is not None:
            baris.sampai = jeda.sampai
        await db.commit()
        log.info(f"[{camera_id}] ⏸ Mode perawatan diperpanjang sampai {jeda.sampai:%H:%M} UTC oleh {oleh}")
        _kabari(f"⏸ <b>Mode perawatan diperpanjang</b>\n{html.escape(nama_kamera)} tidak dipantau sampai "
                f"{_jam(jeda.sampai)}. Diperpanjang oleh {html.escape(oleh)}.")
        return jeda

    sampai = min(sekarang + timedelta(minutes=menit), batas)
    baris = JedaKamera(camera_id=camera_id, camera_name=nama_kamera, mulai=sekarang, sampai=sampai, oleh=oleh)
    db.add(baris)
    await db.commit()
    jeda = JedaAktif(id=baris.id, sampai=sampai, oleh=oleh)
    registry.jeda[camera_id] = jeda
    _hentikan_alur(camera_id)
    log.info(f"[{camera_id}] ⏸ Mode perawatan {menit} menit oleh {oleh}")
    _kabari(f"⏸ <b>Mode perawatan</b>\n{html.escape(nama_kamera)} tidak dipantau sampai {_jam(sampai)} "
            f"({menit} menit), dimulai {html.escape(oleh)}.\nJatuh di ruang ini tidak terdeteksi selama jeda.")
    return jeda


async def akhiri(db: AsyncSession, camera_id: str, nama_kamera: str, oleh: str, kabari: bool = True) -> bool:
    """Hentikan jeda lebih awal. False bila kamera ini tidak sedang dijeda."""
    jeda = registry.jeda.pop(camera_id, None)
    if jeda is None:
        return False
    baris = await db.get(JedaKamera, jeda.id)
    sekarang = utc_now_naive()
    if baris is not None and baris.selesai is None and sekarang < baris.sampai:
        baris.selesai = sekarang
        baris.diakhiri_oleh = oleh
        await db.commit()
    _hentikan_alur(camera_id)
    log.info(f"[{camera_id}] ▶ Mode perawatan dihentikan oleh {oleh}")
    if kabari:
        _kabari(f"▶️ <b>{html.escape(nama_kamera)} dipantau lagi</b>\nMode perawatan dihentikan "
                f"{html.escape(oleh)}.")
    return True


async def muat_dari_db(db: AsyncSession) -> None:
    """Saat backend menyala: pulihkan jeda yang belum habis."""
    sekarang = utc_now_naive()
    baris = (await db.execute(
        select(JedaKamera).where(JedaKamera.selesai.is_(None), JedaKamera.sampai > sekarang)
    )).scalars().all()
    for b in baris:
        registry.jeda[b.camera_id] = JedaAktif(id=b.id, sampai=b.sampai, oleh=b.oleh or "")
    if baris:
        log.info(f"⏸ Mode perawatan dipulihkan untuk {', '.join(b.camera_id for b in baris)}")


def kabari_habis(camera_id: str) -> None:
    """Dipanggil pipeline saat jeda habis dengan sendirinya."""
    log.info(f"[{camera_id}] ▶ Mode perawatan selesai, pemantauan berjalan lagi")

    async def kirim() -> None:
        nama = await _nama_kamera(camera_id)
        await _kirim(f"▶️ <b>{html.escape(nama)} dipantau lagi</b>\nMode perawatan selesai.")

    _jalankan(kirim())


# ---- Telegram ------------------------------------------------------------------

_tugas: set[asyncio.Task] = set()


def _jalankan(coro) -> None:
    tugas = asyncio.create_task(coro)
    _tugas.add(tugas)
    tugas.add_done_callback(_tugas.discard)


def _kabari(teks: str) -> None:
    _jalankan(_kirim(teks))


def _jam(utc_naive: datetime) -> str:
    from app.services.notification_service import _jam as jam
    return jam(utc_naive)


async def _nama_kamera(camera_id: str) -> str:
    from app.db.database import get_session_factory
    from app.db.repository import CameraRepository

    async with get_session_factory()() as db:
        record = await CameraRepository(db).get_camera(camera_id)
    return record.name if record and record.name else camera_id


async def _kirim(teks: str) -> None:
    """Kirim ke grup bila Telegram diatur dan kabar kamera dinyalakan. Gagal kirim
    hanya dicatat: jeda tetap berlaku dan tetap terlihat di dashboard."""
    from app.db.database import get_session_factory
    from app.db.repository import SettingRepository
    from app.services import notification_service as ns

    try:
        if not ns.dikonfigurasi():
            return
        async with get_session_factory()() as db:
            if not (await SettingRepository(db).telegram()).camera_offline:
                return
        await ns.kirim_teks(teks, label="mode perawatan")
    except Exception as e:      # kabar yang gagal tidak boleh mengganggu pipeline
        log.info(f"Kabar Mode perawatan gagal dikirim: {e}")

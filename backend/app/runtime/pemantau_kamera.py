"""
pemantau_kamera.py
==================
Kabari grup Telegram saat kamera berhenti mengirim gambar, dan saat pulih.

Kamera yang buta berarti jatuh di ruang itu tidak terdeteksi, dan dashboard yang
tidak sedang dibuka tidak memberi tahu siapa pun. Pesan ini menutup celah itu.

- Baru dikabarkan setelah CAMERA_OFFLINE_NOTIFY_SEC (bawaan 30 detik) tanpa gambar,
  supaya kamera yang sekadar dinyalakan ulang dari Daftar Kamera tidak memicu pesan.
- Beberapa kamera yang putus atau pulih dalam satu putaran dikelompokkan dalam
  satu pesan, supaya grup tidak dibanjiri saat WiFi seluruh gedung terputus.
- Kamera yang sengaja dimatikan (enabled = false) tidak dipantau.
- Bisa dimatikan dari halaman Pengaturan.
"""

import asyncio
import html
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger, utc_now_naive

log = get_logger("app.runtime.pemantau_kamera")

JEDA_PERIKSA = 10.0


@dataclass
class _Keadaan:
    putus_sejak: Optional[datetime] = None
    dikabari: bool = False


@dataclass
class Perubahan:
    putus: list[tuple[str, datetime]] = field(default_factory=list)   # (nama, sejak)
    pulih: list[str] = field(default_factory=list)


def periksa(kamera: list[tuple[str, str]], mengalir: dict[str, bool],
            frame_terakhir: dict[str, Optional[datetime]], keadaan: dict[str, _Keadaan],
            sekarang: datetime, ambang: float) -> Perubahan:
    """Satu putaran pemeriksaan. Murni, supaya bisa diuji tanpa kamera dan tanpa jam.

    Args:
        kamera: (camera_id, nama) untuk setiap kamera yang enabled.
        mengalir: camera_id -> sedang mengirim gambar.
        frame_terakhir: camera_id -> jam frame terakhir, None kalau belum pernah.
        keadaan: diubah di tempat; menyimpan sejak kapan tiap kamera putus.
    """
    hasil = Perubahan()
    ada = set()
    for camera_id, nama in kamera:
        ada.add(camera_id)
        k = keadaan.setdefault(camera_id, _Keadaan())
        if mengalir.get(camera_id):
            if k.dikabari:
                hasil.pulih.append(nama)
            keadaan[camera_id] = _Keadaan()
            continue
        if k.putus_sejak is None:
            k.putus_sejak = frame_terakhir.get(camera_id) or sekarang
        if not k.dikabari and sekarang - k.putus_sejak >= timedelta(seconds=ambang):
            k.dikabari = True
            hasil.putus.append((nama, k.putus_sejak))
    for camera_id in list(keadaan):
        if camera_id not in ada:          # kamera dihapus atau dimatikan
            del keadaan[camera_id]
    return hasil


def susun_pesan(p: Perubahan) -> str:
    from app.services.notification_service import _jam

    bagian = []
    if p.putus:
        baris = "\n".join(f"• {html.escape(n)}, sejak {_jam(s)}" for n, s in p.putus)
        bagian.append(f"📷 <b>Kamera terputus</b>\n{baris}\n"
                      "Jatuh di ruang ini tidak terdeteksi sampai kamera pulih.")
    if p.pulih:
        baris = "\n".join(f"• {html.escape(n)}" for n in p.pulih)
        bagian.append(f"✅ <b>Kamera pulih</b>\n{baris}")
    return "\n\n".join(bagian)


async def _putaran(keadaan: dict[str, _Keadaan]) -> None:
    from app.db.database import get_session_factory
    from app.db.models import CameraRecord
    from app.db.repository import SettingRepository
    from app.runtime.registry import registry
    from app.services import notification_service as ns
    from sqlalchemy import select

    async with get_session_factory()() as db:
        baris = (await db.execute(
            select(CameraRecord.id, CameraRecord.name).where(CameraRecord.enabled.is_(True))
        )).all()
        aktif = (await SettingRepository(db).telegram()).camera_offline

    mengalir, frame = {}, {}
    for camera_id, _ in baris:
        cam = registry.cameras.get(camera_id)
        mengalir[camera_id] = bool(cam and cam.sedang_mengalir)
        frame[camera_id] = cam.waktu_frame_terakhir if cam else None

    perubahan = periksa(list(baris), mengalir, frame, keadaan, utc_now_naive(),
                        get_settings().CAMERA_OFFLINE_NOTIFY_SEC)
    if not (perubahan.putus or perubahan.pulih):
        return
    for nama, sejak in perubahan.putus:
        log.info(f"📷 {nama} terputus sejak {sejak:%H:%M:%S} UTC")
    for nama in perubahan.pulih:
        log.info(f"📷 {nama} pulih")
    if aktif and ns.dikonfigurasi():
        await ns.kirim_teks(susun_pesan(perubahan), label="kabar kamera")


async def jalankan_pemantau() -> None:
    """Loop pemantau. Berhenti hanya saat task-nya dibatalkan (backend dimatikan)."""
    keadaan: dict[str, _Keadaan] = {}
    while True:
        await asyncio.sleep(JEDA_PERIKSA)
        try:
            await _putaran(keadaan)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.info(f"⚠️  Pemantau kamera tersendat: {e}")

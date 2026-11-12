"""
klip.py
=======
Klip beberapa detik sebelum dan sesudah alarm, sebagai bukti di Riwayat Insiden.

Foto kejadian hanya menunjukkan satu saat, yaitu saat alarm berbunyi, ketika orangnya
sudah tergeletak beberapa detik. Klip menunjukkan bagaimana ia sampai di lantai,
sehingga perawat bisa menilai alarm palsu dengan lebih yakin.

Cara kerja:
- Pipeline tiap kamera menitipkan frame beranotasi yang sudah diperkecil, paling banyak
  FPS frame per detik, ke penyangga di memori yang memuat BUFFER_DETIK detik terakhir.
- Saat alarm, rekam() menunggu DETIK_SESUDAH detik, lalu memotong penyangga mulai
  JEDA_SEBELUM_TERGELETAK detik sebelum orangnya terbaca tergeletak, sampai DETIK_SESUDAH
  detik sesudah alarm. Hasilnya satu berkas ZIP berisi JPEG di KLIP_DIR.
- Klip dihapus otomatis setelah KLIP_MASA_SIMPAN_HARI hari. Nilai 0 mematikan perekaman
  dan menghapus klip yang ada.

Klip tidak pernah dikirim ke Telegram.

Status klip di kolom alerts.klip_status:
    merekam    menunggu detik-detik sesudah alarm
    tersimpan  berkasnya ada
    kosong     kamera tidak mengirim gambar di sekitar kejadian
    gagal      berkas tidak bisa ditulis
    dihapus    lewat masa simpan
    NULL       alert dari sebelum fitur ini ada, atau perekaman dimatikan
"""

import asyncio
import base64
import json
import time
import zipfile
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("app.services.klip")

FPS = 4.0                       # cukup untuk melihat gerak jatuh, ringan di memori
BUFFER_DETIK = 30.0
DETIK_SESUDAH = 5.0
JEDA_SEBELUM_TERGELETAK = 5.0   # gerak jatuhnya terjadi sebelum timer mulai
DETIK_SEBELUM_MAKS = 20.0       # sisakan ruang di penyangga untuk DETIK_SESUDAH
LEBAR = 640
MUTU = 70


def aktif() -> bool:
    return get_settings().KLIP_MASA_SIMPAN_HARI > 0


def folder() -> Path:
    setelan = Path(get_settings().KLIP_DIR)
    if setelan.is_absolute():
        return setelan
    return Path(__file__).resolve().parents[2] / setelan


def jalur(alert_id: int) -> Path:
    return folder() / f"alert-{alert_id}.zip"


class PenyanggaKlip:
    """Frame beberapa detik terakhir per kamera, sebagai (waktu epoch, JPEG kecil)."""

    def __init__(self) -> None:
        self._frame: dict[str, deque[tuple[float, bytes]]] = {}
        self._terakhir: dict[str, float] = {}

    def perlu_frame(self, camera_id: str, waktu: float) -> bool:
        """Apakah frame pada waktu ini perlu disimpan. Membatasi ke FPS frame per detik."""
        return aktif() and waktu - self._terakhir.get(camera_id, float("-inf")) >= 1.0 / FPS

    def tambah(self, camera_id: str, waktu: float, jpeg: bytes) -> None:
        self._terakhir[camera_id] = waktu
        antre = self._frame.setdefault(camera_id, deque())
        antre.append((waktu, jpeg))
        while antre and waktu - antre[0][0] > BUFFER_DETIK:
            antre.popleft()

    def potong(self, camera_id: str, dari: float, sampai: float) -> list[tuple[float, bytes]]:
        return [(t, j) for t, j in self._frame.get(camera_id, ()) if dari <= t <= sampai]

    def lupakan(self, camera_id: str) -> None:
        self._frame.pop(camera_id, None)
        self._terakhir.pop(camera_id, None)


penyangga = PenyanggaKlip()


# ---- Berkas -------------------------------------------------------------------

def tulis_berkas(alert_id: int, frame: list[tuple[float, bytes]], waktu_alarm: float,
                 detik_tergeletak: float) -> None:
    """Tulis ZIP berisi JPEG dan klip.json. Ditulis ke berkas sementara dulu, supaya
    pembaca tidak pernah mendapat berkas setengah jadi."""
    tujuan = jalur(alert_id)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    sementara = tujuan.with_suffix(".tmp")
    meta = {"alert_id": alert_id, "detik_tergeletak": round(detik_tergeletak, 2), "frame": []}
    with zipfile.ZipFile(sementara, "w", zipfile.ZIP_STORED) as z:   # JPEG sudah terkompresi
        for i, (t, jpeg) in enumerate(frame):
            nama = f"{i:03d}.jpg"
            z.writestr(nama, jpeg)
            meta["frame"].append({"nama": nama, "t": round(t - waktu_alarm, 2)})
        z.writestr("klip.json", json.dumps(meta))
    sementara.replace(tujuan)


def baca_berkas(alert_id: int) -> Optional[dict]:
    """Isi klip untuk dashboard: waktu tiap frame relatif terhadap alarm, dan JPEG base64."""
    berkas = jalur(alert_id)
    if not berkas.is_file():
        return None
    with zipfile.ZipFile(berkas) as z:
        meta = json.loads(z.read("klip.json"))
        frame = [{"t": f["t"], "jpeg": base64.b64encode(z.read(f["nama"])).decode("ascii")}
                 for f in meta["frame"]]
    disimpan = datetime.fromtimestamp(berkas.stat().st_mtime, timezone.utc)
    return {
        "detik_tergeletak": meta["detik_tergeletak"],
        "frame": frame,
        "dihapus_pada": (disimpan + timedelta(days=get_settings().KLIP_MASA_SIMPAN_HARI)).isoformat(),
    }


def hapus_kedaluwarsa(sekarang: Optional[float] = None) -> list[int]:
    """Hapus klip yang melewati masa simpan (semua klip bila perekaman dimatikan).

    Returns: id alert yang klipnya dihapus.
    """
    tempat = folder()
    if not tempat.is_dir():
        return []
    batas = (time.time() if sekarang is None else sekarang) - get_settings().KLIP_MASA_SIMPAN_HARI * 86400
    dihapus = []
    for berkas in tempat.glob("alert-*.*"):
        if berkas.stat().st_mtime >= batas and aktif():
            continue
        berkas.unlink(missing_ok=True)
        if berkas.suffix == ".zip":
            try:
                dihapus.append(int(berkas.stem.removeprefix("alert-")))
            except ValueError:
                pass
    return dihapus


# ---- Merekam dan memperbarui status -------------------------------------------

async def _catat(alert_ids: list[int], status: str, detik: Optional[float] = None) -> None:
    """Simpan status klip dan kabari dashboard. Pesan Telegram tidak ikut disunting."""
    from app.db.database import get_session_factory
    from app.db.models import AlertRecord
    from app.models.schemas import WSMessage
    from app.services.insiden_service import alert_ke_dict
    from app.websocket.ws_manager import manager

    async with get_session_factory()() as session:
        for alert_id in alert_ids:
            alert = await session.get(AlertRecord, alert_id)
            if alert is None:
                continue
            alert.klip_status = status
            if detik is not None:
                alert.klip_detik = detik
            await session.commit()
            await session.refresh(alert)
            await manager.broadcast(WSMessage(event="alert_update", data=alert_ke_dict(alert)))


_tugas: set[asyncio.Task] = set()     # rujukan supaya tugasnya tidak dibuang pengumpul sampah


def mulai_rekam(alert_id: int, camera_id: str, waktu_alarm: float, detik_tergeletak: float) -> None:
    tugas = asyncio.create_task(rekam(alert_id, camera_id, waktu_alarm, detik_tergeletak))
    _tugas.add(tugas)
    tugas.add_done_callback(_tugas.discard)


async def rekam(alert_id: int, camera_id: str, waktu_alarm: float, detik_tergeletak: float,
                tunggu: float = DETIK_SESUDAH + 0.5) -> None:
    """Dipanggil sesudah alert tersimpan dengan klip_status "merekam".

    `tunggu`: beri waktu frame sesudah alarm masuk ke penyangga. Tes memakai 0.
    """
    sebelum = min(detik_tergeletak + JEDA_SEBELUM_TERGELETAK, DETIK_SEBELUM_MAKS)
    await asyncio.sleep(tunggu)
    frame = penyangga.potong(camera_id, waktu_alarm - sebelum, waktu_alarm + DETIK_SESUDAH)
    if not frame:
        log.info(f"[{camera_id}] Klip alert #{alert_id} kosong: tidak ada gambar di sekitar kejadian.")
        await _catat([alert_id], "kosong")
        return
    try:
        await asyncio.to_thread(tulis_berkas, alert_id, frame, waktu_alarm, detik_tergeletak)
    except OSError as e:
        log.info(f"[{camera_id}] Klip alert #{alert_id} gagal ditulis: {e}")
        await _catat([alert_id], "gagal")
        return
    detik = round(frame[-1][0] - frame[0][0], 1)
    log.info(f"[{camera_id}] Klip alert #{alert_id} tersimpan: {len(frame)} frame, {detik} detik.")
    await _catat([alert_id], "tersimpan", detik)


async def bersihkan() -> None:
    dihapus = await asyncio.to_thread(hapus_kedaluwarsa)
    if dihapus:
        log.info(f"Klip dihapus karena melewati masa simpan: alert {', '.join(map(str, sorted(dihapus)))}")
        await _catat(dihapus, "dihapus")


async def jalankan_pembersih(jeda: float = 3600.0) -> None:
    """Pekerja latar: hapus klip kedaluwarsa saat backend menyala, lalu setiap jam."""
    while True:
        try:
            await bersihkan()
        except Exception as e:      # pembersih yang gagal tidak boleh menjatuhkan backend
            log.info(f"Pembersih klip gagal: {e}")
        await asyncio.sleep(jeda)

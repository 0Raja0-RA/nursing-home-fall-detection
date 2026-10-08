"""
local_devices.py
================
Mendaftar kamera yang terpasang langsung di komputer ini, lengkap dengan namanya.

OpenCV hanya menerima kamera lokal sebagai angka indeks (`0`, `1`, `2`, ...) dan
tidak punya cara menanyakan nama perangkatnya. Begitu ada lebih dari satu kamera
-- apalagi dengan Iriun yang memasang empat perangkat virtual sekaligus -- tidak
ada yang tahu indeks berapa milik HP siapa. Modul ini menjembatani angka itu ke
nama yang bisa dibaca manusia.

Cara utamanya memakai ffmpeg, karena ffmpeg membaca daftar perangkat DirectShow
dengan urutan yang sama seperti yang dipakai OpenCV pada backend CAP_DSHOW. Kalau
ffmpeg tidak ada, modul jatuh ke cara cadangan: mencoba membuka beberapa indeks
pertama dan melaporkannya tanpa nama.
"""

import re
import shutil
import subprocess
import sys

from app.core.logging import get_logger
from app.models.schemas import LocalDevice

log = get_logger("app.services.local_devices")

# Baris keluaran ffmpeg: [dshow @ 000001...] "HD Webcam" (video)
_BARIS_DSHOW = re.compile(r'"([^"]+)"\s*\(video\)', re.IGNORECASE)

# Iriun memasang perangkat bernama "Iriun Webcam", "Iriun Webcam #2", dan seterusnya.
# Aplikasi di layar menyebutnya Camera #1 sampai Camera #4, jadi penamaan di sini
# mengikuti aplikasinya supaya cocok dengan tab yang dilihat pengguna.
_IRIUN = re.compile(r"^Iriun\s+Webcam(?:\s*#\s*(\d+))?\s*$", re.IGNORECASE)

# Berapa indeks yang dicoba saat ffmpeg tidak tersedia.
BATAS_PROBE = 6


def _label(nama: str) -> tuple[str, str | None]:
    """Ubah nama perangkat mentah menjadi label tampilan + nama driver."""
    cocok = _IRIUN.match(nama)
    if cocok:
        nomor = int(cocok.group(1) or 1)
        return f"Camera #{nomor}", "Iriun"
    return nama, None


def _daftar_ffmpeg() -> list[str] | None:
    """Nama perangkat video menurut ffmpeg, urut sesuai DirectShow.

    Mengembalikan None kalau ffmpeg tidak ada atau tidak bisa dibaca, supaya
    pemanggil tahu harus memakai cara cadangan.
    """
    if not sys.platform.startswith("win"):
        return None
    if shutil.which("ffmpeg") is None:
        return None

    try:
        # ffmpeg menulis daftar perangkat ke stderr lalu keluar dengan kode error;
        # itu perilaku normal untuk -list_devices, bukan tanda kegagalan.
        proses = subprocess.run(
            ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.info(f"ffmpeg gagal dijalankan untuk mendaftar perangkat: {e}")
        return None

    nama = _BARIS_DSHOW.findall(proses.stderr or "")
    return nama or None


def _daftar_probe() -> list[str | None]:
    """Cara cadangan: coba buka beberapa indeks pertama, tanpa nama.

    Hanya dipakai kalau ffmpeg tidak ada. Membuka perangkat kamera itu lambat,
    jadi jumlah indeks yang dicoba sengaja dibatasi.
    """
    import cv2

    hasil: list[str | None] = []
    for i in range(BATAS_PROBE):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY)
        try:
            hasil.append(None if cap.isOpened() else "")
        finally:
            cap.release()
    # Buang ekor indeks yang tidak terbuka.
    while hasil and hasil[-1] == "":
        hasil.pop()
    return [h for h in hasil if h != ""]


def daftar_perangkat(sumber_terpakai: set[str] | None = None) -> list[LocalDevice]:
    """Kamera lokal yang bisa dipilih, beserta indeks yang dipakai sebagai sumber.

    Args:
        sumber_terpakai: kumpulan nilai `source` kamera yang sudah terdaftar,
            dipakai untuk menandai perangkat yang sudah dipakai.
    """
    terpakai = sumber_terpakai or set()

    nama_perangkat = _daftar_ffmpeg()
    if nama_perangkat is None:
        log.info("ffmpeg tidak tersedia; indeks kamera dideteksi tanpa nama")
        nama_perangkat = [None] * len(_daftar_probe())

    hasil: list[LocalDevice] = []
    for indeks, nama in enumerate(nama_perangkat):
        if nama:
            label, driver = _label(nama)
        else:
            label, driver = f"Kamera {indeks}", None
        hasil.append(
            LocalDevice(
                index=indeks,
                name=nama or f"Kamera {indeks}",
                label=label,
                driver=driver,
                source=str(indeks),
                in_use=str(indeks) in terpakai,
            )
        )
    return hasil

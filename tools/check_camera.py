"""
check_camera.py
===============
Memeriksa apakah sumber kamera bisa dibuka, SEBELUM backend dijalankan.

Dipanggil oleh run-backend.bat. Dibuat terpisah karena pemeriksaannya dua tahap:

1. Uji jangkauan jaringan dengan socket biasa (batas 3 detik).
   Ini penting: kalau host tidak terjangkau sama sekali -- misalnya WiFi kampus yang
   memblokir komunikasi antar-perangkat -- cv2.VideoCapture bisa menggantung sampai
   1,5 menit sebelum menyerah. Peluncur jadi terlihat macet.
2. Baru buka dengan OpenCV untuk memastikan formatnya memang bisa dibaca.

Pakai:  python tools/check_camera.py "<CAMERA_SOURCE>"
Keluar: 0 kalau kamera siap, 1 kalau tidak.
"""

import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

BATAS_JARINGAN = 3.0   # detik


def jangkau(host: str, port: int) -> tuple[bool, str]:
    """Cek apakah host:port bisa disambungi lewat TCP."""
    try:
        with socket.create_connection((host, port), timeout=BATAS_JARINGAN):
            return True, ""
    except socket.timeout:
        return False, f"tidak ada jawaban dari {host}:{port} dalam {BATAS_JARINGAN:.0f} detik"
    except socket.gaierror:
        return False, f"nama host '{host}' tidak dikenali"
    except OSError as e:
        return False, f"{host}:{port} tidak dapat dihubungi ({e.strerror or e})"


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("  [GAGAL] CAMERA_SOURCE kosong.")
        return 1

    sumber = sys.argv[1].strip()

    # Tahap 1: pemeriksaan cepat sesuai jenis sumber.
    if sumber.isdigit():
        pass                                   # webcam lokal, tidak ada yang bisa dicek cepat
    elif "://" in sumber:
        u = urlparse(sumber)
        port = u.port or (554 if u.scheme == "rtsp" else 80)
        if u.hostname:
            bisa, alasan = jangkau(u.hostname, port)
            if not bisa:
                print(f"  [GAGAL] {alasan}")
                print("          Kamera HP: pastikan aplikasi IP Webcam menyala dan alamatnya cocok.")
                print("          Kalau IP sudah benar tapi tetap gagal, jaringannya mungkin memblokir")
                print("          komunikasi antar-perangkat. Lihat bagian WiFi kampus di TESTING.md.")
                return 1
    elif not Path(sumber).exists():
        print(f"  [GAGAL] file video tidak ditemukan: {sumber}")
        return 1

    # Tahap 2: benar-benar buka dengan OpenCV.
    try:
        import cv2
    except ImportError:
        print("  [GAGAL] OpenCV belum terpasang di virtual environment.")
        return 1

    cap = cv2.VideoCapture(int(sumber) if sumber.isdigit() else sumber)
    terbuka = cap.isOpened()
    ukuran = ""
    if terbuka:
        ok, frame = cap.read()
        if ok and frame is not None:
            ukuran = f" ({frame.shape[1]}x{frame.shape[0]})"
        else:
            terbuka = False
    cap.release()

    if not terbuka:
        print("  [GAGAL] sumber terjangkau, tapi tidak menghasilkan gambar.")
        print("          Webcam: kemungkinan sedang dipakai aplikasi lain (browser, Zoom, kamera HP).")
        return 1

    print(f"  Kamera OK{ukuran}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

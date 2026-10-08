"""
overlay.py
==========
Menggambar hasil deteksi ke atas frame dan mengemasnya jadi JPEG.

Pekerjaan ini dulu dilakukan di dalam endpoint stream, artinya satu kali untuk
setiap penonton. Membuka dua halaman sekaligus berarti dua kali menggambar dan
dua kali encode JPEG untuk frame yang sama -- dan keduanya berjalan di event
loop, bukan di thread, sehingga saling berebut dengan REST, WebSocket, dan
pipeline deteksi. Gejalanya: satu halaman mengalir lancar sementara halaman lain
tampak membeku.

Sekarang pipeline yang memanggil modul ini sekali per frame, lalu hasil JPEG-nya
dibagikan ke semua penonton. Biaya penonton tambahan jadi nol.
"""

from typing import Optional

import cv2
import numpy as np

from app.models.schemas import DetectionResult, PostureClass

# Warna kotak per postur (format BGR karena OpenCV).
WARNA = {
    PostureClass.NORMAL: (80, 200, 80),            # hijau
    PostureClass.TRANSITIONAL: (0, 165, 255),      # oranye
    PostureClass.LYING_ON_GROUND: (60, 60, 230),   # merah
}
ABU = (150, 150, 150)   # dipakai saat confidence di bawah ambang


def gambar_deteksi(frame: np.ndarray, hasil: Optional[DetectionResult], ambang: float) -> np.ndarray:
    """Gambar bounding box + label ke atas frame (frame dimodifikasi di tempat).

    Deteksi dengan confidence di bawah `ambang` tetap digambar, tapi berwarna abu-abu
    dan diberi tanda "(ragu)". Ini disengaja: tanpa itu layar terlihat kosong dan kita
    tidak bisa membedakan "model tidak melihat apa pun" dari "model melihat sesuatu
    tapi kurang yakin".
    """
    if hasil is None or not hasil.bbox:
        return frame

    yakin = hasil.confidence >= ambang
    warna = WARNA.get(hasil.posture, ABU) if yakin else ABU

    x1, y1, x2, y2 = (int(v) for v in hasil.bbox)
    cv2.rectangle(frame, (x1, y1), (x2, y2), warna, 3)

    teks = f"{hasil.posture.value} {hasil.confidence:.2f}" + ("" if yakin else " (ragu)")
    (tw, th), _ = cv2.getTextSize(teks, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    atas = max(y1 - th - 10, 0)
    cv2.rectangle(frame, (x1, atas), (x1 + tw + 10, atas + th + 10), warna, -1)
    cv2.putText(frame, teks, (x1 + 5, atas + th + 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return frame


def jadikan_jpeg(frame: np.ndarray, hasil: Optional[DetectionResult], ambang: float) -> Optional[bytes]:
    """Gambar deteksi lalu kembalikan frame sebagai byte JPEG siap kirim.

    Frame disalin dulu supaya gambar yang dipakai pipeline tidak ikut tercoret.
    """
    ok, buffer = cv2.imencode(".jpg", gambar_deteksi(frame.copy(), hasil, ambang))
    return buffer.tobytes() if ok else None

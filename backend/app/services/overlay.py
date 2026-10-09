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

# Pasangan sendi yang disambung garis, urutan keypoint COCO-17:
#   0 hidung, 1-2 mata, 3-4 telinga, 5-6 bahu, 7-8 siku, 9-10 pergelangan,
#   11-12 pinggul, 13-14 lutut, 15-16 pergelangan kaki.
TULANG = [
    (5, 6), (11, 12), (5, 11), (6, 12),          # badan
    (5, 7), (7, 9), (6, 8), (8, 10),             # lengan
    (11, 13), (13, 15), (12, 14), (14, 16),      # kaki
    (0, 1), (0, 2), (1, 3), (2, 4),              # kepala
]
# Sendi di bawah ini tidak digambar. Model pose tetap mengeluarkan koordinat
# untuk sendi yang tidak terlihat (tertutup, di luar frame), dan koordinat itu
# tebakan -- kalau digambar, skeletonnya mencuat ke tempat yang tidak masuk akal.
SENDI_MIN_CONF = 0.3

# Garis yang dipakai sudut tulang belakang (bahu -> pinggul) ditebalkan, supaya
# saat demo kelihatan apa yang sebenarnya dinilai model untuk memutuskan postur.
TULANG_PENENTU = {(5, 11), (6, 12)}


def _gambar_skeleton(frame: np.ndarray, keypoints: list[list[float]], warna) -> None:
    def titik(i):
        x, y, c = keypoints[i]
        return (int(x), int(y)) if c >= SENDI_MIN_CONF else None

    for a, b in TULANG:
        pa, pb = titik(a), titik(b)
        if pa and pb:
            tebal = 4 if (a, b) in TULANG_PENENTU else 2
            cv2.line(frame, pa, pb, warna, tebal, cv2.LINE_AA)

    for i in range(len(keypoints)):
        p = titik(i)
        if p:
            cv2.circle(frame, p, 4, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, p, 4, warna, 1, cv2.LINE_AA)


def gambar_deteksi(frame: np.ndarray, hasil: Optional[DetectionResult], ambang: float) -> np.ndarray:
    """Gambar bounding box + label ke atas frame (frame dimodifikasi di tempat).

    Di mode pose, skeleton ikut digambar dengan warna yang sama dengan kotaknya.

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

    # Skeleton digambar lebih dulu supaya kotak dan labelnya tetap di atas.
    if hasil.keypoints:
        _gambar_skeleton(frame, hasil.keypoints, warna)

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

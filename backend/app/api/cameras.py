"""
cameras.py
==========
REST endpoints untuk status kamera dan video stream.

Endpoints:
    GET  /api/cameras/                — Daftar semua kamera & status terakhirnya
    GET  /api/cameras/{id}            — Status satu kamera
    GET  /api/cameras/{id}/stream     — Video MJPEG dengan bounding box tergambar
"""

import asyncio

import cv2
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.models.schemas import CameraStatus, PostureClass
from app.runtime.registry import registry

router = APIRouter()

# Warna kotak per postur (format BGR karena OpenCV).
_WARNA = {
    PostureClass.NORMAL: (80, 200, 80),            # hijau
    PostureClass.TRANSITIONAL: (0, 165, 255),      # oranye
    PostureClass.LYING_ON_GROUND: (60, 60, 230),   # merah
}
_ABU = (150, 150, 150)   # dipakai saat confidence di bawah ambang


@router.get("/", response_model=list[CameraStatus])
async def get_cameras():
    """Ambil status semua kamera yang terdaftar.

    Status diisi oleh detection_pipeline setiap frame. Kamera yang baru dinyalakan
    tapi belum menghasilkan frame tetap muncul, dengan status default.
    """
    hasil = []
    for camera_id in registry.cameras:
        status = registry.latest_status.get(camera_id)
        hasil.append(status or CameraStatus(camera_id=camera_id))
    return hasil


@router.get("/{camera_id}", response_model=CameraStatus)
async def get_camera(camera_id: str):
    """Ambil status satu kamera berdasarkan ID."""
    if camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    return registry.latest_status.get(camera_id) or CameraStatus(camera_id=camera_id)


def _gambar_deteksi(frame, camera_id: str):
    """Gambar bounding box + label dari deteksi terakhir ke atas frame.

    Kotaknya berasal dari hasil inference yang sudah dihitung detection_pipeline,
    jadi endpoint ini tidak menjalankan model lagi.

    Deteksi dengan confidence di bawah CONFIDENCE_THRESHOLD tetap digambar, tapi
    berwarna abu-abu dan diberi tanda "(ragu)". Ini disengaja: tanpa itu, layar
    terlihat kosong dan kita tidak bisa membedakan "model tidak melihat apa pun"
    dari "model melihat sesuatu tapi kurang yakin".
    """
    hasil = registry.latest_detection.get(camera_id)
    if hasil is None or not hasil.bbox:
        return frame

    settings = get_settings()
    yakin = hasil.confidence >= settings.CONFIDENCE_THRESHOLD
    warna = _WARNA.get(hasil.posture, _ABU) if yakin else _ABU

    x1, y1, x2, y2 = (int(v) for v in hasil.bbox)
    cv2.rectangle(frame, (x1, y1), (x2, y2), warna, 3)

    teks = f"{hasil.posture.value} {hasil.confidence:.2f}" + ("" if yakin else " (ragu)")
    (tw, th), _ = cv2.getTextSize(teks, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    atas = max(y1 - th - 10, 0)
    cv2.rectangle(frame, (x1, atas), (x1 + tw + 10, atas + th + 10), warna, -1)
    cv2.putText(frame, teks, (x1 + 5, atas + th + 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return frame


async def generate_frames(camera_id: str):
    """Generator MJPEG: frame terbaru dari kamera, dengan kotak deteksi tergambar."""
    camera = registry.cameras.get(camera_id)
    if not camera:
        return

    while camera_id in registry.cameras:
        frame = camera.get_latest_frame()
        if frame is not None:
            # copy() supaya gambar yang dipakai pipeline tidak ikut tercoret.
            ret, buffer = cv2.imencode(".jpg", _gambar_deteksi(frame.copy(), camera_id))
            if ret:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        await asyncio.sleep(0.03)  # ~30 fps


@router.get("/{camera_id}/stream")
async def video_stream(camera_id: str):
    """Endpoint video streaming langsung (MJPEG)."""
    if camera_id not in registry.cameras:
        raise HTTPException(status_code=404, detail="Camera not found")
    return StreamingResponse(
        generate_frames(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )

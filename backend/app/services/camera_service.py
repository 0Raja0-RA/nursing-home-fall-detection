"""
camera_service.py
=================
Capture video dari webcam lokal atau RTSP stream.

Menjalankan loop capture di background thread, mengambil frame
terbaru, dan menyediakannya untuk inference service.

Supports:
    - Webcam lokal (source="0", "1", dst.)
    - RTSP stream (source="rtsp://user:pass@ip:port/path")
    - File video untuk testing (source="path/to/video.mp4")
"""

import asyncio
import threading
import time
from typing import Optional

import cv2
import numpy as np

from app.core.config import get_settings


class CameraService:
    """Manage video capture dari satu sumber kamera.

    Attributes:
        camera_id: Identifier unik untuk kamera ini.
        source: Sumber video (index webcam, URL RTSP, atau path file).
        is_active: Apakah kamera sedang aktif menangkap frame.
    """

    def __init__(self, camera_id: str, source: Optional[str] = None):
        self.camera_id = camera_id
        settings = get_settings()
        self.source = source or settings.CAMERA_SOURCE
        self.target_fps = settings.CAMERA_FPS

        self.is_active = False
        self._capture: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._actual_fps: float = 0.0

    def start(self) -> bool:
        """Mulai capture video di background thread.

        Returns:
            True jika berhasil start, False jika gagal.
        """
        # Tentukan source: angka untuk webcam, string untuk RTSP/file
        src = int(self.source) if self.source.isdigit() else self.source

        self._capture = cv2.VideoCapture(src)
        if not self._capture.isOpened():
            print(f"❌ Gagal membuka kamera: {self.source}")
            return False

        self.is_active = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"camera-{self.camera_id}",
        )
        self._thread.start()
        print(f"📷 Camera {self.camera_id} started (source={self.source})")
        return True

    def stop(self) -> None:
        """Hentikan capture video."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        if self._capture:
            self._capture.release()
        self.is_active = False
        print(f"📷 Camera {self.camera_id} stopped")

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Ambil frame terbaru (thread-safe).

        Returns:
            Frame terbaru sebagai numpy array (BGR), atau None.
        """
        with self._lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    @property
    def fps(self) -> float:
        """FPS aktual dari capture loop."""
        return self._actual_fps

    def _capture_loop(self) -> None:
        """Background thread: baca frame secara kontinu."""
        frame_interval = 1.0 / self.target_fps
        frame_count = 0
        fps_start = time.time()

        while not self._stop_event.is_set():
            ret, frame = self._capture.read()
            if not ret:
                # Untuk file video, loop kembali ke awal
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            with self._lock:
                self._latest_frame = frame

            frame_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                self._actual_fps = frame_count / elapsed
                frame_count = 0
                fps_start = time.time()

            # Throttle ke target FPS
            time.sleep(max(0, frame_interval - 0.001))

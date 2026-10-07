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
import socket
import threading
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import cv2
import numpy as np

from app.core.config import get_settings

from app.core.logging import get_logger
log = get_logger("app.services.camera_service")


# Derajat searah jarum jam -> kode rotasi OpenCV. None = tanpa rotasi.
_ROTATE_CODES = {
    0: None,
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


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

        # Rotasi diterapkan di capture loop, jadi stream dan model sama-sama menerima gambar tegak.
        if settings.CAMERA_ROTATE not in _ROTATE_CODES:
            raise ValueError(f"CAMERA_ROTATE harus salah satu dari {sorted(_ROTATE_CODES)}, dapat {settings.CAMERA_ROTATE}")
        self._rotate_code = _ROTATE_CODES[settings.CAMERA_ROTATE]

        self.is_active = False
        self._capture: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._actual_fps: float = 0.0

        # Waktu frame terakhir yang BERHASIL dibaca. Dipakai untuk mendeteksi frame basi:
        # tanpa ini, satu frame lama bisa disajikan terus-menerus seolah kamera masih hidup.
        self._last_frame_at: float = 0.0
        self._stale_after: float = settings.CAMERA_STALE_SEC

        # File video berperilaku beda dari siaran langsung saat read() gagal:
        # file perlu diulang dari awal, siaran langsung perlu disambungkan ulang.
        self._is_file = (not self.source.isdigit()) and Path(self.source).exists()

    def start(self) -> bool:
        """Mulai capture video di background thread.

        Returns:
            True jika berhasil start, False jika gagal.
        """
        self._capture = self._buka_capture()
        if not self._capture.isOpened():
            log.info(f"❌ Gagal membuka kamera: {self.source}")
            return False

        self.is_active = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
            name=f"camera-{self.camera_id}",
        )
        self._thread.start()
        log.info(f"📷 Camera {self.camera_id} started (source={self.source})")
        return True

    def stop(self) -> None:
        """Hentikan capture video."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        if self._capture:
            self._capture.release()
        self.is_active = False
        log.info(f"📷 Camera {self.camera_id} stopped")

    def _host_terjangkau(self, batas: float = 2.0) -> bool:
        """Cek cepat apakah host sumber bisa disambungi lewat TCP.

        Tanpa ini, cv2.VideoCapture ke alamat yang tidak terjangkau menggantung sekitar
        90 detik sebelum menyerah -- startup backend ikut tertahan selama itu, dan setiap
        percobaan sambung ulang juga.
        """
        u = urlparse(self.source)
        if not u.hostname:
            return True
        port = u.port or (554 if u.scheme == "rtsp" else 80)
        try:
            with socket.create_connection((u.hostname, port), timeout=batas):
                return True
        except OSError:
            return False

    def _buka_capture(self) -> cv2.VideoCapture:
        """Buka koneksi ke sumber video.

        Untuk siaran langsung, buffer dibatasi 1 frame supaya yang terbaca selalu gambar
        terbaru. Tanpa ini frame menumpuk di antrean dan tampilan jadi tertinggal jauh.

        Kalau host-nya tidak terjangkau, dikembalikan objek VideoCapture kosong
        (isOpened() bernilai False) supaya pemanggil gagal cepat, bukan menunggu ~90 detik.
        """
        src = int(self.source) if self.source.isdigit() else self.source
        if isinstance(src, str) and "://" in src and not self._host_terjangkau():
            return cv2.VideoCapture()
        cap = cv2.VideoCapture(src)
        if not self._is_file:
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass    # tidak semua backend OpenCV mendukung ini
        return cap

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Ambil frame terbaru (thread-safe).

        Mengembalikan None kalau frame terakhir sudah lebih tua dari CAMERA_STALE_SEC.
        Ini disengaja: kamera yang koneksinya putus harus terbaca sebagai OFFLINE, bukan
        menyajikan gambar lama yang sama berulang kali seolah semuanya baik-baik saja.

        Returns:
            Frame terbaru sebagai numpy array (BGR), atau None.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            if time.monotonic() - self._last_frame_at > self._stale_after:
                return None
            return self._latest_frame.copy()

    @property
    def fps(self) -> float:
        """FPS aktual dari capture loop."""
        return self._actual_fps

    def _capture_loop(self) -> None:
        """Background thread: baca frame secara kontinu."""
        frame_interval = 1.0 / self.target_fps
        frame_count = 0
        fps_start = time.time()

        gagal_beruntun = 0

        while not self._stop_event.is_set():
            ret, frame = self._capture.read()

            if not ret:
                gagal_beruntun += 1
                self._actual_fps = 0.0

                if self._is_file:
                    # File video sudah habis: ulang dari awal.
                    self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                # Siaran langsung (webcam / kamera HP / RTSP). read() yang gagal di sini
                # TIDAK akan pulih sendiri, jadi koneksinya harus dibuka ulang. Sebelum
                # perbaikan ini, loop berputar tanpa henti dan frame lama tersaji terus.
                if gagal_beruntun == 1 or gagal_beruntun % 20 == 0:
                    log.info(f"⚠️  {self.camera_id}: gagal membaca frame ({gagal_beruntun}x), menyambung ulang...")
                if self._stop_event.wait(1.0):
                    break
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = self._buka_capture()
                continue

            if gagal_beruntun:
                log.info(f"✅ {self.camera_id}: koneksi kamera pulih setelah {gagal_beruntun}x gagal")
                gagal_beruntun = 0

            if self._rotate_code is not None:
                frame = cv2.rotate(frame, self._rotate_code)

            with self._lock:
                self._latest_frame = frame
                self._last_frame_at = time.monotonic()

            frame_count += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                self._actual_fps = frame_count / elapsed
                frame_count = 0
                fps_start = time.time()

            # Throttle ke target FPS
            time.sleep(max(0, frame_interval - 0.001))

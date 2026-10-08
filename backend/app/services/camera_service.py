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
import http.client
import socket
import sys
import ssl
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


# ---- Helper sumber kamera (dipakai juga oleh endpoint sebelum menyimpan) ----

def sumber_adalah_file(source: str) -> bool:
    """True kalau sumber menunjuk file video yang ada di disk."""
    return (not source.isdigit()) and "://" not in source and Path(source).exists()


def host_terjangkau(source: str, batas: float = 3.0) -> bool:
    """Cek cepat apakah host pada URL sumber bisa disambungi lewat TCP.

    Tanpa ini, cv2.VideoCapture ke alamat yang tidak terjangkau menggantung sekitar
    90 detik sebelum menyerah -- startup backend ikut tertahan selama itu, dan setiap
    percobaan sambung ulang juga. Sumber non-URL selalu dianggap terjangkau.
    """
    u = urlparse(source)
    if not u.hostname:
        return True
    port = u.port or (554 if u.scheme == "rtsp" else 80)
    try:
        with socket.create_connection((u.hostname, port), timeout=batas):
            return True
    except OSError:
        return False


def _periksa_konten_http(source: str, batas: float = 3.0) -> tuple[bool, str]:
    """Pastikan URL benar-benar mengirim aliran gambar, bukan halaman web.

    Host yang bisa dihubungi belum berarti alamatnya benar. Aplikasi IP Webcam
    menyajikan halaman HTML di akar (`http://IP:8080`) dan aliran MJPEG-nya di
    `/video`. Alamat tanpa `/video` lolos pemeriksaan TCP tapi gagal saat dibuka
    OpenCV, dan kegagalannya muncul belakangan tanpa penjelasan.

    Hanya header yang dibaca; badan respons tidak pernah diambil, jadi aliran
    MJPEG yang tak berujung tidak membuat pemeriksaan ini menggantung.
    """
    u = urlparse(source)
    koneksi = None
    try:
        if u.scheme == "https":
            # Kamera di jaringan lokal lazimnya memakai sertifikat tanda tangan sendiri.
            konteks = ssl._create_unverified_context()
            koneksi = http.client.HTTPSConnection(u.hostname, u.port or 443,
                                                  timeout=batas, context=konteks)
        else:
            koneksi = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=batas)

        koneksi.request("GET", u.path or "/", headers={"User-Agent": "FallDetect/1.0"})
        respons = koneksi.getresponse()
        status = respons.status
        tipe = (respons.headers.get("Content-Type") or "").lower()
    except Exception:
        # Tidak bisa disimpulkan (server tidak bicara HTTP, mis. RTSP di port tak lazim).
        # Jangan menolak hanya karena probe ini gagal.
        return True, ""
    finally:
        if koneksi is not None:
            try:
                koneksi.close()
            except Exception:
                pass

    if status >= 400:
        return False, f"Server menjawab HTTP {status} untuk alamat itu. Periksa kembali path-nya."

    if tipe.startswith("text/html"):
        akar = f"{u.scheme}://{u.hostname}:{u.port or 80}"
        return False, (
            "Alamat itu mengembalikan halaman web, bukan aliran video. "
            f"Untuk aplikasi IP Webcam, tambahkan /video di belakangnya: {akar}/video"
        )

    return True, ""


def validasi_sumber(source: str, batas: float = 3.0) -> tuple[bool, str]:
    """Periksa apakah sumber kamera benar-benar bisa dipakai.

    Dipanggil sebelum kamera disimpan ke database, supaya salah ketik alamat
    ketahuan saat itu juga dan bukan muncul belakangan sebagai kamera OFFLINE
    tanpa penjelasan.

    Catatan: pemeriksaan ini memblokir (membuka socket / perangkat), jadi dari
    kode async panggil lewat asyncio.to_thread.

    Returns:
        (True, "") kalau sumber bisa dipakai, atau (False, alasan).
    """
    source = source.strip()
    if not source:
        return False, "Sumber kamera kosong."

    # Webcam lokal: satu-satunya cara memastikan adalah mencoba membukanya.
    if source.isdigit():
        cap = cv2.VideoCapture(int(source))
        try:
            if not cap.isOpened():
                return False, (
                    f"Webcam indeks {source} tidak bisa dibuka. "
                    "Kemungkinan tidak ada, atau sedang dipakai aplikasi lain "
                    "(browser, Zoom, aplikasi kamera)."
                )
            return True, ""
        finally:
            cap.release()

    if "://" in source:
        u = urlparse(source)
        if u.scheme not in ("http", "https", "rtsp", "rtmp"):
            return False, f"Skema URL '{u.scheme}' tidak didukung. Pakai http, https, atau rtsp."
        if not u.hostname:
            return False, "URL tidak memuat alamat host."
        if not host_terjangkau(source, batas):
            port = u.port or (554 if u.scheme == "rtsp" else 80)
            return False, (
                f"Host {u.hostname}:{port} tidak merespons dalam {batas:.0f} detik. "
                "Pastikan aplikasi kamera di HP sedang menyala, alamat IP-nya masih sama, "
                "dan laptop berada di jaringan yang sama. WiFi kampus/publik sering "
                "memblokir koneksi antar-perangkat (client isolation) -- pakai hotspot HP "
                "atau USB tethering."
            )
        if u.scheme in ("http", "https"):
            return _periksa_konten_http(source, batas)
        return True, ""

    if Path(source).exists():
        return True, ""
    return False, f"File video tidak ditemukan: {source}"


class CameraService:
    """Manage video capture dari satu sumber kamera.

    Attributes:
        camera_id: Identifier unik untuk kamera ini.
        source: Sumber video (index webcam, URL RTSP, atau path file).
        is_active: Apakah kamera sedang aktif menangkap frame.
    """

    def __init__(self, camera_id: str, source: Optional[str] = None, rotate: Optional[int] = None):
        self.camera_id = camera_id
        settings = get_settings()
        self.source = source or settings.CAMERA_SOURCE
        self.target_fps = settings.CAMERA_FPS

        # Rotasi diterapkan di capture loop, jadi stream dan model sama-sama menerima gambar tegak.
        # Nilainya per kamera: kamera HP biasanya butuh 90 derajat sementara webcam laptop tidak,
        # dan keduanya bisa aktif bersamaan. CAMERA_ROTATE di env hanya jadi nilai bawaan.
        putaran = settings.CAMERA_ROTATE if rotate is None else rotate
        if putaran not in _ROTATE_CODES:
            raise ValueError(f"rotate harus salah satu dari {sorted(_ROTATE_CODES)}, dapat {putaran}")
        self.rotate = putaran
        self._rotate_code = _ROTATE_CODES[putaran]

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
        self._is_file = sumber_adalah_file(self.source)

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
        """Cek cepat apakah host sumber bisa disambungi lewat TCP."""
        return host_terjangkau(self.source, batas)

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

        if isinstance(src, int) and sys.platform.startswith("win"):
            # Kamera lokal dibuka lewat DirectShow, bukan MSMF yang jadi bawaan OpenCV
            # di Windows. Dua alasannya:
            #   1. Daftar perangkat di endpoint /devices disusun dari enumerasi
            #      DirectShow, jadi nomor indeksnya hanya cocok kalau pembukaannya
            #      memakai DirectShow juga.
            #   2. MSMF tidak melihat sebagian kamera virtual (OBS tidak muncul sama
            #      sekali) dan kadang mengembalikan nol frame dari perangkat yang
            #      lewat DirectShow terbaca normal.
            cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
        else:
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

    def tunggu_frame_pertama(self, batas: float = 2.0) -> bool:
        """Tunggu sampai frame pertama masuk, maksimal `batas` detik.

        Dipanggil setelah start() supaya status yang dilaporkan ke dashboard sudah
        benar begitu kamera didaftarkan. Tanpa ini, kamera yang baru ditambahkan
        sempat terlihat "Terputus" selama satu-dua putaran loop meski sebenarnya
        baik-baik saja.
        """
        tenggat = time.monotonic() + batas
        while time.monotonic() < tenggat:
            if self.sedang_mengalir:
                return True
            if self._stop_event.wait(0.05):
                break
        return self.sedang_mengalir

    @property
    def sedang_mengalir(self) -> bool:
        """True kalau kamera ini sedang menghasilkan frame yang belum basi.

        Dipakai endpoint daftar kamera untuk menampilkan status Terhubung/Terputus.
        Berbeda dari is_active, yang hanya berarti "thread capture sudah dijalankan"
        dan tetap True walau koneksinya sudah putus.
        """
        with self._lock:
            return (
                self._latest_frame is not None
                and (time.monotonic() - self._last_frame_at) <= self._stale_after
            )

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
                    # File video sudah habis: ulang dari awal. Ini kejadian normal,
                    # bukan gangguan koneksi, jadi hitungannya di-nol-kan supaya tidak
                    # muncul pesan "menyambung ulang" setiap kali video selesai diputar.
                    self._capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    gagal_beruntun = 0
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

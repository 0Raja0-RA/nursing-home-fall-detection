"""
registry.py
===========
Penyimpanan global untuk state yang hidup selama aplikasi berjalan:
instance kamera, state machine, dan background tasks.
"""

import asyncio
from typing import Dict, Optional

from app.models.schemas import CameraStatus, DetectionResult
from app.services.camera_service import CameraService
from app.services.state_machine import FallStateMachine

class AppRegistry:
    def __init__(self):
        self.cameras: Dict[str, CameraService] = {}
        self.state_machines: Dict[str, FallStateMachine] = {}
        self.pipeline_tasks: Dict[str, asyncio.Task] = {}

        # Hasil inference terakhir per kamera (satu entri per orang). Diisi oleh detection_pipeline dan dibaca oleh
        # endpoint stream untuk menggambar bounding box -- supaya inference tidak dijalankan
        # dua kali untuk frame yang sama.
        self.latest_detection: Dict[str, list[DetectionResult]] = {}
        # Status terakhir per kamera, dipakai GET /api/cameras/ supaya dashboard bisa
        # menampilkan daftar kamera tanpa harus menunggu pesan WebSocket.
        self.latest_status: Dict[str, CameraStatus] = {}

        # Frame terakhir yang sudah digambari kotak dan dikemas jadi JPEG, siap kirim.
        # Diisi sekali per frame oleh detection_pipeline, lalu dibagikan ke semua
        # penonton -- sebelumnya tiap penonton menggambar dan meng-encode sendiri di
        # event loop, sehingga dua halaman yang terbuka bersamaan saling berebut.
        self.latest_jpeg: Dict[str, Optional[bytes]] = {}
        # Dinaikkan setiap kali latest_jpeg diperbarui, supaya generator stream tahu
        # ada frame baru tanpa perlu membandingkan isi byte-nya.
        self.frame_seq: Dict[str, int] = {}

        # Batas waktu (time.monotonic) simulasi jatuh per kamera.
        #
        # Selama belum terlewati, pipeline memperlakukan kamera itu seolah model
        # melaporkan postur pemicu. Yang disimulasikan HANYA keluaran detektor:
        # state machine, timer, debounce, cooldown, penyimpanan alert, dan
        # notifikasi tetap berjalan apa adanya. Modelnya sendiri belum andal di
        # luar ruangan dataset, jadi berbaring di depan kamera sering terbaca
        # "transitional" dan tidak pernah memicu alarm.
        self.simulasi_sampai: Dict[str, float] = {}

    def sedang_disimulasikan(self, camera_id: str) -> bool:
        """True kalau kamera ini sedang dalam masa simulasi jatuh."""
        import time
        return self.simulasi_sampai.get(camera_id, 0.0) > time.monotonic()

registry = AppRegistry()

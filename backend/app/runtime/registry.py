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

        # Hasil inference terakhir per kamera. Diisi oleh detection_pipeline dan dibaca oleh
        # endpoint stream untuk menggambar bounding box -- supaya inference tidak dijalankan
        # dua kali untuk frame yang sama.
        self.latest_detection: Dict[str, Optional[DetectionResult]] = {}
        # Status terakhir per kamera, dipakai GET /api/cameras/ supaya dashboard bisa
        # menampilkan daftar kamera tanpa harus menunggu pesan WebSocket.
        self.latest_status: Dict[str, CameraStatus] = {}

registry = AppRegistry()

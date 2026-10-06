"""
registry.py
===========
Penyimpanan global untuk state yang hidup selama aplikasi berjalan:
instance kamera, state machine, dan background tasks.
"""

import asyncio
from typing import Dict

from app.services.camera_service import CameraService
from app.services.state_machine import FallStateMachine

class AppRegistry:
    def __init__(self):
        self.cameras: Dict[str, CameraService] = {}
        self.state_machines: Dict[str, FallStateMachine] = {}
        self.pipeline_tasks: Dict[str, asyncio.Task] = {}

registry = AppRegistry()

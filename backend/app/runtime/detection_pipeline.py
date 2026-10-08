"""
detection_pipeline.py
=====================
Loop utama untuk satu kamera: mengambil frame, menjalankan inference,
mengonversi ke observasi, dan menyuapkannya ke state machine.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.logging import utc_now_naive
from app.models.schemas import Observation, CameraStatus, WSMessage
from app.services.camera_service import CameraService
from app.runtime.registry import registry
from app.services.inference_service import run_inference
from app.services.overlay import jadikan_jpeg
from app.services.state_machine import FallStateMachine
from app.websocket.ws_manager import manager


async def camera_pipeline(camera: CameraService, fsm: FallStateMachine):
    """Detection loop untuk satu kamera."""
    settings = get_settings()
    
    # Throttle interval minimal (10 fps maksimal untuk inference)
    loop_interval = 1.0 / settings.CAMERA_FPS
    
    while camera.is_active:
        loop_start = time.time()
        
        frame = camera.get_latest_frame()
        if frame is None:
            # Frame tidak tersedia atau kamera offline
            fsm.update(Observation.OFFLINE)
            
            # Broadcast offline status
            status = CameraStatus(
                camera_id=camera.camera_id,
                is_active=False,
                fall_state=fsm.state,
                fall_duration=0.0,
                last_frame_at=utc_now_naive()
            )
            registry.latest_detection[camera.camera_id] = None
            registry.latest_status[camera.camera_id] = status
            registry.latest_jpeg[camera.camera_id] = None
            await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))

            await asyncio.sleep(0.1)
            continue
            
        # Inference (dieksekusi di thread pool agar tidak memblokir event loop async)
        result = await asyncio.to_thread(run_inference, frame)
        
        # Terjemahkan DetectionResult ke Observation untuk FSM
        if result is None:
            observation = Observation.PERSON_LOST
        elif result.confidence < settings.CONFIDENCE_THRESHOLD:
            observation = Observation.UNCERTAIN
        else:
            if result.posture.value in settings.TRIGGER_CLASSES:
                observation = Observation.TRIGGER_POSTURE
            else:
                observation = Observation.NON_TRIGGER_POSTURE

        # Simulasi jatuh: timpa observasi, jangan timpa apa pun yang lain.
        #
        # Hanya baris inilah yang berpura-pura. State machine di bawah tetap
        # menghitung durasi, menerapkan debounce, menghormati cooldown, dan
        # memicu alert lewat jalur yang sama persis dengan deteksi sungguhan.
        if registry.sedang_disimulasikan(camera.camera_id):
            observation = Observation.TRIGGER_POSTURE

                
        # Update FSM dengan observasi terbaru
        new_state = fsm.update(observation)
        
        # Broadcast status terkini ke WebSocket
        status = CameraStatus(
            camera_id=camera.camera_id,
            is_active=camera.is_active,
            current_posture=result.posture if result else None,
            fall_state=new_state,
            fall_duration=fsm.fall_duration,
            confidence=result.confidence if result else 0.0,
            fps=camera.fps,
            last_frame_at=utc_now_naive()
        )
        # Simpan untuk dipakai endpoint stream (menggambar kotak) dan GET /api/cameras/.
        registry.latest_detection[camera.camera_id] = result
        registry.latest_status[camera.camera_id] = status

        # Gambar kotak dan encode JPEG sekali di sini, bukan sekali per penonton di
        # endpoint stream. cv2.imencode itu kerja CPU yang memblokir, jadi dijalankan
        # di thread supaya event loop tetap bisa melayani REST dan WebSocket.
        jpeg = await asyncio.to_thread(
            jadikan_jpeg, frame, result, settings.CONFIDENCE_THRESHOLD
        )
        registry.latest_jpeg[camera.camera_id] = jpeg
        registry.frame_seq[camera.camera_id] = registry.frame_seq.get(camera.camera_id, 0) + 1
        await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))
        
        # Pastikan tidak melahap 100% CPU, tidur sisa waktunya
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, loop_interval - elapsed)
        await asyncio.sleep(sleep_time)

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
from app.core.logging import get_logger, utc_now_naive
from app.models.schemas import DetectionResult, Observation, CameraStatus, WSMessage
from app.services.camera_service import CameraService
from app.runtime.registry import registry
from app.services.inference_service import run_inference
from app.services.overlay import jadikan_jpeg
from app.services.state_machine import FallStateMachine
from app.websocket.ws_manager import manager

log = get_logger("app.runtime.detection_pipeline")

# Makin kecil makin diutamakan. Satu orang tergeletak harus menang atas orang
# lain yang berdiri di frame yang sama; kalau tidak, yang berdiri terus mereset
# timer yang jatuh. UNCERTAIN di atas NON_TRIGGER karena orang yang
# posturnya samar bisa jadi sedang tergeletak: timer ditahan, bukan direset.
_PRIORITAS = {
    Observation.TRIGGER_POSTURE: 0,
    Observation.UNCERTAIN: 1,
    Observation.NON_TRIGGER_POSTURE: 2,
}


def pilih_observasi(results: list[DetectionResult], settings) -> tuple[Observation, Optional[DetectionResult]]:
    """Gabungkan deteksi semua orang di satu frame jadi satu observasi kamera.

    Returns:
        (observasi, deteksi yang mewakilinya -- yang paling yakin di antara
        orang yang menentukan observasi itu; None kalau tidak ada siapa pun)
    """
    if not results:
        return Observation.PERSON_LOST, None

    def observasi_satu(r: DetectionResult) -> Observation:
        pemicu = r.posture.value in settings.TRIGGER_CLASSES
        # Postur pemicu tidak boleh dibungkam oleh ambang umum: orang yang
        # tergeletak justru yang keyakinannya paling rendah.
        if pemicu and r.confidence >= settings.TRIGGER_MIN_CONF:
            return Observation.TRIGGER_POSTURE
        if r.posture.value in settings.PAUSE_CLASSES:
            return Observation.UNCERTAIN
        if r.confidence < settings.CONFIDENCE_THRESHOLD:
            return Observation.UNCERTAIN
        return Observation.NON_TRIGGER_POSTURE

    berpasangan = [(observasi_satu(r), r) for r in results]
    menang = min((o for o, _ in berpasangan), key=_PRIORITAS.get)
    wakil = max((r for o, r in berpasangan if o == menang), key=lambda r: r.confidence)
    return menang, wakil


async def camera_pipeline(camera: CameraService, fsm: FallStateMachine):
    """Detection loop untuk satu kamera."""
    settings = get_settings()
    
    # Throttle interval minimal (10 fps maksimal untuk inference)
    loop_interval = 1.0 / settings.CAMERA_FPS
    
    terakhir_log = 0.0

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
            registry.latest_detection[camera.camera_id] = []
            registry.latest_status[camera.camera_id] = status
            registry.latest_jpeg[camera.camera_id] = None
            await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))

            await asyncio.sleep(0.1)
            continue
            
        # Inference (dieksekusi di thread pool agar tidak memblokir event loop async)
        results = await asyncio.to_thread(run_inference, frame)
        
        # Terjemahkan semua deteksi ke satu Observation untuk FSM
        observation, result = pilih_observasi(results, settings)

        # Simulasi jatuh: timpa observasi, jangan timpa apa pun yang lain.
        #
        # Hanya baris inilah yang berpura-pura. State machine di bawah tetap
        # menghitung durasi, menerapkan debounce, menghormati cooldown, dan
        # memicu alert lewat jalur yang sama persis dengan deteksi sungguhan.
        if registry.sedang_disimulasikan(camera.camera_id):
            observation = Observation.TRIGGER_POSTURE

                
        # Update FSM dengan observasi terbaru
        new_state = fsm.update(observation)

        # Log diagnosa, sekali per detik: apa yang dilihat model, diterjemahkan
        # jadi apa, dan seberapa jauh timernya. Untuk menjawab "kenapa alarm tidak
        # berbunyi" tanpa menebak.
        if time.time() - terakhir_log >= 1.0:
            terakhir_log = time.time()
            ringkas = ", ".join(f"{r.posture.value}:{r.confidence:.2f}" for r in results) or "tidak ada"
            log.info(f"[{camera.camera_id}] lihat=[{ringkas}] -> {observation.value} | "
                     f"state={new_state.value} timer={fsm.fall_duration:.1f}/"
                     f"{fsm.fall_duration_threshold:.0f}s")
        
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
        registry.latest_detection[camera.camera_id] = results
        registry.latest_status[camera.camera_id] = status

        # Gambar kotak dan encode JPEG sekali di sini, bukan sekali per penonton di
        # endpoint stream. cv2.imencode itu kerja CPU yang memblokir, jadi dijalankan
        # di thread supaya event loop tetap bisa melayani REST dan WebSocket.
        jpeg = await asyncio.to_thread(
            jadikan_jpeg, frame, results, settings.CONFIDENCE_THRESHOLD,
            settings.SHOW_UNCERTAIN_BOXES, settings.TRIGGER_MIN_CONF,
            tuple(settings.TRIGGER_CLASSES)
        )
        registry.latest_jpeg[camera.camera_id] = jpeg
        registry.frame_seq[camera.camera_id] = registry.frame_seq.get(camera.camera_id, 0) + 1
        await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))
        
        # Pastikan tidak melahap 100% CPU, tidur sisa waktunya
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, loop_interval - elapsed)
        await asyncio.sleep(sleep_time)

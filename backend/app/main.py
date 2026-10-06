"""
Fall Detection Backend — FastAPI Entry Point
=============================================
Inisialisasi aplikasi FastAPI, mounting routers, CORS middleware,
WebSocket endpoint, dan lifecycle events (startup/shutdown).

Jalankan dengan:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
import asyncio
import sys

# Fix Windows emoji print error
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, cameras, settings
from app.core.config import get_settings
from app.db.database import init_db
from app.websocket.ws_manager import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: jalankan saat startup & cleanup saat shutdown."""
    # --- Startup ---
    settings = get_settings()
    print(f"🚀 Starting Fall Detection Backend (env={settings.ENVIRONMENT})")
    await init_db()

    # Import saat runtime untuk menghindari circular dependency
    from app.runtime.registry import registry
    from app.services.camera_service import CameraService
    from app.services.state_machine import FallStateMachine
    from app.runtime.detection_pipeline import camera_pipeline
    from app.services.alert_service import alert_service

    # Setup kamera tunggal (untuk MVP)
    cam_id = "cam-01"
    camera = CameraService(camera_id=cam_id)
    if camera.start():
        registry.cameras[cam_id] = camera
        
        def trigger_alert(c_id: str, duration: float):
            # Jalankan async alert process tanpa memblokir callback
            asyncio.create_task(alert_service.process_confirmed_fall(c_id, duration))
            
        fsm = FallStateMachine(
            camera_id=cam_id,
            fall_duration_threshold=settings.FALL_DURATION_THRESHOLD,
            possible_fall_threshold=settings.POSSIBLE_FALL_THRESHOLD,
            debounce_frames=settings.DEBOUNCE_FRAMES,
            grace_period_sec=settings.GRACE_PERIOD_SEC,
            on_confirmed_fall=trigger_alert
        )
        registry.state_machines[cam_id] = fsm
        
        # Jalankan loop pipeline secara asynchronous
        task = asyncio.create_task(camera_pipeline(camera, fsm))
        registry.pipeline_tasks[cam_id] = task

    yield
    # --- Shutdown ---
    print("🛑 Shutting down Fall Detection Backend")
    
    from app.runtime.registry import registry
    
    # Matikan loop pipeline
    for task in registry.pipeline_tasks.values():
        task.cancel()
        
    if registry.pipeline_tasks:
        await asyncio.gather(*registry.pipeline_tasks.values(), return_exceptions=True)

    # Matikan capture kamera
    for camera in registry.cameras.values():
        camera.stop()

    # Bebaskan memori GPU / RAM dari model YOLO
    from app.services.inference_service import unload_model
    unload_model()


app = FastAPI(
    title="Fall Detection API",
    description="REST & WebSocket API untuk sistem deteksi jatuh real-time di panti jompo.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---- CORS (izinkan frontend dev server) --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: batasi di production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Mount Routers -----------------------------------------
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"])
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "fall-detection-backend"}

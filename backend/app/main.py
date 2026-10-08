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

from app.core.logging import get_logger
log = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle: jalankan saat startup & cleanup saat shutdown."""
    # --- Startup ---
    settings = get_settings()
    log.info(f"🚀 Starting Fall Detection Backend (env={settings.ENVIRONMENT})")
    await init_db()

    # Import saat runtime untuk menghindari circular dependency
    from app.runtime import camera_manager

    # Nyalakan semua kamera yang tersimpan di database. Kalau tabelnya masih kosong,
    # satu kamera bawaan dibuat dari CAMERA_SOURCE supaya alur run-backend.bat yang
    # lama tetap bekerja tanpa harus mendaftar lewat dashboard dulu.
    await camera_manager.muat_dari_db()

    yield
    # --- Shutdown ---
    log.info("🛑 Shutting down Fall Detection Backend")

    await camera_manager.hentikan_semua()

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

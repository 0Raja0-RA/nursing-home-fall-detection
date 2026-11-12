"""
Fall Detection Backend — FastAPI Entry Point
=============================================
Inisialisasi aplikasi FastAPI, mounting routers, CORS middleware,
WebSocket endpoint, dan lifecycle events (startup/shutdown).

Jalankan dengan:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import sys

# Fix Windows emoji print error
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import alerts, auth, cameras, settings
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

    # Terapkan pengaturan yang pernah diubah lewat dashboard SEBELUM kamera
    # dinyalakan, supaya pipeline memakai model dan threshold yang benar sejak
    # frame pertama -- bukan memakai bawaan sebentar lalu berganti.
    from app.api.settings import muat_dari_db as muat_pengaturan
    from app.db.database import get_session_factory

    async with get_session_factory()() as session:
        await muat_pengaturan(session)
        # Akun demo tim dari backend/.env, disamakan setiap backend menyala.
        await auth.siapkan_akun_demo(session)
        # Mode perawatan yang belum habis, sebelum pipeline kamera mulai berjalan.
        from app.services.mode_perawatan import muat_dari_db as muat_jeda
        await muat_jeda(session)

    # Import saat runtime untuk menghindari circular dependency
    from app.runtime import camera_manager

    # Nyalakan semua kamera yang tersimpan di database. Kalau tabelnya masih kosong,
    # satu kamera bawaan dibuat dari CAMERA_SOURCE supaya alur run-backend.bat yang
    # lama tetap bekerja tanpa harus mendaftar lewat dashboard dulu.
    await camera_manager.muat_dari_db()

    # Pekerja latar: penerima tombol di pesan Telegram, pemantau yang mengabari grup
    # saat kamera terputus (keduanya diam kalau Telegram belum diisi), dan pembersih
    # klip kejadian yang melewati masa simpan.
    from app.runtime.pemantau_kamera import jalankan_pemantau
    from app.services.eskalasi import jalankan_eskalasi
    from app.services.klip import jalankan_pembersih
    from app.services.telegram_bot import jalankan_penerima

    pekerja = [asyncio.create_task(jalankan_penerima()), asyncio.create_task(jalankan_pemantau()),
               asyncio.create_task(jalankan_pembersih()), asyncio.create_task(jalankan_eskalasi())]

    yield
    # --- Shutdown ---
    log.info("🛑 Shutting down Fall Detection Backend")

    for task in pekerja:
        task.cancel()
    await asyncio.gather(*pekerja, return_exceptions=True)

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
# Dashboard memakai cookie sesi, jadi asal permintaan harus disebut satu per satu,
# bukan "*". Yang diizinkan: alamat di ALLOWED_ORIGINS, ditambah localhost dan
# alamat jaringan lokal (10.x, 172.16-31.x, 192.168.x) di port mana pun, supaya
# dashboard tetap bisa dibuka dari HP di WiFi atau hotspot yang sama.
_ASAL_LOKAL = (
    r"^https?://(localhost|127\.0\.0\.1|\[::1\]|10(\.\d{1,3}){3}|192\.168(\.\d{1,3}){2}"
    r"|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})(:\d+)?$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[a.strip() for a in get_settings().ALLOWED_ORIGINS.split(",") if a.strip()],
    allow_origin_regex=_ASAL_LOKAL,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Mount Routers -----------------------------------------
# Semua API wajib login, kecuali /api/auth (status, masuk, pengunjung, keluar) dan
# health check. Video kamera ikut terlindungi karena berada di bawah /api/cameras.
# Pengunjung dari QR stand boleh membaca semuanya, tetapi tidak bisa mengubah apa pun.
_login = [Depends(auth.wajib_login), Depends(auth.tolak_perubahan_pengunjung)]
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(auth.router_akun, prefix="/api/users", tags=["Users"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"], dependencies=_login)
app.include_router(cameras.router, prefix="/api/cameras", tags=["Cameras"], dependencies=_login)
app.include_router(settings.router, prefix="/api/settings", tags=["Settings"], dependencies=_login)
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "fall-detection-backend"}


# ---- Dashboard (build frontend) ---------------------------
# Untuk pameran, backend ikut menyajikan hasil `npm run build`, supaya dashboard dan
# API berada di satu host saat dibuka lewat tunnel. Hanya dengan begitu cookie sesi
# (SameSite=Lax) ikut terkirim. Didaftarkan paling akhir: /api, /ws, /docs, dan
# health check di atas tetap didahulukan.
_dist_setel = get_settings().FRONTEND_DIST.strip()
_DIST = (Path(__file__).resolve().parents[1] / _dist_setel).resolve() if _dist_setel else None

if _DIST is not None and (_DIST / "index.html").is_file():
    _INDEX = _DIST / "index.html"

    @app.api_route("/{jalur:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def sajikan_dashboard(jalur: str):
        """Berkas statis dari build, atau index.html untuk rute SPA (/login, /lihat, ...)."""
        # Alamat API yang tidak dikenal tetap dijawab 404 JSON, bukan halaman dashboard.
        if jalur == "api" or jalur.startswith(("api/", "ws")):
            raise HTTPException(status_code=404, detail="Not Found")
        if jalur:
            berkas = (_DIST / jalur).resolve()
            # Tolak jalur yang keluar dari folder build (mis. ../../backend/.env).
            if berkas.is_file() and berkas.is_relative_to(_DIST):
                # Nama berkas di assets/ memuat hash isi, jadi aman disimpan lama.
                simpan = "public, max-age=31536000, immutable" if jalur.startswith("assets/") else "no-cache"
                return FileResponse(berkas, headers={"Cache-Control": simpan})
        # index.html selalu diperiksa ulang, supaya build baru langsung terpakai.
        return FileResponse(_INDEX, headers={"Cache-Control": "no-cache"})

    log.info(f"🖥️  Dashboard disajikan dari {_DIST}")

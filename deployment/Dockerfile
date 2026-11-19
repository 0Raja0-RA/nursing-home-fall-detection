# ============================================================
# FallDetect — satu image: backend FastAPI yang ikut menyajikan dashboard
# ============================================================
# Sama seperti mode pameran (tools/pameran.py): dashboard hasil `npm run build`
# disajikan backend, jadi dashboard dan API berada di satu alamat. Dibangun dari
# akar repo lewat deployment/docker-compose.yml.
#
# Susunan folder di dalam image meniru repo (/app/backend, /app/frontend/dist,
# /app/ml/models). Jalur bawaan di backend/app/core/config.py dihitung dari letak
# berkasnya, jadi tetap benar tanpa variabel tambahan.
# ============================================================

# ---- Tahap 1: build dashboard ------------------------------
# Vite 8 butuh Node 20.19 atau 22.12 ke atas.
FROM node:22-slim AS dashboard
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Tahap 2: backend --------------------------------------
# Python 3.12, sama dengan .venv yang dipakai menjalankan tes.
FROM python:3.12-slim
# Batas waktu dan percobaan ulang pip dilonggarkan untuk koneksi lambat: dengan
# bawaan 15 detik, unduhan opencv (sekitar 64 MB) pernah gagal di tengah jalan.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

# OpenCV butuh libGL dan glib: ultralytics ikut memasang opencv-python biasa,
# bukan hanya versi headless yang ada di requirements.txt.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# PyTorch versi CPU dipasang lebih dulu. Tanpa ini, ultralytics menarik versi CUDA
# yang beberapa GB lebih besar, padahal image ini tidak memakai GPU.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt

COPY backend/app ./app
COPY --from=dashboard /app/frontend/dist /app/frontend/dist

# Database, foto kejadian, dan klip disimpan di /app/data, yang dipasang sebagai
# volume di docker-compose.yml supaya tidak hilang saat container dibuat ulang.
# DEBUG=false mematikan cetak setiap perintah SQL ke log (bawaan config.py: true).
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/fall_detection.db \
    KLIP_DIR=/app/data/klip \
    YOLO_CONFIG_DIR=/app/data/ultralytics \
    DEBUG=false
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

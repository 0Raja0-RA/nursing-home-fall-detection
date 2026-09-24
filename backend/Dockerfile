# ============================================================
# Fall Detection Backend — Dockerfile
# ============================================================
# Multi-stage build: slim Python image + headless OpenCV.
# ============================================================

FROM python:3.11-slim AS base

# Prevent Python from writing bytecode & enable unbuffered stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies for OpenCV headless
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1-mesa-glx \
        libsm6 \
        libxext6 \
        libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# ---- Dependencies ------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Application Code --------------------------------------
COPY app/ ./app/

# ---- Model files (mounted via volume in docker-compose) -----
# Model .pt files are NOT baked into the image.
# Mount them at runtime: -v ./ml/models:/app/ml/models

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

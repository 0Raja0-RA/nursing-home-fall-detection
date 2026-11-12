@echo off
setlocal
title FallDetect - Pameran

REM ============================================================
REM  Launcher pameran: dashboard, backend, tunnel, dan QR pengunjung
REM  dalam satu jendela. Rinciannya di docs\deploy-pameran.md.
REM
REM  Pemakaian:
REM    run-pameran.bat                 dengan internet (Cloudflare tunnel)
REM    run-pameran.bat --tanpa-tunnel  cadangan tanpa internet, hanya di laptop ini
REM ============================================================

REM Nilai demo, sama dengan run-backend.bat. Ubah di kedua berkas bila perlu.
set "MODEL_PATH=%~dp0ml\models\fall_detection\weights\best.pt"
set "CONFIDENCE_THRESHOLD=0.5"
set "POSSIBLE_FALL_THRESHOLD=0.5"
set "FALL_DURATION_THRESHOLD=3"
set "ALERT_COOLDOWN_SEC=10"
set "CAMERA_SOURCE=0"
set "CAMERA_ROTATE=0"
set "PORT=8000"
set "OPENCV_FFMPEG_CAPTURE_OPTIONS=timeout;5000000"

cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo [GAGAL] Virtual environment tidak ditemukan di %PY%
    echo Buat dulu: py -3.12 -m venv .venv
    echo            .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
    echo [GAGAL] File model tidak ditemukan: %MODEL_PATH%
    echo Minta best.pt ke anggota ML, atau ubah MODEL_PATH di berkas ini.
    pause
    exit /b 1
)

"%PY%" "%~dp0tools\pameran.py" %*

echo.
pause

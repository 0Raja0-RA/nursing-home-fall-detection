@echo off
setlocal enabledelayedexpansion
title FallDetect - Backend

REM ============================================================
REM  PENGATURAN -- ubah bagian ini sesuai komputer & kamera kamu
REM ============================================================

REM Sumber kamera:
REM   "0"                                     = webcam laptop
REM   "http://10.252.129.120:8080/video"      = kamera HP via aplikasi IP Webcam
REM   "D:\...\fall-01-cam0.mp4"               = file video untuk uji ulang
REM
REM CATATAN: alamat IP HP berubah setiap kali pindah/menyambung ulang WiFi.
REM Lihat alamatnya di layar aplikasi IP Webcam, lalu samakan baris di bawah.
REM Di WiFi kampus biasanya antar-perangkat diblokir (client isolation), jadi
REM pakai hotspot HP atau USB tethering. Penjelasannya ada di TESTING.md.
set "CAMERA_SOURCE=http://10.252.129.120:8080/video"

REM Putar gambar searah jarum jam: 0, 90, 180, atau 270.
REM Kamera HP biasanya mengirim gambar miring, jadi butuh 90.
set "CAMERA_ROTATE=90"

REM Model hasil training tim (EXP-006 / exp006_hybrid_adamw).
REM File .pt tidak ikut di repo (lihat .gitignore), jadi minta ke anggota ML
REM lalu taruh di lokasi di bawah ini. Pastikan kelasnya ada 3
REM (normal, transitional, lying_on_ground) -- bukan 80 kelas COCO.
set "MODEL_PATH=%~dp0ml\models\fall_detection\weights\best.pt"

REM Ambang keyakinan model. 0.5 terlalu tinggi untuk kamera di luar dataset URFD,
REM sehingga layar sering kosong. 0.25 membuat kotak lebih sering muncul.
set "CONFIDENCE_THRESHOLD=0.25"

REM Ambang state machine (detik).
set "POSSIBLE_FALL_THRESHOLD=0.5"
set "FALL_DURATION_THRESHOLD=3"

REM Alamat server backend.
set "HOST=127.0.0.1"
set "PORT=8000"

REM ============================================================
REM  Di bawah ini tidak perlu diubah
REM ============================================================

cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

echo ============================================================
echo  FallDetect - Backend
echo ============================================================
echo.

if not exist "%PY%" (
    echo [GAGAL] Virtual environment tidak ditemukan di:
    echo         %PY%
    echo.
    echo Buat dulu dengan perintah berikut di folder ini:
    echo         py -3.12 -m venv .venv
    echo         .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%MODEL_PATH%" (
    echo [GAGAL] File model tidak ditemukan:
    echo         %MODEL_PATH%
    echo.
    echo File bobot .pt sengaja tidak disimpan di repo. Minta file best.pt
    echo hasil EXP-006 ke anggota ML, lalu taruh di path di atas.
    echo Atau ubah nilai MODEL_PATH di bagian PENGATURAN pada file ini.
    echo.
    pause
    exit /b 1
)

echo Model           : %MODEL_PATH%
echo Sumber kamera   : %CAMERA_SOURCE%
echo Rotasi gambar   : %CAMERA_ROTATE% derajat
echo Ambang keyakinan: %CONFIDENCE_THRESHOLD%
echo.

echo Mengecek apakah kamera bisa dibuka...
set "OPENCV_FFMPEG_CAPTURE_OPTIONS=timeout;5000000"
"%PY%" "%~dp0tools\check_camera.py" "%CAMERA_SOURCE%" 2>nul
if errorlevel 1 (
    echo.
    echo Backend tetap dijalankan, tapi tidak akan ada gambar maupun deteksi
    echo sampai sumber kameranya bisa dibuka.
    echo.
    pause
)
echo.

echo ============================================================
echo  Setelah server menyala, buka alamat ini di browser:
echo.
echo    Video + bounding box :
echo    http://%HOST%:%PORT%/api/cameras/cam-01/stream
echo.
echo    Dokumentasi API      :
echo    http://%HOST%:%PORT%/docs
echo.
echo  Tekan Ctrl+C untuk menghentikan server.
echo ============================================================
echo.

cd backend
"%PY%" -m uvicorn app.main:app --host %HOST% --port %PORT%

echo.
echo Server berhenti.
pause

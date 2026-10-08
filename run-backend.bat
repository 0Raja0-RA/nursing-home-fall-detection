@echo off
setlocal enabledelayedexpansion
title FallDetect - Backend

REM ============================================================
REM  PENGATURAN -- ubah bagian ini sesuai komputer & kamera kamu
REM ============================================================

REM ------------------------------------------------------------
REM  PENTING: daftar kamera sekarang disimpan di database, dan
REM  diatur lewat halaman "Kelola Kamera" di dashboard.
REM
REM  Dua baris di bawah HANYA dipakai saat database masih kosong,
REM  yaitu untuk membuat kamera pertama. Setelah ada kamera yang
REM  terdaftar, keduanya DIABAIKAN -- mengubahnya di sini tidak
REM  akan mengganti kamera yang sedang dipakai.
REM
REM  Mau ganti kamera? Buka dashboard -> Kelola Kamera.
REM ------------------------------------------------------------

REM Kamera pertama saat database masih kosong:
REM   "0"                          = webcam laptop
REM   "1"                          = Iriun Camera #1 (tekan Pindai untuk lihat daftarnya)
REM   "http://IP-HP:8080/video"    = kamera HP via aplikasi IP Webcam
REM   "D:\...\fall-01-cam0.mp4"    = file video untuk uji ulang
set "CAMERA_SOURCE=0"

REM Rotasi bawaan untuk kamera pertama itu (0, 90, 180, 270 searah jarum jam).
REM Rotasi tiap kamera bisa diubah per baris di halaman Kelola Kamera.
set "CAMERA_ROTATE=0"

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

REM Jeda minimal antar alert untuk satu kamera. Bawaannya 60 detik supaya grup
REM perawat tidak dibanjiri saat seseorang tergeletak lama.
REM
REM Diturunkan ke 10 detik di sini karena saat demo wajar diminta mengulang
REM simulasi beberapa kali berturut-turut; dengan 60 detik, tekanan tombol kedua
REM tidak mengirim apa pun dan sistemnya terlihat seperti rusak.
REM Naikkan kembali ke 60 untuk pemakaian sungguhan.
set "ALERT_COOLDOWN_SEC=10"

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
echo Ambang keyakinan: %CONFIDENCE_THRESHOLD%
echo.

set "OPENCV_FFMPEG_CAPTURE_OPTIONS=timeout;5000000"

if exist "%~dp0backend\fall_detection.db" (
    echo Kamera          : diambil dari database yang sudah ada.
    echo                   Untuk melihat atau menggantinya, buka dashboard
    echo                   lalu masuk ke halaman "Kelola Kamera".
    echo.
) else (
    echo Database belum ada. Kamera pertama akan dibuat dari: %CAMERA_SOURCE%
    echo Mengecek apakah kamera itu bisa dibuka...
    "%PY%" "%~dp0tools\check_camera.py" "%CAMERA_SOURCE%" 2>nul
    if errorlevel 1 (
        echo.
        echo Backend tetap dijalankan. Kamera bisa ditambahkan belakangan
        echo lewat halaman "Kelola Kamera" di dashboard.
        echo.
        pause
    )
    echo.
)

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

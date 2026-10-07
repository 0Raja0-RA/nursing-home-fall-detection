@echo off
setlocal
title FallDetect - Frontend

REM ============================================================
REM  FallDetect - Frontend (React + Vite)
REM  Jalankan file ini SETELAH run-backend.bat menyala.
REM ============================================================

cd /d "%~dp0frontend"

echo ============================================================
echo  FallDetect - Frontend
echo ============================================================
echo.

where npm >nul 2>nul
if errorlevel 1 (
    echo [GAGAL] npm tidak ditemukan. Pasang Node.js lebih dulu dari https://nodejs.org
    echo.
    pause
    exit /b 1
)

if not exist "node_modules" (
    echo Folder node_modules belum ada. Memasang dependensi dulu,
    echo proses ini bisa memakan beberapa menit...
    echo.
    call npm install
    if errorlevel 1 (
        echo.
        echo [GAGAL] npm install gagal.
        echo Coba hapus folder node_modules dan file package-lock.json, lalu ulangi.
        echo.
        pause
        exit /b 1
    )
    echo.
)

echo Dashboard akan terbuka di http://localhost:5173
echo Tekan Ctrl+C untuk menghentikan.
echo.

call npm run dev

echo.
echo Frontend berhenti.
pause

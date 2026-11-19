"""Pengaturan bersama semua tes backend: tes tidak boleh menyentuh data pameran.

Setelan dibaca dari variabel lingkungan dan dari `.env` di folder kerja, dan DATABASE_URL
bawaannya `./fall_detection.db`. Akibatnya, pytest yang dijalankan dari folder backend
dulu memakai database pameran dan token Telegram sungguhan. Kode yang membuka database
sendiri lewat `get_session_factory()`, misalnya pencatat episode berbaring, menulis baris
tes ke database itu.

Nilai di bawah diisi saat conftest dimuat, sebelum modul `app` diimpor (get_settings()
di-cache), dan menang atas isi `.env`:
- DATABASE_URL: SQLite di memori tanpa tabel. Kode yang menulis lewat database bawaan tanpa
  disiapkan tes, seperti pencatat episode, kini gagal dengan aman ("no such table") dan tidak
  meninggalkan apa pun. Tes yang butuh database tetap membuat dan menyuntikkan database
  ujinya sendiri.
- Token dan chat Telegram kosong, jadi tidak ada tes yang bisa mengirim ke grup sungguhan.
  Tes Telegram menambal setelan atau fungsi kirimnya sendiri.
- CAMERA_FPS dan TELEGRAM_TUNDA_DETIK memakai nilai bawaan kode, bukan setelan pameran di
  `.env` lokal. Sejumlah tes menghitung frame, bukan detik (mengandaikan 15 fps), dan tes
  pengiriman mengandaikan Telegram langsung terkirim. Tes masa tunda mengisinya sendiri.
"""
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["CAMERA_FPS"] = "15"
os.environ["TELEGRAM_TUNDA_DETIK"] = "0"

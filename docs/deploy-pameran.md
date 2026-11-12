# Deploy untuk pameran

Cara menjalankan FallDetect di stand pameran: satu laptop menjalankan backend, kamera, dan database, lalu dashboard dibuka dari HP pengunjung lewat QR.

## Susunan

```
HP pengunjung ── scan QR ──► https://xxxx.trycloudflare.com/lihat#t=TOKEN
Tim stand     ─────────────► https://xxxx.trycloudflare.com/login
                                        │ Cloudflare quick tunnel (HTTPS)
                                        ▼
               Laptop stand: backend FastAPI (127.0.0.1:8000)
                 ├─ /api, /ws          API, video MJPEG, WebSocket
                 ├─ /login, /dashboard dashboard hasil `npm run build`
                 └─ fall_detection.db  SQLite, satu-satunya database

Vercel (*.vercel.app) ── hanya halaman depan proyek, tanpa token pengunjung
```

- **Dashboard disajikan oleh backend, bukan oleh Vercel.** Cookie sesi memakai `SameSite=Lax`, jadi cookie itu hanya terkirim bila dashboard dan API berada di satu host. Dashboard di `vercel.app` dengan backend di `trycloudflare.com` tidak akan bisa login.
- **Satu laptop, satu database.** Semua yang membuka dashboard melihat alarm dan riwayat yang sama secara langsung.
- **Pengunjung hanya bisa melihat.** QR membawa token pengunjung di fragmen URL (`#t=`). Fragmen tidak dikirim ke server, sehingga token tidak tercatat di log. Penguncian aksi dijaga di backend.
- **Token baru setiap kali launcher dijalankan.** QR lama otomatis tidak berlaku setelah restart, dan alamat tunnel juga berganti. Karena itu QR ditampilkan di layar, tidak dicetak permanen.

## Persiapan, sekali saja

1. Siapkan `.venv` dan `backend\requirements.txt` seperti biasa (lihat README). Paket `segno` dipakai untuk membuat QR.
2. Pasang `cloudflared`: `winget install --id Cloudflare.cloudflared`. Quick tunnel tidak butuh akun Cloudflare.
3. Pastikan `node_modules` ada di `frontend`. Launcher membangun ulang dashboard bila kodenya lebih baru dari hasil build.
4. Isi `DEMO_USERNAME` dan `DEMO_PASSWORD` di `backend\.env`. `DEMO_NAME` boleh dikosongkan. Contohnya ada di `backend\.env.example`. Setiap kali menyala, backend membuat akun demo dari isian ini, dan akun itulah yang dipakai tim untuk login di stand. Kalau isiannya kosong, tim tidak bisa login, dan halaman Login akan memberi tahu. Jangan menaruh sandinya di README, landing, atau QR.

## Hari pameran

1. Jalankan `run-pameran.bat`.
2. Launcher membangun dashboard bila perlu, membuka tunnel, lalu menyalakan backend dengan token pengunjung baru. `DASHBOARD_URL` untuk tombol Telegram diarahkan ke alamat tunnel.
3. Halaman QR terbuka di browser. Tampilkan di layar stand. Tim masuk lewat alamat `/login` yang tercetak di terminal, memakai akun demo dari `backend\.env`. Pengunjung yang memindai QR melihat halaman Login dengan tombol "Masuk sebagai pengunjung". Mereka hanya bisa melihat Pemantauan dan Riwayat, dan alarm tidak berbunyi di HP mereka.
4. Tekan `Ctrl+C` di jendela launcher untuk menghentikan backend dan tunnel sekaligus.

Bila internet di lokasi buruk, jalankan `run-pameran.bat --tanpa-tunnel`. Dashboard tetap bisa dibuka di laptop itu (`http://127.0.0.1:8000/login`), tetapi tidak dari HP pengunjung. Cadangan lama, `run-backend.bat` + `run-frontend.bat`, juga tetap bisa dipakai.

## Yang perlu diuji sebelum hari pameran

- Berapa HP yang bisa menonton video bersamaan sebelum laptop atau WiFi lokasi melambat. Setiap penonton menambah beban unggah.
- Buka QR dari HP lewat data seluler, bukan WiFi yang sama, untuk memastikan tunnel benar-benar terjangkau dari luar.
- Pasang tulisan "Area ini direkam untuk demo" di stand. Halaman QR sudah memuat kalimat itu.

## Berkas terkait

- `run-pameran.bat`, `tools/pameran.py`: launcher.
- `backend/app/main.py`: penyajian dashboard (`sajikan_dashboard`), didaftarkan sesudah semua router.
- `backend/app/core/config.py`: `FRONTEND_DIST`, `VISITOR_TOKEN`.
- `frontend/src/config.js`: hasil build memakai origin halaman sebagai alamat API.

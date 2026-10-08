# Fall Detection System — Nursing Home Monitoring

Sistem deteksi jatuh real-time untuk panti jompo menggunakan YOLO11 computer vision, FastAPI backend, dan React dashboard.

---

## Architecture

```
Kamera (RTSP/Webcam)
    │
    ▼
Camera Service ──▶ Inference Service (YOLO11) ──▶ State Machine
                                                       │
                              ┌─────────────────────────┤
                              ▼                         ▼
                    Telegram Notification        WebSocket Push
                              │                         │
                              ▼                         ▼
                        📱 Penjaga               🖥️ Dashboard
```

**Flow:** Kamera menangkap video → YOLO11 mendeteksi postur (normal/transitional/lying_on_ground) per frame → State machine menghitung durasi "lying_on_ground" → Jika melebihi threshold → Kirim alert Telegram + tampilkan di dashboard.

Lihat detail lengkap di [docs/architecture.md](docs/architecture.md).

---

## Project Structure

```
fall-detection/
├── ml/                          # Data science & training
│   ├── data/
│   │   ├── raw/                 # Video mentah (gitignored)
│   │   ├── extracted_frames/    # Frame hasil ekstraksi (gitignored)
│   │   └── processed/           # Dataset YOLO format + data.yaml
│   ├── scripts/
│   │   ├── extract_frames.py    # Ekstrak frame dari video
│   │   └── dedup_check.py       # Deteksi & hapus frame duplikat
│   ├── notebooks/               # Jupyter notebooks untuk eksplorasi
│   ├── models/                  # File .pt hasil training (gitignored)
│   └── training/
│       ├── config.yaml          # Hyperparameter training
│       └── train.py             # Script training YOLO11
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── main.py              # Entry point + lifespan (nyalakan kamera & pipeline)
│   │   ├── api/                 # REST endpoints — hanya MEMBACA state, tidak memilikinya
│   │   │   ├── alerts.py        # Riwayat alert
│   │   │   ├── cameras.py       # CRUD kamera, pemindaian, daftar perangkat, stream MJPEG
│   │   │   └── settings.py      # Konfigurasi runtime
│   │   ├── core/
│   │   │   ├── config.py        # Settings (env variables)
│   │   │   └── logging.py       # Logger + helper waktu UTC
│   │   ├── services/            # Komponen MURNI — tidak tahu-menahu soal FastAPI
│   │   │   ├── inference_service.py    # Load & run YOLO11 (sekali muat, inference berurutan)
│   │   │   ├── state_machine.py        # FSM fall detection
│   │   │   ├── camera_service.py       # Video capture + rotasi + sambung ulang
│   │   │   ├── overlay.py              # Gambar bounding box lalu encode JPEG
│   │   │   ├── local_devices.py        # Daftar webcam/Iriun beserta namanya
│   │   │   ├── network_scan.py         # Cari kamera IP di subnet lokal
│   │   │   ├── alert_service.py        # DB → WebSocket → Telegram + cooldown
│   │   │   └── notification_service.py # Telegram alerts
│   │   ├── runtime/             # State yang hidup selama aplikasi berjalan
│   │   │   ├── registry.py             # Kamera, FSM, task, frame & status terakhir
│   │   │   ├── camera_manager.py       # Nyalakan/matikan kamera saat runtime
│   │   │   └── detection_pipeline.py   # Loop utama per kamera
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic schemas
│   │   ├── db/
│   │   │   ├── database.py      # Engine & session (SQLite + SQLAlchemy async)
│   │   │   ├── models.py        # Tabel cameras & alerts
│   │   │   └── repository.py    # Satu-satunya tempat query SQL
│   │   └── websocket/
│   │       └── ws_manager.py    # WebSocket broadcast manager
│   ├── tests/
│   │   ├── test_state_machine.py
│   │   ├── test_detection_pipeline.py
│   │   └── test_camera_registry.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                    # React + Vite dashboard
│   │   ├── src/
│   │   │   ├── context/
│   │   │   │   └── ThemeContext.jsx      # Pengelola mode gelap/terang (Dark/Light Mode)
│   │   │   ├── pages/
│   │   │   │   ├── LandingPage.jsx       # Halaman sambutan utama (Landing Page)
│   │   │   │   ├── Login.jsx             # Halaman login caregiver
│   │   │   │   ├── SimulationDashboard.jsx # Dasbor simulasi live monitoring CCTV & YOLO11
│   │   │   ├── LiveCamera.jsx        # Pengujian kamera perangkat (HP/Laptop) via WebRTC
│   │   │   ├── Cameras.jsx           # Halaman manajemen daftar kamera CCTV
│   │   │   ├── AlertHistory.jsx      # Riwayat notifikasi insiden jatuh
│   │   │   └── Settings.jsx          # Pengaturan sistem dan threshold durasi
│   │   ├── components/
│   │   │   └── DashboardLayout.jsx   # Tata letak responsif dengan sidebar collapsible
│   │   ├── App.jsx                   # Pusat navigasi & rute aplikasi (React Router)
│   │   ├── main.jsx                  # Entry point React
│   │   └── index.css                 # Konfigurasi Tailwind CSS
│   ├── public/                       # Aset publik, favicon, dan ikon
│   ├── package.json                  # Dependensi dan skrip npm
│   ├── vite.config.js                # Konfigurasi build Vite
│   └── Dockerfile                    # Konfigurasi Docker frontend
│
├── docs/
│   ├── architecture.md          # Diagram arsitektur sistem
│   └── api.md                   # Dokumentasi endpoint API
│
├── deployment/
│   ├── docker-compose.yml       # Orchestrasi backend + frontend
│   └── .env.example             # Template environment variables
│
├── tools/
│   └── check_camera.py          # Uji satu sumber kamera dalam 3 detik
│
├── run-backend.bat              # Jalankan backend (cek venv, model, kamera dulu)
├── run-frontend.bat             # Jalankan dashboard
├── TESTING.md                   # Panduan pengujian manual langkah demi langkah
├── .gitignore
└── README.md                    # ← Anda di sini
```

---

## Quick Start (Development Lokal)

Seluruh perintah di bawah ditulis untuk **Windows PowerShell** dan dijalankan dari
**folder root repo**. Semuanya sudah diuji pada clone yang benar-benar baru.

> **Branch mana yang harus dipakai**
>
> | Tujuan | Branch |
> |---|---|
> | Menjalankan sistem lengkap (dashboard + backend) | `integration` |
> | Membaca atau mengerjakan kode backend saja | `backend` |
>
> Branch `backend` sengaja hanya memuat sisi backend. Frontend di dalamnya masih versi
> lama dan **belum punya** halaman Kelola Kamera, Simulasi Live, maupun Testing Kamera HP
> — ketiganya ada di `integration`, tempat kerja backend dan frontend disatukan.
>
> Jadi kalau kamu ingin **memakai** sistemnya, bukan sekadar membaca kodenya, pakai
> `integration`. Seluruh langkah di bawah sama persis untuk kedua branch.

### Yang harus terpasang lebih dulu

| Kebutuhan | Versi | Cara memastikan |
|---|---|---|
| Python | **3.12** | `py -0p` — harus ada baris `-3.12` |
| Node.js | 18+ | `node --version` |
| Git | — | `git --version` |

> **Harus 3.12, bukan 3.13 atau 3.14.** `ultralytics` belum menyediakan wheel untuk
> versi yang lebih baru, dan pemasangannya akan gagal di tengah jalan.

### 1. Clone

```powershell
git clone https://github.com/0Raja0-RA/nursing-home-fall-detection.git
cd nursing-home-fall-detection
git switch integration    # atau: git switch backend, lihat catatan di atas
```

### 2. Pasang dependensi Python

Virtual environment dibuat di **root repo**, bukan di dalam `backend/`. Launcher dan
seluruh perintah di dokumen ini mengandalkan letak itu.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Unduhannya sekitar 1 GB (PyTorch ikut terbawa oleh `ultralytics`), jadi siapkan waktu
beberapa menit. Tidak perlu `activate` — semua perintah memanggil `.venv\Scripts\python.exe`
secara langsung, sehingga tidak ada kebingungan Python mana yang sedang dipakai.

Pastikan berhasil:

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q
```

Semua uji harus lulus. Tahap ini belum butuh model, kamera, maupun internet.

### 3. Taruh file model

File bobot `.pt` **tidak ikut di repo** (lihat `.gitignore`). Minta `best.pt` hasil
EXP-006 ke anggota ML, lalu taruh tepat di:

```
ml\models\fall_detection\weights\best.pt
```

Pastikan file yang benar — bobot COCO bawaan YOLO berukuran mirip dan mudah tertukar:

```powershell
.venv\Scripts\python.exe -c "from ultralytics import YOLO; print(YOLO('ml/models/fall_detection/weights/best.pt').names)"
```

Harus muncul tepat `{0: 'normal', 1: 'transitional', 2: 'lying_on_ground'}`. Kalau yang
muncul 80 kelas, itu bobot COCO, bukan model tim.

### 4. Jalankan

```powershell
.\run-backend.bat
```

Di jendela terminal lain:

```powershell
.\run-frontend.bat
```

`run-frontend.bat` menjalankan `npm install` sendiri kalau `node_modules` belum ada.

| Alamat | Isi |
|---|---|
| http://localhost:5173 | Dashboard |
| http://127.0.0.1:8000/docs | Dokumentasi API interaktif |
| http://127.0.0.1:8000/api/cameras/cam-01/stream | Video + bounding box |

Kamera diatur dari dashboard, bukan dari berkas — lihat [Mengelola Kamera](#mengelola-kamera).
Saat pertama dijalankan, satu kamera dibuat otomatis dari `CAMERA_SOURCE` di
`run-backend.bat` (bawaannya `0`, yaitu webcam laptop).

### 5. (Opsional) Notifikasi Telegram

Tanpa langkah ini sistem tetap berjalan penuh; alert tersimpan dan muncul di dashboard,
hanya notifikasi ke HP yang tidak dikirim.

```powershell
copy backend\.env.example backend\.env
```

Isi `TELEGRAM_BOT_TOKEN` dengan token dari [@BotFather](https://t.me/BotFather), lalu
ambil `chat_id` tujuannya:

```powershell
.venv\Scripts\python.exe tools\get_chat_id.py
.venv\Scripts\python.exe tools\get_chat_id.py --simpan <chat_id>
```

Jalankan ulang backend, lalu uji:

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/settings/test-telegram
```

> Tulis **`curl.exe`**, bukan `curl`. Di PowerShell `curl` adalah alias untuk
> `Invoke-WebRequest` yang tidak mengenal `-X`. Alternatifnya:
> `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/settings/test-telegram`

Langkah lengkapnya — termasuk kenapa bot harus disapa lebih dulu dan apa yang harus
dilakukan kalau `chat_id` tidak muncul — ada di **[TESTING.md](TESTING.md)**.

Saat ada yang jatuh, grup menerima **foto** kejadian lengkap dengan bounding box, nama
kamar, durasi, dan jam. Kegagalan kirim tidak membatalkan alert: barisnya tetap tersimpan
dengan `notified: false`, supaya kegagalan terlihat alih-alih hilang diam-diam.

### 6. (Opsional) Training ulang model

```powershell
.venv\Scripts\python.exe ml\training\train.py --config ml\training\config.yaml
```

Perlu dataset format YOLO di `ml/data/processed/`. Model hasilnya tersimpan di
`ml/models/fall_detection/weights/`.

---

## Docker Deployment

> **Belum diuji, dan diketahui belum sesuai.** Berkas Compose dan Dockerfile masih dari
> kerangka awal proyek: `backend/Dockerfile` memakai `python:3.11-slim`, padahal
> `ultralytics` butuh 3.12. Jalur Docker juga belum menangani akses kamera dari dalam
> container, yang di Windows tidak sesederhana memasang volume.
>
> Untuk sekarang, pakai `run-backend.bat` dan `run-frontend.bat` di Quick Start.

```bash
cd deployment
docker compose up --build
```

---

## Testing

```powershell
.venv\Scripts\python.exe -m pytest backend\tests -q
```

**52 uji**, dan semuanya berjalan tanpa kamera, tanpa model, tanpa token, dan tanpa
koneksi internet — Telegram digantikan server HTTP lokal, kamera dan model digantikan
objek tiruan. Jadi anggota tim mana pun bisa menjalankannya segera setelah `pip install`,
sebelum meminta file model ke siapa pun.

| Berkas | Yang dijaga |
|---|---|
| `test_state_machine.py` | Debounce, grace period, observasi ragu-ragu, alert tidak berulang, dan jeda pipeline yang tidak boleh terhitung sebagai durasi tergeletak |
| `test_detection_pipeline.py` | Loop deteksi dengan kamera & model tiruan |
| `test_camera_registry.py` | Validasi sumber kamera, repository, pemetaan subnet pemindai, dan model YOLO yang hanya boleh dimuat sekali meski beberapa kamera menyala bersamaan |
| `test_telegram.py` | Pemilihan sendPhoto/sendMessage, escape HTML, percobaan ulang, penandaan simulasi, dan token yang tidak boleh bocor ke log |
| `test_alert_service.py` | Urutan DB → WebSocket → Telegram, cooldown, kegagalan Telegram yang tidak boleh membatalkan alert |

Pengujian manual — menghubungkan kamera HP, memastikan bounding box muncul, menguji
Telegram, dan daftar masalah yang sering terjadi — ada di **[TESTING.md](TESTING.md)**.

---

## API Endpoints

| Method | Endpoint                     | Description                                        |
| ------ | ---------------------------- | -------------------------------------------------- |
| GET    | `/`                          | Health check                                        |
| GET    | `/api/alerts/`               | Daftar alert (pagination)                           |
| GET    | `/api/alerts/count`          | Hitung total alert                                  |
| GET    | `/api/alerts/{id}`           | Detail satu alert                                   |
| PUT    | `/api/alerts/{id}/ack`       | Acknowledge alert                                   |
| GET    | `/api/cameras/`              | Daftar kamera + status runtime-nya                  |
| POST   | `/api/cameras/`              | Daftarkan kamera baru (sumber divalidasi dulu)      |
| GET    | `/api/cameras/{id}`          | Satu kamera                                         |
| PATCH  | `/api/cameras/{id}`          | Ubah nama/sumber/rotasi/enabled, pipeline restart   |
| DELETE | `/api/cameras/{id}`          | Matikan dan hapus kamera                            |
| GET    | `/api/cameras/{id}/stream`   | Video MJPEG dengan bounding box tergambar           |
| GET    | `/api/cameras/devices`       | Kamera lokal (webcam, Iriun) beserta namanya        |
| POST   | `/api/cameras/scan`          | Pindai subnet lokal untuk mencari kamera IP         |
| GET    | `/api/settings/`             | Konfigurasi aktif                                   |
| PUT    | `/api/settings/threshold`    | Update threshold durasi                             |
| POST   | `/api/cameras/{id}/simulate-fall` | Paksa simulasi jatuh (untuk demo)              |
| POST   | `/api/settings/test-telegram`| Kirim notifikasi uji ke Telegram                    |
| WS     | `/ws`                        | WebSocket live updates                              |

Dokumentasi interaktif tersedia di `http://127.0.0.1:8000/docs` saat server berjalan.

---

## Mengelola Kamera

Daftar kamera disimpan di database, **bukan** di environment variable, dan diatur lewat
halaman **Kelola Kamera** di dashboard. Alasannya praktis: alamat IP kamera HP berubah
setiap kali berpindah jaringan WiFi, dan mengubahnya tidak boleh berarti menyunting kode
lalu me-restart server.

| Jenis sumber | Nilai | Catatan |
| --- | --- | --- |
| Webcam laptop | `0` | |
| Iriun (kamera HP sebagai webcam) | `1`, `2`, `3`, `4` | tekan **Pindai** untuk melihat namanya |
| IP Webcam (Android) | `http://IP-HP:8080/video` | jangan lupa `/video` di belakang |
| RTSP / CCTV | `rtsp://IP:554/...` | |
| File video | path ke `.mp4` | untuk uji ulang yang bisa diulang persis |

Hal yang perlu diketahui:

- **Sumber divalidasi sebelum disimpan.** Alamat yang tidak bisa dihubungi, atau yang
  mengembalikan halaman web alih-alih aliran video, ditolak berikut alasannya.
- **Rotasi diatur per kamera**, bukan global — kamera HP sering butuh 90°, webcam tidak.
- **Tombol Pindai** mencari dua-duanya sekaligus: perangkat lokal dan perangkat di subnet
  jaringan, lalu alamatnya tinggal diklik.
- **Batas 4 kamera** (`MAX_CAMERAS`). Inference berjalan di CPU, jadi tiap kamera menambah
  beban secara linear.
- `CAMERA_SOURCE` di `run-backend.bat` hanya dipakai untuk membuat kamera **pertama** saat
  database masih kosong. Setelah itu diabaikan.

Panduan pengujian langkah demi langkah ada di **[TESTING.md](TESTING.md)**.

---

## Simulasi Jatuh

Model masih sering membaca orang yang berbaring sebagai `transitional` di luar ruangan
dataset URFD, sehingga alarm sungguhan sulit dipicu dengan tubuh. Tombol **Trigger
Simulasi Orang Jatuh** di halaman Simulasi Live menutup celah itu untuk keperluan demo.

Yang disimulasikan **hanya keluaran detektor**. Sisanya berjalan apa adanya:

```
tombol → observasi ditimpa jadi "postur pemicu" selama beberapa detik
       → state machine menghitung durasinya sendiri
       → debounce dan cooldown tetap berlaku
       → alert tersimpan, disiarkan ke dashboard, dikirim ke Telegram beserta
         foto frame kamera saat itu juga
```

Dengan begitu yang ditunjukkan saat demo adalah mekanisme yang memang dibangun, bukan
jalan pintasnya. Kalimat yang bisa disampaikan ke penguji: *"yang kami simulasikan hanya
keluaran modelnya, karena modelnya belum optimal di luar ruangan dataset. Seluruh rantai
sesudahnya berjalan apa adanya."*

Alert hasil simulasi **selalu bisa dibedakan** dari kejadian nyata:

| Di mana | Bentuknya |
|---|---|
| Database | kolom `simulated = true` |
| Pesan alert | diawali `[SIMULASI]` |
| Telegram | judul **SIMULASI — BUKAN KEJADIAN SUNGGUHAN** di baris pertama |
| Riwayat Insiden | badge kuning *Simulasi* |

Itu disengaja, bukan sekadar kerapian: sistem deteksi jatuh yang bisa memunculkan alarm
tanpa meninggalkan jejak membuat seluruh riwayat insidennya kehilangan nilai sebagai
bukti — baik bagi perawat maupun bagi penguji.

Lewat API:

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/cameras/cam-01/simulate-fall
```

> `ALERT_COOLDOWN_SEC` di `run-backend.bat` diturunkan ke **10 detik**, karena saat demo
> wajar diminta mengulang simulasi beberapa kali berturut-turut. Dengan nilai bawaan 60
> detik, tekanan tombol kedua tidak mengirim apa pun dan sistemnya terlihat seperti rusak.
> Kembalikan ke 60 untuk pemakaian sungguhan.

---

## State Machine

```
MONITORING ──[postur pemicu]──▶ POSSIBLE_FALL ──[durasi ≥ threshold]──▶ CONFIRMED_FALL
     ▲                              │                                         │
     └──[postur bukan pemicu, N frame berturut-turut]──┴─────────────────────┘

UNKNOWN ◀──[kamera offline]
```

| State | Arti |
| --- | --- |
| `MONITORING` | Normal, tidak ada indikasi jatuh |
| `POSSIBLE_FALL` | Postur pemicu terdeteksi, timer berjalan |
| `CONFIRMED_FALL` | Durasi melewati ambang → simpan alert, siarkan ke dashboard, kirim Telegram |
| `UNKNOWN` | Kamera tidak mengirim gambar |

Pipeline tidak hanya mengenal "jatuh" dan "tidak jatuh". Setiap frame diterjemahkan jadi
salah satu observasi berikut, dan perbedaannya penting:

| Observasi | Kapan | Perlakuan terhadap timer |
| --- | --- | --- |
| `TRIGGER_POSTURE` | postur ada di `TRIGGER_CLASSES`, confidence ≥ ambang | maju |
| `NON_TRIGGER_POSTURE` | postur lain, confidence ≥ ambang | mundur ke nol, setelah debounce |
| `UNCERTAIN` | ada deteksi tapi confidence di bawah ambang | berhenti di tempat |
| `PERSON_LOST` | model tidak menemukan siapa pun | bertahan selama grace period |
| `OFFLINE` | kamera tidak mengirim frame | state jadi `UNKNOWN` |

Dua di antaranya menjawab kasus yang justru paling berbahaya. **Orang hilang dari deteksi
bukan berarti orang itu sudah bangun** — lansia yang tergeletak lalu tertutup selimut atau
kursi akan membuat detektor kehilangan dia, dan tanpa grace period timernya kembali ke nol
tepat di saat paling gawat. Begitu pula deteksi ragu-ragu: ia tidak boleh dihitung sebagai
"aman".

Pengaturan yang relevan (semuanya bisa ditimpa lewat environment):

| Setting | Bawaan | Arti |
| --- | --- | --- |
| `TRIGGER_CLASSES` | `["lying_on_ground"]` | postur yang menjalankan timer |
| `FALL_DURATION_THRESHOLD` | `10.0` detik | ambang `CONFIRMED_FALL` |
| `POSSIBLE_FALL_THRESHOLD` | `2.0` detik | ambang masuk `POSSIBLE_FALL` |
| `DEBOUNCE_FRAMES` | `5` | frame berturut-turut sebelum timer direset |
| `GRACE_PERIOD_SEC` | `3.0` | berapa lama timer bertahan saat orang hilang dari deteksi |
| `ALERT_COOLDOWN_SEC` | `60.0` | jeda minimal antar alert untuk satu kamera |
| `CONFIDENCE_THRESHOLD` | `0.5` | ambang deteksi dianggap meyakinkan |
| `MAX_CAMERAS` | `4` | batas jumlah kamera terdaftar |

---

## 📝 License

[MIT](LICENSE)

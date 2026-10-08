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
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx    # Live monitoring semua kamera
│   │   │   ├── AlertHistory.jsx # Riwayat notifikasi jatuh
│   │   │   └── Settings.jsx     # Atur threshold durasi
│   │   ├── components/
│   │   │   ├── CameraFeedCard.jsx  # Kartu status per kamera
│   │   │   ├── AlertBanner.jsx     # Banner notifikasi darurat
│   │   │   ├── StatusBadge.jsx     # Badge safe/warning/danger
│   │   │   └── ThresholdSlider.jsx # Slider threshold durasi
│   │   ├── services/
│   │   │   ├── api.js           # Axios API client
│   │   │   └── websocket.js     # WebSocket client
│   │   └── hooks/
│   │       └── useWebSocket.js  # React hook WebSocket
│   ├── package.json
│   ├── vite.config.js
│   └── Dockerfile
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

> **Mau langsung menguji sistemnya?** Jalankan `run-backend.bat` dan `run-frontend.bat`,
> lalu ikuti **[TESTING.md](TESTING.md)**. Dokumen itu memuat cara menghubungkan kamera HP,
> cara memastikan bounding box muncul, dan daftar masalah yang sering terjadi.
>
> Catatan: butuh **Python 3.12** (bukan 3.13/3.14, karena `ultralytics` belum mendukungnya),
> dan virtual environment dibuat di **root repo** (`.venv`), bukan di dalam `backend/`.

### Prerequisites

- **Python** 3.12
- **Node.js** 18+
- **Git**

### 1. Clone & Setup Environment

```bash
git clone <repo-url>
cd fall-detection
```

Copy environment variables:

```bash
cp deployment/.env.example backend/.env
```

Edit `backend/.env` dan isi:

- `TELEGRAM_BOT_TOKEN` — Token dari [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` — Chat ID tujuan notifikasi

> **Status Telegram: belum tersambung.** `notification_service.py` sudah bisa mengirim
> pesan, tapi `alert_service.py` belum memanggilnya, jadi kolom `notified` pada alert
> selalu bernilai 0. Alert tetap tersimpan ke database dan muncul di dashboard lewat
> WebSocket. Mengisi dua variabel di atas sekarang belum menghasilkan notifikasi apa pun.

Kamera **tidak** diatur di sini — lihat bagian [Mengelola Kamera](#mengelola-kamera).

### 2. Jalankan Backend

```bash
cd backend

# Buat virtual environment
python -m venv .venv

# Aktivasi (Windows)
.venv\Scripts\activate

# Aktivasi (Linux/Mac)
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Jalankan server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend akan berjalan di **http://localhost:8000**

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 3. Jalankan Frontend

```bash
cd frontend

# Install dependencies
npm install

# Jalankan dev server
npm run dev
```

Frontend akan berjalan di **http://localhost:5173**

> Vite sudah dikonfigurasi untuk proxy `/api` dan `/ws` ke backend di port 8000.

### 4. (Opsional) Training Model

```bash
cd ml/training

# Pastikan sudah ada dataset di ml/data/processed/
# dengan struktur YOLO format (images/ + labels/)

python train.py --config config.yaml
```

Model `best.pt` akan tersimpan di `ml/models/fall_detection/weights/`.

---

## Docker Deployment

```bash
cd deployment

# Build & jalankan semua service
docker compose up --build

# Atau di background
docker compose up --build -d
```

- Backend: http://localhost:8000
- Frontend: http://localhost:5173

---

## Testing

Uji otomatis (tidak butuh kamera, model, maupun jaringan):

```bash
.venv\Scripts\python.exe -m pytest backend/tests -q
```

Yang dijaga: perilaku state machine (debounce, grace period, observasi ragu-ragu, alert
tidak berulang), detection pipeline dengan kamera & model tiruan, validasi sumber kamera,
repository kamera, pemetaan subnet pemindai, dan model YOLO yang hanya boleh dimuat sekali
meski beberapa kamera menyala bersamaan.

Pengujian manual — menghubungkan kamera HP, memastikan bounding box muncul, dan daftar
masalah yang sering terjadi — ada di **[TESTING.md](TESTING.md)**.

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

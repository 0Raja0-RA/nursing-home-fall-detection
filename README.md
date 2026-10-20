# Fall Detection System — Nursing Home Monitoring

Sistem deteksi jatuh real-time untuk panti jompo menggunakan **Dual-Engine Computer Vision** (Custom YOLO11 Bounding Box & YOLO11-Pose Kinematics), **FastAPI Backend** dengan Finite State Machine (FSM) 10-detik, dan **React Dashboard**.

---

## 🏗️ System Architecture

```
                  ┌─────────────────────────────────────────┐
                  │          Kamera (RTSP / Webcam)         │
                  └────────────────────┬────────────────────┘
                                       │
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │       Camera Service (OpenCV Loop)      │
                  └────────────────────┬────────────────────┘
                                       │
                    ┌──────────────────┴──────────────────┐
                    ▼                                     ▼
         [ Mode Bounding Box ]                  [ Mode Pose Estimation ]
        Custom YOLO11n (EXP-006)               YOLO11n-Pose (17 Keypoints)
       • Bounding box classification         • Sudut tulang belakang (θ < 20°)
       • Super cepat (290+ FPS)              • Kebal false alarm kasur/sofa
       • Cocok untuk koridor/lorong          • Cocok untuk kamar tidur
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       │ Posture: normal / trans / lying
                                       ▼
                  ┌─────────────────────────────────────────┐
                  │   State Machine (FSM Timer 10 Detik)    │
                  │  MONITORING ──▶ POSSIBLE ──▶ CONFIRMED  │
                  └────────────────────┬────────────────────┘
                                       │
                     ┌─────────────────┴─────────────────┐
                     ▼                                   ▼
          📱 Telegram Alert Service             🖥️ WebSocket Push Service
         (Foto Snapshot + Detail Durasi)          (Live Posture + Status)
```

**Alur Kerja (Flow):**
1. **Capture:** Kamera menangkap video frame secara real-time.
2. **Dual-Engine Inference:** Pengguna dapat memilih mesin deteksi:
   - **Bounding Box:** Klasifikasi postur langsung dari deteksi kotak objek.
   - **Pose Estimation:** Ekstraksi 17 titik sendi tubuh dan analisis sudut kemiringan tulang belakang terhadap bidang lantai ($\theta$).
3. **State Machine (FSM):** Saat postur `lying_on_ground` terdeteksi, stopwatch aktif ke state `POSSIBLE_FALL`. Jika posisi terkapar bertahan selama $\ge 10$ detik, sistem mengonfirmasi ke `CONFIRMED_FALL`. Jika pasien bangkit sebelum 10 detik, timer di-reset.
4. **Alerting:** Begitu `CONFIRMED_FALL` tercapai, sistem memicu notifikasi darurat Telegram kepada penjaga dan push update real-time ke web dashboard.

Lihat detail lengkap di [docs/architecture.md](docs/architecture.md).

---

## Project Structure

```
fall-detection/
├── ml/                          # Data science, modeling & training
│   ├── data/
│   │   ├── raw/                 # Video mentah (gitignored)
│   │   ├── extracted_frames/    # Frame hasil ekstraksi (gitignored)
│   │   └── processed/           # Dataset YOLO format + data.yaml
│   ├── scripts/
│   │   ├── extract_frames.py    # Ekstrak frame dari video
│   │   ├── dedup_check.py       # Deteksi & hapus frame duplikat
│   │   ├── demo_pose_fall.py    # Live demo kamera + visualisasi sudut skeleton
│   │   └── tune_pose_fall.py    # Script grid search kinematic threshold
│   ├── notebooks/
│   │   └── pose_tuning.ipynb    # Notebook eksperimen EXP-009 (Pose Benchmark)
│   ├── models/                  # File .pt hasil training (gitignored)
│   ├── DATA_PREPROCESSING.md    # Dokumentasi lengkap pipeline & konsep preprocessing
│   └── training/
│       ├── config.yaml          # Hyperparameter training
│       ├── train.py             # Script training YOLO11
│       ├── experiments.csv      # Riwayat metrik kuantitatif eksperimen
│       └── EXPERIMENTS.md       # Laporan ilmiah mendalam (EXP-001 s.d. EXP-010)
│
├── backend/                     # FastAPI backend
│   ├── app/
│   │   ├── main.py              # Entry point FastAPI
│   │   ├── api/                 # REST endpoints
│   │   │   ├── alerts.py        # CRUD alert history
│   │   │   ├── cameras.py       # Status kamera
│   │   │   └── settings.py      # Konfigurasi runtime
│   │   ├── core/
│   │   │   └── config.py        # Settings (env variables)
│   │   ├── services/
│   │   │   ├── inference_service.py    # Load & run YOLO11
│   │   │   ├── state_machine.py        # FSM fall detection
│   │   │   ├── notification_service.py # Telegram alerts
│   │   │   └── camera_service.py       # Video capture
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic schemas
│   │   ├── db/
│   │   │   └── database.py      # SQLite + SQLAlchemy async
│   │   └── websocket/
│   │       └── ws_manager.py    # WebSocket broadcast manager
│   ├── tests/
│   │   └── test_state_machine.py
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
├── .gitignore
└── README.md                    # ← Anda di sini
```

---

## Quick Start (Development Lokal)

### Prerequisites

- **Python** 3.10+
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

### 4. (Opsional) Menjalankan Model & Eksperimen

#### A. Menjalankan Live Pose Demo (Webcam / Iriun Phone Camera):
```bash
# Jalankan demo deteksi pose real-time dengan kamera bawaan / webcam
python ml/scripts/demo_pose_fall.py --source 0

# Untuk kamera eksternal / Iriun Webcam:
python ml/scripts/demo_pose_fall.py --source 1
```

#### B. Menjalankan Training Bounding Box Custom (EXP-006):
```bash
cd ml/training
python train.py --config config.yaml
```
Model `best.pt` akan tersimpan di `ml/models/fall_detection/weights/`.

---

## 🧠 Model Paradigms: Bounding Box vs Pose Estimation

Sistem ini mengimplementasikan dua paradigma computer vision yang dapat disesuaikan dengan kebutuhan area pemantauan:

| Parameter | **Bounding Box Detection (Custom YOLO11n)** | **Kinematic Pose Estimation (YOLO11n-Pose)** |
| :--- | :--- | :--- |
| **Model** | `best.pt` (EXP-006 Champion) | `yolo11n-pose.pt` (EXP-009) |
| **Metode** | Klasifikasi kotak objek (x, y, w, h) | 17 Keypoints sendi + Sudut tulang belakang $\theta$ |
| **Formula Deteksi** | Direct class probability: 0 (Normal), 1 (Trans), 2 (Lying) | $\theta = \arctan2(|\Delta y|, |\Delta x|) \times \frac{180}{\pi}$ |
| **Batas Threshold** | Confidence $\ge 0.50$ | Fall: $\theta < 20.0^\circ$ \| Trans: $\theta < 60.0^\circ$ \| AR $> 1.15$ |
| **Kecepatan** | **~290+ FPS** (3.4 ms/frame) | **~65+ FPS** (15.3 ms/frame) |
| **Ketahanan Clutter** | Rentan false positive jika ada kasur/bantal rebah | **Kebal false positive** (wajib ada struktur sendi manusia) |
| **Rekomendasi Area** | **Koridor & Lorong Bebas Furnitur** | **Kamar Tidur & Ruang Keluarga Panti Jompo** |

Detail riwayat riset dari EXP-001 hingga EXP-009 dapat dilihat di [ml/training/EXPERIMENTS.md](ml/training/EXPERIMENTS.md).

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

```bash
cd backend
pytest tests/ -v
```

---

## API Endpoints

| Method | Endpoint                    | Description               |
| ------ | --------------------------- | ------------------------- |
| GET    | `/`                       | Health check              |
| GET    | `/api/alerts/`            | Daftar alert (pagination) |
| GET    | `/api/alerts/count`       | Hitung total alert        |
| GET    | `/api/alerts/{id}`        | Detail satu alert         |
| PUT    | `/api/alerts/{id}/ack`    | Acknowledge alert         |
| GET    | `/api/cameras/`           | Status semua kamera       |
| GET    | `/api/cameras/{id}`       | Status satu kamera        |
| GET    | `/api/settings/`          | Konfigurasi aktif         |
| PUT    | `/api/settings/threshold` | Update threshold durasi   |
| WS     | `/ws`                     | WebSocket live updates    |

Dokumentasi lengkap: [docs/api.md](docs/api.md)

---

## State Machine

```
MONITORING ──[lying_on_ground]──▶ POSSIBLE_FALL ──[duration ≥ threshold]──▶ CONFIRMED_FALL
     ▲                              │                                         │
     └──[posture = normal/trans.]──┘                                         │
     └──[acknowledged/reset]─────────────────────────────────────────────┘
```

- **MONITORING**: Normal — tidak ada indikasi jatuh.
- **POSSIBLE_FALL**: Postur "lying_on_ground" terdeteksi, timer berjalan.
- **CONFIRMED_FALL**: Durasi melebihi threshold → kirim Telegram + alert dashboard.

---

## 📝 License

[MIT](LICENSE)

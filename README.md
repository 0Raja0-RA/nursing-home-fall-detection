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

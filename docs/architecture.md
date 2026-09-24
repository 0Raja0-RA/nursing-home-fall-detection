# Architecture Overview

Dokumentasi arsitektur sistem Fall Detection untuk panti jompo.

## System Overview

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐
│  IP Camera  │     │                    BACKEND (FastAPI)                  │
│  / Webcam   │────▶│                                                      │
│  (RTSP)     │     │  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
└─────────────┘     │  │  Camera    │  │  Inference   │  │   State     │  │
                    │  │  Service   │──│  Service     │──│   Machine   │  │
                    │  │ (capture)  │  │ (YOLO11 .pt) │  │  (per cam)  │  │
                    │  └────────────┘  └──────────────┘  └──────┬──────┘  │
                    │                                           │         │
                    │                    ┌──────────────────────┤         │
                    │                    ▼                      ▼         │
                    │  ┌─────────────────────┐  ┌────────────────────┐   │
                    │  │  Notification       │  │   WebSocket        │   │
                    │  │  Service (Telegram) │  │   Manager          │   │
                    │  └─────────────────────┘  └────────┬───────────┘   │
                    │                                    │               │
                    │  ┌─────────────────────┐           │               │
                    │  │  SQLite Database    │           │               │
                    │  │  (alert history)    │           │               │
                    │  └─────────────────────┘           │               │
                    │                                    │               │
                    │  ┌─────────────────────┐           │               │
                    │  │  REST API           │           │               │
                    │  │  /api/alerts        │           │               │
                    │  │  /api/cameras       │           │               │
                    │  │  /api/settings      │           │               │
                    │  └─────────┬───────────┘           │               │
                    └────────────┼────────────────────────┼───────────────┘
                                 │                        │
                    ┌────────────┼────────────────────────┼───────────────┐
                    │            ▼          FRONTEND      ▼               │
                    │  ┌─────────────────┐  ┌────────────────────┐       │
                    │  │  API Client     │  │  WebSocket Client  │       │
                    │  │  (axios)        │  │  (auto-reconnect)  │       │
                    │  └────────┬────────┘  └────────┬───────────┘       │
                    │           │                     │                   │
                    │  ┌────────┴─────────────────────┴───────────┐      │
                    │  │              React Dashboard              │      │
                    │  │  ┌───────────┐ ┌──────────┐ ┌─────────┐ │      │
                    │  │  │ Dashboard │ │  Alert   │ │Settings │ │      │
                    │  │  │ (live)    │ │ History  │ │(thresh) │ │      │
                    │  │  └───────────┘ └──────────┘ └─────────┘ │      │
                    │  └──────────────────────────────────────────┘      │
                    └───────────────────────────────────────────────────┘
```

## Development Phase

```mermaid
graph LR
    A[Collect Video] --> B[Extract Frames]
    B --> C[Label Dataset]
    C --> D[Train YOLO11]
    D --> E[Export best.pt]
    E --> F[Integrate with Backend]
```

1. **Data Collection**: Download UR Fall Detection Dataset.
2. **Frame Extraction**: `ml/scripts/extract_frames.py` → frame individual.
3. **Dedup**: `ml/scripts/dedup_check.py` → hapus frame redundan.
4. **Label Conversion**: Convert UR Fall labels (-1/0/1) ke YOLO format (0/1/2).
5. **Training**: `ml/training/train.py` dengan config di `config.yaml`.
6. **Export**: Model `best.pt` tersimpan di `ml/models/`.

## Real-Time Deployment Phase

```mermaid
graph TD
    CAM[Camera/RTSP] --> CS[Camera Service]
    CS -->|frame| IS[Inference Service]
    IS -->|posture + confidence| SM[State Machine]
    SM -->|CONFIRMED_FALL| NS[Notification Service]
    SM -->|status_update| WS[WebSocket Manager]
    NS -->|alert| TG[Telegram Bot]
    WS -->|real-time| FE[Frontend Dashboard]
    SM -->|alert record| DB[(SQLite)]
```

## State Machine Diagram

```mermaid
stateDiagram-v2
    [*] --> MONITORING
    MONITORING --> POSSIBLE_FALL : lying_on_ground detected
    POSSIBLE_FALL --> CONFIRMED_FALL : duration >= threshold
    POSSIBLE_FALL --> MONITORING : posture = normal / transitional
    CONFIRMED_FALL --> MONITORING : acknowledged / reset
```

## Tech Stack

| Layer     | Technology             |
|-----------|------------------------|
| ML        | YOLO11 (ultralytics)   |
| Backend   | FastAPI + uvicorn      |
| Database  | SQLite (aiosqlite)     |
| Frontend  | React + Vite           |
| Notif     | Telegram Bot API       |
| Deploy    | Docker Compose         |

# API Documentation

Dokumentasi endpoint REST API dan WebSocket untuk Fall Detection Backend.

Base URL: `http://localhost:8000`

---

## Health Check

### `GET /`

Cek apakah backend berjalan.

**Response:**
```json
{
  "status": "ok",
  "service": "fall-detection-backend"
}
```

---

## Alerts

### `GET /api/alerts/`

Ambil daftar alert dengan pagination.

| Parameter      | Type    | Default | Description                        |
|----------------|---------|---------|------------------------------------|
| `skip`         | int     | 0       | Offset pagination                  |
| `limit`        | int     | 20      | Jumlah item per halaman (1-100)    |
| `acknowledged` | bool    | null    | Filter: true/false/null (semua)    |

**Response:** `Array<Alert>`

```json
[
  {
    "id": 1,
    "camera_id": "cam-lobby",
    "severity": "critical",
    "message": "Fall detected at lobby camera",
    "fall_duration": 12.5,
    "acknowledged": false,
    "created_at": "2026-09-23T13:00:00",
    "acknowledged_at": null
  }
]
```

### `GET /api/alerts/count`

Hitung total alert.

| Parameter      | Type | Description                     |
|----------------|------|---------------------------------|
| `acknowledged` | bool | Filter (opsional)               |

**Response:**
```json
{ "count": 42 }
```

### `GET /api/alerts/{alert_id}`

Detail satu alert.

### `PUT /api/alerts/{alert_id}/ack`

Tandai alert sebagai sudah ditangani.

**Response:** Alert object dengan `acknowledged: true`.

---

## Cameras

### `GET /api/cameras/`

Daftar semua kamera beserta status real-time.

**Response:** `Array<CameraStatus>`

```json
[
  {
    "camera_id": "cam-lobby",
    "is_active": true,
    "current_posture": "normal",
    "fall_state": "monitoring",
    "fall_duration": 0.0,
    "confidence": 0.92,
    "fps": 14.8,
    "last_frame_at": "2026-09-23T13:05:00"
  }
]
```

### `GET /api/cameras/{camera_id}`

Status satu kamera.

---

## Settings

### `GET /api/settings/`

Ambil konfigurasi aktif.

**Response:**
```json
{
  "fall_duration_threshold": 10.0,
  "possible_fall_threshold": 2.0,
  "confidence_threshold": 0.5,
  "camera_source": "0"
}
```

### `PUT /api/settings/threshold`

Update threshold durasi falling.

**Request Body:**
```json
{
  "fall_duration_threshold": 15.0
}
```

**Constraints:** `1 < fall_duration_threshold <= 60`

---

## WebSocket

### `WS /ws`

Koneksi WebSocket untuk real-time updates.

**Event: `status_update`**
```json
{
  "event": "status_update",
  "data": {
    "camera_id": "cam-lobby",
    "current_posture": "lying_on_ground",
    "fall_state": "possible_fall",
    "fall_duration": 3.2,
    "confidence": 0.87
  }
}
```

**Event: `alert`**
```json
{
  "event": "alert",
  "data": {
    "camera_id": "cam-lobby",
    "fall_duration": 12.5,
    "message": "Fall confirmed at lobby"
  }
}
```

**Event: `heartbeat`**
```json
{
  "event": "heartbeat",
  "data": { "status": "pong" }
}
```

**Client → Server:**
- Send `"ping"` string untuk trigger heartbeat response.

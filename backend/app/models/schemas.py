"""
schemas.py
==========
Pydantic models (schemas) untuk request/response API dan
representasi data internal.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---- Enums -------------------------------------------------

class PostureClass(str, Enum):
    """Kelas postur yang dideteksi oleh model.

    Mapping dari UR Fall Detection Dataset:
        -1 (person is not lying)       → NORMAL
         0 (temporary pose)            → TRANSITIONAL
         1 (person is lying on ground) → LYING_ON_GROUND
    """
    NORMAL = "normal"
    TRANSITIONAL = "transitional"
    LYING_ON_GROUND = "lying_on_ground"


class FallState(str, Enum):
    """State machine states untuk fall detection."""
    MONITORING = "monitoring"
    POSSIBLE_FALL = "possible_fall"
    CONFIRMED_FALL = "confirmed_fall"


class AlertSeverity(str, Enum):
    """Tingkat keparahan alert."""
    WARNING = "warning"
    CRITICAL = "critical"


# ---- Alert -------------------------------------------------

class AlertBase(BaseModel):
    """Base schema untuk alert."""
    camera_id: str = Field(..., description="ID kamera sumber deteksi")
    severity: AlertSeverity = AlertSeverity.CRITICAL
    message: str = Field(..., description="Deskripsi alert")


class AlertCreate(AlertBase):
    """Schema untuk membuat alert baru (internal use)."""
    fall_duration: float = Field(..., description="Durasi falling dalam detik")


class AlertResponse(AlertBase):
    """Schema response untuk alert yang sudah tersimpan."""
    id: int
    fall_duration: float
    acknowledged: bool = False
    created_at: datetime
    acknowledged_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---- Camera Status -----------------------------------------

class CameraStatus(BaseModel):
    """Status real-time dari sebuah kamera."""
    camera_id: str
    is_active: bool = True
    current_posture: Optional[PostureClass] = None
    fall_state: FallState = FallState.MONITORING
    fall_duration: float = 0.0
    confidence: float = 0.0
    fps: float = 0.0
    last_frame_at: Optional[datetime] = None


# ---- Settings ----------------------------------------------

class ThresholdUpdate(BaseModel):
    """Schema untuk update threshold durasi falling."""
    fall_duration_threshold: float = Field(
        ..., gt=0, le=60,
        description="Durasi falling (detik) sebelum trigger alert (1-60)",
    )


class SettingsResponse(BaseModel):
    """Response berisi konfigurasi aktif."""
    fall_duration_threshold: float
    possible_fall_threshold: float
    confidence_threshold: float
    camera_source: str


# ---- Detection Result (internal) --------------------------

class DetectionResult(BaseModel):
    """Hasil deteksi per-frame dari inference service."""
    posture: PostureClass
    confidence: float
    bbox: Optional[list[float]] = None  # [x1, y1, x2, y2]


# ---- WebSocket Messages -----------------------------------

class WSMessage(BaseModel):
    """Pesan yang dikirim via WebSocket ke frontend."""
    event: str = Field(..., description="Tipe event: status_update | alert | heartbeat")
    data: dict

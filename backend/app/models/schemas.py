"""
schemas.py
==========
Pydantic models (schemas) untuk request/response API dan
representasi data internal.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Pilihan rotasi yang didukung (derajat, searah jarum jam).
ROTATE_CHOICES = (0, 90, 180, 270)


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
    UNKNOWN = "unknown"


class Observation(str, Enum):
    """Observasi hasil pemrosesan model untuk FSM."""
    TRIGGER_POSTURE = "trigger_posture"
    NON_TRIGGER_POSTURE = "non_trigger_posture"
    UNCERTAIN = "uncertain"
    PERSON_LOST = "person_lost"
    OFFLINE = "offline"


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
    simulated: bool = Field(False, description="Dipicu tombol simulasi, bukan deteksi sungguhan")


class AlertResponse(AlertBase):
    """Schema response untuk alert yang sudah tersimpan."""
    id: int
    fall_duration: float
    acknowledged: bool = False
    # Apakah notifikasi Telegram berhasil terkirim. Ikut dikembalikan supaya
    # kegagalan terlihat di Riwayat Insiden -- notifikasi yang gagal diam-diam
    # meninggalkan keyakinan palsu bahwa perawat sudah diberi tahu.
    notified: bool = False
    # Dipicu tombol simulasi, bukan deteksi sungguhan. Ikut dikembalikan supaya
    # riwayat insiden bisa dipercaya sebagai bukti.
    simulated: bool = False
    created_at: datetime
    acknowledged_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class TestNotificationResponse(BaseModel):
    """Hasil percobaan kirim notifikasi uji."""
    terkirim: bool
    dikonfigurasi: bool = Field(..., description="Token dan chat id sudah terisi")
    pesan: str


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


# ---- Camera Registry ---------------------------------------

class CameraBase(BaseModel):
    """Field yang bisa diatur pengguna untuk sebuah kamera."""
    name: str = Field(..., min_length=1, max_length=100, description="Nama lokasi/kamar")
    source: str = Field(
        ..., min_length=1,
        description='Sumber kamera: "0" untuk webcam laptop, http://IP:8080/video untuk '
                    'kamera HP (IP Webcam), rtsp://IP:554/... untuk CCTV, atau path file video',
    )
    rotate: int = Field(0, description="Rotasi searah jarum jam: 0, 90, 180, atau 270")
    enabled: bool = Field(True, description="Kamera dinyalakan saat backend start")

    @field_validator("name", "source")
    @classmethod
    def _tidak_boleh_kosong(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("tidak boleh kosong")
        return v

    @field_validator("rotate")
    @classmethod
    def _rotate_valid(cls, v: int) -> int:
        if v not in ROTATE_CHOICES:
            raise ValueError(f"harus salah satu dari {list(ROTATE_CHOICES)}")
        return v


class CameraCreate(CameraBase):
    """Payload untuk mendaftarkan kamera baru."""
    pass


class CameraUpdate(BaseModel):
    """Payload untuk mengubah kamera. Field yang tidak dikirim dibiarkan apa adanya."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    source: Optional[str] = Field(None, min_length=1)
    rotate: Optional[int] = None
    enabled: Optional[bool] = None

    @field_validator("name", "source")
    @classmethod
    def _tidak_boleh_kosong(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("tidak boleh kosong")
        return v

    @field_validator("rotate")
    @classmethod
    def _rotate_valid(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in ROTATE_CHOICES:
            raise ValueError(f"harus salah satu dari {list(ROTATE_CHOICES)}")
        return v


class CameraInfo(CameraStatus):
    """Kamera terdaftar beserta status runtime-nya.

    Sengaja merupakan superset dari CameraStatus supaya konsumen lama yang hanya
    membaca camera_id / is_active / fall_state tetap bekerja tanpa perubahan.
    """
    name: str
    source: str
    rotate: int = 0
    enabled: bool = True
    stream_url: str = Field(..., description="Path endpoint MJPEG untuk kamera ini")


class SimulationResponse(BaseModel):
    """Hasil memulai simulasi jatuh pada satu kamera."""
    camera_id: str
    durasi_simulasi: float = Field(..., description="Berapa lama observasi ditimpa, dalam detik")
    ambang_konfirmasi: float = Field(..., description="Detik sebelum state machine mengonfirmasi")
    pesan: str


class ScanCandidate(BaseModel):
    """Satu kandidat kamera hasil pemindaian jaringan."""
    ip: str
    port: int
    source: str = Field(..., description="URL siap pakai untuk diisikan ke field source")
    label: str = Field(..., description="Dugaan jenis perangkat berdasarkan nomor port")


class LocalDevice(BaseModel):
    """Kamera yang terpasang langsung di komputer ini."""
    index: int = Field(..., description="Indeks perangkat, dipakai OpenCV sebagai sumber")
    name: str = Field(..., description="Nama perangkat menurut sistem operasi")
    label: str = Field(..., description="Nama untuk ditampilkan; Iriun memakai penamaan aplikasinya")
    driver: Optional[str] = Field(None, description="Perangkat lunak di baliknya, mis. Iriun")
    source: str = Field(..., description="Nilai siap pakai untuk field source")
    in_use: bool = Field(False, description="Sudah dipakai salah satu kamera terdaftar")


class ScanResponse(BaseModel):
    """Hasil pemindaian jaringan lokal."""
    subnets: list[str] = Field(..., description="Subnet yang dipindai, mis. 192.168.1.0/24")
    duration_sec: float
    candidates: list[ScanCandidate]


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

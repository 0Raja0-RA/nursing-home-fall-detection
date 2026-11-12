"""
schemas.py
==========
Pydantic models (schemas) untuk request/response API dan
representasi data internal.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

import re

from pydantic import BaseModel, Field, field_validator, model_validator

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


class Putusan(str, Enum):
    """Putusan perawat setelah memeriksa: apakah alarm ini benar jatuh."""
    JATUH = "jatuh"
    PALSU = "palsu"
    BELUM_YAKIN = "belum_yakin"


# Label putusan untuk ditampilkan. Satu sumber untuk dashboard dan Telegram.
LABEL_PUTUSAN = {
    Putusan.JATUH.value: "Jatuh sungguhan",
    Putusan.PALSU.value: "Alarm palsu",
    Putusan.BELUM_YAKIN.value: "Belum yakin",
}

# Alasan alarm palsu. Wajib dipilih saat putusannya palsu: tanpa alasan, angka
# alarm palsu tidak bisa dipakai untuk memperbaiki model atau ambang. Labelnya
# pendek karena juga menjadi tombol Telegram.
ALASAN_PALSU = {
    "berbaring_sengaja": "Berbaring sengaja",
    "duduk_membungkuk": "Duduk atau membungkuk",
    "bukan_orang": "Bukan orang",
    "orang_lain": "Orang lain di lantai",
    "lainnya": "Lainnya",
}


# ---- Alert -------------------------------------------------

class AlertBase(BaseModel):
    """Base schema untuk alert."""
    camera_id: str = Field(..., description="ID kamera sumber deteksi")
    camera_name: Optional[str] = Field(
        None, description="Nama ruang saat kejadian. Kosong pada alert lama; pakai camera_id sebagai cadangan."
    )
    severity: AlertSeverity = AlertSeverity.CRITICAL
    message: str = Field(..., description="Deskripsi alert")


class AlertCreate(AlertBase):
    """Schema untuk membuat alert baru (internal use)."""
    fall_duration: float = Field(..., description="Durasi falling dalam detik")
    simulated: bool = Field(False, description="Dipicu tombol simulasi, bukan deteksi sungguhan")
    threshold_sec: Optional[float] = Field(None, description="Ambang yang berlaku saat kejadian")
    detection_mode: Optional[str] = Field(None, description="Mode detektor saat kejadian")
    telegram_status: Optional[str] = None
    klip_status: Optional[str] = None


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
    caregiver_note: Optional[str] = None
    created_at: datetime
    acknowledged_at: Optional[datetime] = None

    # Penanganan oleh manusia. Lihat AlertRecord untuk alasan tiap kolom.
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    verdict: Optional[Putusan] = Field(None, description="NULL = belum dinilai")
    verdict_reason: Optional[str] = None
    verdict_by: Optional[str] = None
    verdict_at: Optional[datetime] = None
    # Keadaan sistem saat kejadian. Kosong pada alert lama.
    threshold_sec: Optional[float] = None
    detection_mode: Optional[str] = None
    # mengirim | terkirim | gagal | mati | dilewati. Kosong pada alert lama: pakai notified.
    telegram_status: Optional[str] = None
    # merekam | tersimpan | kosong | gagal | dihapus. Kosong = tidak ada klip.
    klip_status: Optional[str] = None
    klip_detik: Optional[float] = None

    model_config = {"from_attributes": True}


# Batas panjang catatan perawat. Cukup untuk beberapa kalimat tindakan, dan
# mencegah teks raksasa masuk ke database lewat API.
CATATAN_MAKS = 500


class _DenganPutusan(BaseModel):
    """Aturan putusan yang sama untuk menutup alarm dan untuk mengubah putusan."""
    verdict: Optional[Putusan] = None
    reason: Optional[str] = Field(None, description="Kode alasan, wajib bila verdict = palsu")

    @model_validator(mode="after")
    def _alasan_sesuai_putusan(self):
        if self.verdict == Putusan.PALSU:
            if not self.reason:
                raise ValueError("Alasan alarm palsu wajib dipilih.")
            if self.reason not in ALASAN_PALSU:
                raise ValueError(f"Alasan tidak dikenal. Pilihan: {', '.join(ALASAN_PALSU)}.")
        else:
            # Alasan hanya bermakna untuk alarm palsu; jangan simpan sisa pilihan lama.
            self.reason = None
        return self


class AckRequest(_DenganPutusan):
    """Body opsional untuk PUT /api/alerts/{id}/ack.

    Putusan boleh kosong (API lama tetap bekerja), tetapi alert tanpa putusan tetap
    berada di antrean "Perlu tindakan" sampai ada yang menilainya.
    """
    note: Optional[str] = Field(None, max_length=CATATAN_MAKS,
                                description="Tindakan yang diambil perawat")


class VerdictUpdate(_DenganPutusan):
    """Body untuk PUT /api/alerts/{id}/verdict: mengisi atau mengubah putusan belakangan."""
    verdict: Putusan


class AlertSummary(BaseModel):
    """Jumlah per kelompok, untuk tab dan lencana di dashboard."""
    perlu_tindakan: int = Field(..., description="Belum ditangani, ditambah yang belum dinilai")
    belum_ditangani: int
    sedang_ditangani: int = Field(..., description="Sudah ada yang menuju lokasi, belum ditutup")
    belum_dinilai: int = Field(..., description="Sudah ditangani, putusannya kosong atau belum yakin")
    total: int = Field(..., description="Semua alert sungguhan (tanpa latihan)")
    jatuh: int
    palsu: int
    latihan: int
    telegram_gagal: int


class NoteUpdate(BaseModel):
    """Body untuk PUT /api/alerts/{id}/note."""
    note: str = Field(..., max_length=CATATAN_MAKS)


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
    # Sedang dilatih lewat Mode latihan (tombol simulasi), bukan kejadian sungguhan.
    simulated: bool = False


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


class ModeUpdate(BaseModel):
    """Schema untuk mengganti mode detektor."""
    detection_mode: str = Field(..., description="bbox | pose")


class ModeInfo(BaseModel):
    """Satu pilihan mode detektor, untuk mengisi dropdown di dashboard."""
    id: str
    label: str
    description: str
    recommended: bool


class Pilihan(BaseModel):
    """Satu pilihan berlabel, untuk tombol atau dropdown di dashboard."""
    id: str
    label: str


# Cara foto kejadian dikirim ke Telegram. Bawaannya buram: foto penghuni yang
# tergeletak adalah data kesehatan, dan pesan grup mudah diteruskan.
MODE_FOTO_TELEGRAM = {
    "buram": "Foto diburamkan (bawaan)",
    "utuh": "Foto utuh, tertutup sampai diketuk",
    "tanpa": "Tanpa foto, hanya teks",
}


class TelegramSettings(BaseModel):
    """Pengaturan Telegram yang bisa diubah dari dashboard. Token dan chat id tidak."""
    photo_mode: str = Field("buram", description="buram | utuh | tanpa")
    # Latihan tidak dikirim secara bawaan, supaya grup perawat tidak terbiasa
    # mengabaikan pesan alarm.
    send_drills: bool = False
    # Kabari grup bila kamera terputus lebih dari 30 detik, dan saat pulih.
    camera_offline: bool = True


class TelegramSettingsUpdate(BaseModel):
    """Body untuk PUT /api/settings/telegram. Field yang tidak dikirim tidak berubah."""
    photo_mode: Optional[str] = None
    send_drills: Optional[bool] = None
    camera_offline: Optional[bool] = None

    @field_validator("photo_mode")
    @classmethod
    def _mode_foto_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in MODE_FOTO_TELEGRAM:
            raise ValueError(f"harus salah satu dari {list(MODE_FOTO_TELEGRAM)}")
        return v


class SettingsResponse(BaseModel):
    """Response berisi konfigurasi aktif."""
    fall_duration_threshold: float
    possible_fall_threshold: float
    confidence_threshold: float
    camera_source: str
    detection_mode: str
    available_modes: list[ModeInfo]
    telegram_configured: bool
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    photo_modes: list[Pilihan] = Field(default_factory=list)
    # Pilihan putusan dan alasan alarm palsu, supaya dashboard tidak menyalin daftarnya.
    verdicts: list[Pilihan] = Field(default_factory=list)
    false_alarm_reasons: list[Pilihan] = Field(default_factory=list)


# ---- Akun ----------------------------------------------------

PERAN = ("pengelola", "perawat")
_POLA_USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")
SANDI_MIN = 8


def _username_valid(v: str) -> str:
    v = v.strip().lower()
    if not _POLA_USERNAME.fullmatch(v):
        raise ValueError("3 sampai 32 karakter: huruf kecil, angka, titik, garis bawah, atau tanda hubung")
    return v


def _nama_valid(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("tidak boleh kosong")
    return v


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=200)


class AkunBaru(BaseModel):
    """Membuat akun: pengelola pertama lewat /api/auth/setup, sisanya lewat /api/users."""
    display_name: str = Field(..., min_length=1, max_length=60, description="Nama yang tampil saat menangani alarm")
    username: str
    password: str = Field(..., min_length=SANDI_MIN, max_length=200)
    role: str = "perawat"

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        return _username_valid(v)

    @field_validator("display_name")
    @classmethod
    def _nama(cls, v: str) -> str:
        return _nama_valid(v)

    @field_validator("role")
    @classmethod
    def _peran_valid(cls, v: str) -> str:
        if v not in PERAN:
            raise ValueError(f"harus salah satu dari {list(PERAN)}")
        return v


class AkunUbah(BaseModel):
    """Body untuk PATCH /api/users/{id}. Field yang tidak dikirim tidak berubah."""
    display_name: Optional[str] = Field(None, min_length=1, max_length=60)
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=SANDI_MIN, max_length=200)

    @field_validator("display_name")
    @classmethod
    def _nama(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _nama_valid(v)

    @field_validator("role")
    @classmethod
    def _peran_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PERAN:
            raise ValueError(f"harus salah satu dari {list(PERAN)}")
        return v


class GantiSandi(BaseModel):
    password_lama: str = Field(..., max_length=200)
    password_baru: str = Field(..., min_length=SANDI_MIN, max_length=200)


class AkunResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StatusAuth(BaseModel):
    """Dipakai halaman Login untuk memberi petunjuk sebelum ada yang masuk."""
    ada_akun: bool = Field(..., description="Ada akun aktif; kalau tidak, akun demo belum diatur di backend/.env")
    pengunjung_aktif: bool = Field(..., description="Akses lihat-saja lewat QR sedang dinyalakan")


class TokenPengunjung(BaseModel):
    """Body untuk POST /api/auth/pengunjung: token dari QR di stand."""
    token: str = Field(..., min_length=1, max_length=200)


# ---- Detection Result (internal) --------------------------

class DetectionResult(BaseModel):
    """Hasil deteksi per-frame dari inference service."""
    posture: PostureClass
    confidence: float
    bbox: Optional[list[float]] = None  # [x1, y1, x2, y2]
    # Hanya terisi di mode pose: 17 keypoint COCO, masing-masing [x, y, conf].
    # Dipakai overlay untuk menggambar skeleton. Tidak ikut disiarkan lewat
    # WebSocket -- yang disiarkan CameraStatus, bukan objek ini.
    keypoints: Optional[list[list[float]]] = None


# ---- WebSocket Messages -----------------------------------

class WSMessage(BaseModel):
    """Pesan yang dikirim via WebSocket ke frontend."""
    event: str = Field(..., description="Tipe event: status_update | alert | alert_ack | heartbeat")
    data: dict

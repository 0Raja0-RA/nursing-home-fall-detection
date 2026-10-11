"""
config.py
=========
Konfigurasi aplikasi menggunakan pydantic-settings.

Semua environment variable didefinisikan di sini dan bisa
di-override melalui file .env atau env var langsung.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings — diambil dari environment variables."""

    # ---- General -------------------------------------------
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # ---- Server --------------------------------------------
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ---- Database ------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./fall_detection.db"

    # ---- Model Path ----------------------------------------
    # Path relatif ke file .pt hasil training YOLO11
    MODEL_PATH: str = str(
        Path(__file__).resolve().parents[3] / "ml" / "models" / "fall_detection" / "weights" / "best.pt"
    )
    # Model kedua: estimasi pose (17 keypoint). Dipakai mode "pose".
    # Berkas rilis standar Ultralytics; kalau belum ada, diunduh otomatis saat
    # pertama dipakai. Jangan tulis nama telanjang "yolo11n-pose.pt" di kode --
    # Ultralytics akan meresolusinya relatif ke working directory dan mengunduh
    # salinan baru ke sana, bukan memakai berkas yang sudah ada di repo.
    POSE_MODEL_PATH: str = str(
        Path(__file__).resolve().parents[3] / "ml" / "models" / "fall_detection" / "weights" / "yolo11n-pose.pt"
    )
    # Mode detektor bawaan saat database masih kosong: "bbox" | "pose".
    # Nilai yang benar-benar dipakai dibaca dari tabel app_settings saat startup.
    DETECTION_MODE: str = "pose"

    CONFIDENCE_THRESHOLD: float = 0.5
    # Gambar juga kotak abu-abu "(ragu)" di stream? Hanya memengaruhi tampilan:
    # deteksi ragu tetap menjadi UNCERTAIN di state machine (timer ditahan, bukan
    # direset). Nyalakan hanya untuk diagnosa.
    SHOW_UNCERTAIN_BOXES: bool = False
    # Batas bawah agar deteksi lemah tetap dikembalikan model (untuk digambar & didiagnosa).
    # Keputusan dipercaya atau tidak tetap memakai CONFIDENCE_THRESHOLD di pipeline.
    DETECTION_MIN_CONF: float = 0.05
    # Kotak dengan keyakinan "ini orang" di bawah ini dibuang sama sekali: tidak
    # digambar dan tidak ikut menentukan keputusan. Berbeda dengan
    # CONFIDENCE_THRESHOLD, yang menilai keyakinan POSTUR dan menghasilkan
    # UNCERTAIN. Tanpa saringan ini, colokan atau kursi yang sekilas mirip orang
    # dibaca UNCERTAIN dan menahan timer di semua kamera. Naikkan kalau masih ada
    # benda yang terbaca sebagai orang.
    PERSON_MIN_CONF: float = 0.50
    # Kotak yang lebih kecil dari ini (pecahan luas frame) dibuang. Orang yang
    # terlihat, bahkan dari jauh, jauh lebih besar daripada colokan atau stiker.
    MIN_BOX_AREA_FRAC: float = 0.01
    # Postur pemicu (lying_on_ground) adalah yang HARUS sampai ke state machine.
    # Orang yang tergeletak justru yang keyakinannya paling rendah dan sendinya
    # paling sering tertutup, jadi saringan di atas dilonggarkan untuknya:
    #  - postur pemicu dengan keyakinan >= TRIGGER_MIN_CONF dihitung sebagai
    #    pemicu walau di bawah CONFIDENCE_THRESHOLD, dan selalu digambar;
    #  - kotak yang melebar (mirip orang berbaring) memakai TRIGGER_MIN_CONF
    #    sebagai batas bawah keyakinan, dan cukup MIN_KEYPOINTS_PEMICU sendi.
    # Harga yang dibayar: kasur atau sofa yang melebar bisa memicu timer.
    TRIGGER_MIN_CONF: float = 0.25
    MIN_KEYPOINTS_PEMICU: int = 3
    # Khusus mode pose: minimal berapa dari 17 sendi yang harus terbaca (keyakinan
    # >= 0.3) agar sebuah kotak dianggap manusia. Kursi dan colokan tidak punya
    # sendi yang masuk akal. Dibuat longgar (bukan semua sendi) supaya orang yang
    # tergeletak dengan sebagian tubuh tertutup tetap lolos. 0 = matikan.
    MIN_VISIBLE_KEYPOINTS: int = 7

    # ---- Fall Detection State Machine ----------------------
    FALL_DURATION_THRESHOLD: float = 10.0  # detik
    POSSIBLE_FALL_THRESHOLD: float = 2.0   # detik sebelum mulai hitung
    DEBOUNCE_FRAMES: int = 5
    GRACE_PERIOD_SEC: float = 3.0
    # Batas waktu yang boleh dihitung dari satu observasi. Melindungi timer dari
    # jeda pipeline (pemuatan model, inference tersendat, kamera menyambung ulang)
    # yang kalau tidak dibatasi akan terhitung sebagai durasi tergeletak.
    MAX_FRAME_GAP_SEC: float = 1.0
    TRIGGER_CLASSES: list[str] = ["lying_on_ground"]
    # Postur yang MENAHAN timer (tidak memajukan, tidak mereset). Model sering
    # menukar lying_on_ground dan transitional dari frame ke frame untuk orang
    # yang sama-sama tergeletak; kalau transitional dihitung "sudah bangun",
    # timer terus direset dan alarm tidak pernah berbunyi. Hanya postur lain
    # (normal) yang mereset.
    PAUSE_CLASSES: list[str] = ["transitional"]
    # Berapa lama sesudah lying_on_ground terakhir terlihat, postur PAUSE_CLASSES
    # masih dianggap "orang yang sama sedang berkedip" dan menahan timer. Lewat
    # dari ini, ia dibaca seperti postur biasa. Tanpa batas waktu, orang yang
    # duduk (terbaca transitional) menahan timer selamanya: kamera tersangkut di
    # CONFIRMED_FALL, jatuh berikutnya tidak berbunyi, dan salah-baca lying yang
    # tercecer berjam-jam terus terakumulasi sampai menembus ambang.
    PAUSE_WINDOW_SEC: float = 3.0
    ALERT_COOLDOWN_SEC: float = 60.0

    # ---- Camera --------------------------------------------
    # Dipakai sebagai kamera bawaan saat tabel `cameras` masih kosong. Setelah ada
    # kamera terdaftar, sumbernya diambil dari database (bisa diatur dari dashboard).
    CAMERA_SOURCE: str = "0"  # "0" = webcam, atau URL RTSP
    CAMERA_FPS: int = 15
    # Batas jumlah kamera. Inference berjalan di CPU, jadi tiap kamera menambah
    # beban secara linear -- batas ini mencegah sistem melambat diam-diam.
    MAX_CAMERAS: int = 4
    # Rotasi searah jarum jam: 0, 90, 180, 270. Kamera HP sering mengirim gambar miring (90 atau 270).
    CAMERA_ROTATE: int = 0
    # Frame yang lebih tua dari ini dianggap basi, dan kamera dilaporkan OFFLINE.
    CAMERA_STALE_SEC: float = 3.0

    # ---- Telegram Notification -----------------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # ---- CORS ----------------------------------------------
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()

"""
inference_service.py
====================
Memuat model YOLO11 (.pt) dan menjalankan inference pada frame
video untuk mendeteksi postur (normal / transitional / lying_on_ground).

Label mapping (UR Fall Detection Dataset):
    0: normal          — orang tidak terbaring (berdiri/berjalan/duduk)
    1: transitional    — pose sementara (sedang jatuh / transisi)
    2: lying_on_ground — orang terbaring di lantai

Model di-load sekali saat startup dan digunakan berulang kali
untuk setiap frame yang masuk dari camera service.
"""

import threading
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.models.schemas import DetectionResult, PostureClass

from app.core.logging import get_logger
log = get_logger("app.services.inference_service")

# Label mapping — harus sesuai dengan data.yaml di ml/
_CLASS_MAP = {
    0: PostureClass.NORMAL,
    1: PostureClass.TRANSITIONAL,
    2: PostureClass.LYING_ON_GROUND,
}

# Singleton model instance
_model = None

# Setiap kamera menjalankan inference lewat asyncio.to_thread, jadi beberapa thread
# bisa masuk ke sini bersamaan begitu ada lebih dari satu kamera.
#
# _load_lock mencegah model dimuat berkali-kali. Tanpa ini, empat kamera yang
# menyala bersamaan sama-sama lolos pengecekan `_model is None` dan masing-masing
# membuat salinan YOLO sendiri -- terbukti di log: "Model loaded" lima kali.
#
# _infer_lock membuat pemanggilan model berurutan. Objek YOLO milik ultralytics
# menyimpan state internal (predictor) yang dipakai ulang antar panggilan, jadi
# memanggilnya dari beberapa thread sekaligus tidak aman. Lagi pula inference
# berjalan di CPU: menjalankan empat sekaligus hanya memperebutkan core yang sama.
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


def load_model(model_path: Optional[str] = None):
    """Load model YOLO11 dari file .pt.

    Args:
        model_path: Path ke file model. Jika None, gunakan dari settings.

    Returns:
        YOLO model instance.

    Raises:
        FileNotFoundError: Jika file model tidak ditemukan.
    """
    global _model

    if _model is not None:
        return _model

    with _load_lock:
        # Diperiksa ulang di dalam lock: thread lain bisa saja sudah memuatnya
        # selagi kita menunggu giliran.
        if _model is not None:
            return _model

        from ultralytics import YOLO

        settings = get_settings()
        path = model_path or settings.MODEL_PATH

        if not Path(path).exists():
            log.info(f"⚠️ Model custom belum ditemukan di '{path}'.")
            log.info("   Menggunakan base model 'yolo11n.pt' sebagai fallback sementara (mode demo).")
            log.info("   [DEMO MODE] Untuk mensimulasikan JATUH, tunjukkan 'cell phone' ke kamera!")
            path = "yolo11n.pt"

            # Override _CLASS_MAP untuk demo dengan yolo11n.pt
            global _CLASS_MAP
            _CLASS_MAP = {
                0: PostureClass.NORMAL,             # Person -> Normal
                67: PostureClass.LYING_ON_GROUND,   # Cell phone -> Jatuh
            }

        _model = YOLO(path)
        log.info(f"✅ Model loaded: {path}")
        return _model


<<<<<<< Updated upstream
def run_inference(frame: np.ndarray) -> Optional[DetectionResult]:
    """Jalankan inference pada satu frame.
=======
def load_model(model_path: Optional[str] = None):
    """Muat model mode aktif. Tetap ada supaya pemanggil lama tidak perlu diubah."""
    if model_path:
        # Jalur ini hanya dipakai pengujian yang menunjuk berkas tertentu.
        with _load_lock:
            from ultralytics import YOLO
            _models[mode_aktif()] = YOLO(model_path)
            log.info(f"✅ Model loaded: {model_path}")
            return _models[mode_aktif()]
    return _muat(mode_aktif())


# ---- Kinematika pose (EXP-009) -----------------------------

# Indeks keypoint COCO yang dipakai.
_KP_BAHU_KIRI, _KP_BAHU_KANAN = 5, 6
_KP_PINGGUL_KIRI, _KP_PINGGUL_KANAN = 11, 12

# Di bawah ini sendi dianggap tidak terbaca, dan sudut tulang belakang tidak
# bisa dipercaya.
_KP_MIN_CONF = 0.25

# Sendi dihitung "terlihat" untuk saringan manusia di atas ambang ini.
_KP_TERLIHAT = 0.3

# Ambang hasil kalibrasi EXP-009, dalam derajat terhadap lantai
# (0 = rebah mendatar, 90 = tegak berdiri).
_SUDUT_REBAH = 20.0
_SUDUT_REBAH_LONGGAR = 32.0   # dipakai kalau kotaknya jelas melebar
_SUDUT_TRANSISI = 60.0
_AR_REBAH = 1.15
# Saat sendi tidak terbaca dan hanya bentuk kotak yang tersisa, "berbaring" baru
# dipercaya kalau kotaknya sangat pipih. Orang duduk dengan kaki lurus ke depan
# berkotak melebar sekitar 1,2-1,6; yang benar-benar tergeletak jauh lebih pipih.
_AR_TEBAKAN_REBAH = 1.8
_AR_TRANSISI = 0.95


def calculate_spine_angle(kpts: np.ndarray) -> float:
    """Sudut tulang belakang terhadap lantai: 0 derajat rebah, 90 derajat tegak."""
    bahu_kiri, bahu_kanan = kpts[_KP_BAHU_KIRI][:2], kpts[_KP_BAHU_KANAN][:2]
    pinggul_kiri, pinggul_kanan = kpts[_KP_PINGGUL_KIRI][:2], kpts[_KP_PINGGUL_KANAN][:2]

    mid_bahu = ((bahu_kiri[0] + bahu_kanan[0]) / 2, (bahu_kiri[1] + bahu_kanan[1]) / 2)
    mid_pinggul = ((pinggul_kiri[0] + pinggul_kanan[0]) / 2, (pinggul_kiri[1] + pinggul_kanan[1]) / 2)

    dx = mid_bahu[0] - mid_pinggul[0]
    dy = mid_bahu[1] - mid_pinggul[1]
    return math.degrees(math.atan2(abs(dy), abs(dx)))


def _titik_rata(kpts: np.ndarray, indeks: tuple[int, ...]):
    """Titik tengah dari sendi yang terbaca, atau None kalau tidak ada satu pun."""
    terbaca = [kpts[i][:2] for i in indeks if kpts[i][2] >= _KP_TERLIHAT]
    if not terbaca:
        return None
    return (sum(t[0] for t in terbaca) / len(terbaca), sum(t[1] for t in terbaca) / len(terbaca))


def _sudut_kepala_pinggul(kpts: np.ndarray) -> Optional[float]:
    """Sudut garis kepala-ke-pinggul terhadap lantai, kalau keduanya terbaca.

    Pengganti sudut tulang belakang saat bahu atau pinggul tidak terbaca: orang
    yang duduk kepalanya tegak di atas pinggul, sedangkan orang yang tergeletak
    kepalanya sejajar pinggul.
    """
    atas = _titik_rata(kpts, (_KP_BAHU_KIRI, _KP_BAHU_KANAN)) or _titik_rata(kpts, (0, 1, 2, 3, 4))
    bawah = _titik_rata(kpts, (_KP_PINGGUL_KIRI, _KP_PINGGUL_KANAN))
    if atas is None or bawah is None:
        return None
    return math.degrees(math.atan2(abs(atas[1] - bawah[1]), abs(atas[0] - bawah[0])))


def _postur_dari_pose(kpts: np.ndarray, aspect_ratio: float) -> tuple[PostureClass, float]:
    """Terjemahkan keypoint jadi postur, beserta seberapa bisa dipercaya hasilnya.

    Nilai kedua BUKAN keyakinan "ini orang", melainkan keyakinan POSTUR. Bedanya
    menentukan: pipeline memakai angka ini untuk memutuskan Observation.UNCERTAIN,
    dan pada mode pose, keyakinan kotak selalu tinggi untuk orang yang terlihat
    jelas -- berdiri maupun tergeletak. Kalau yang dilaporkan keyakinan kotak,
    cabang UNCERTAIN tidak akan pernah menyala di mode ini.
    """
    conf_bahu = (kpts[_KP_BAHU_KIRI][2] + kpts[_KP_BAHU_KANAN][2]) / 2
    conf_pinggul = (kpts[_KP_PINGGUL_KIRI][2] + kpts[_KP_PINGGUL_KANAN][2]) / 2
    mutu = float(min(conf_bahu, conf_pinggul))

    if mutu >= _KP_MIN_CONF:
        sudut = calculate_spine_angle(kpts)
    else:
        # Bahu atau pinggul tidak terbaca. Coba kepala-ke-pinggul dulu; kalau itu
        # juga tidak ada, sudutnya ditebak dari bentuk kotak.
        #
        # `mutu` sengaja tidak dinaikkan di sini, jadi postur non-berbaring hasil
        # tebakan tetap dibaca pipeline sebagai UNCERTAIN (timer ditahan, bukan
        # direset). Postur dihitung supaya kotaknya tetap bisa digambar.
        sudut = _sudut_kepala_pinggul(kpts)
        if sudut is None:
            if aspect_ratio < 0.8:
                sudut = 90.0
            elif aspect_ratio > _AR_TEBAKAN_REBAH:
                sudut = 20.0
            else:
                sudut = 50.0

    if sudut < _SUDUT_REBAH or (aspect_ratio > _AR_REBAH and sudut < _SUDUT_REBAH_LONGGAR):
        postur = PostureClass.LYING_ON_GROUND
    elif sudut < _SUDUT_TRANSISI or aspect_ratio > _AR_TRANSISI:
        postur = PostureClass.TRANSITIONAL
    else:
        postur = PostureClass.NORMAL

    return postur, mutu


# ---- Inference ---------------------------------------------

def run_inference(frame: np.ndarray) -> list[DetectionResult]:
    """Jalankan inference pada satu frame, memakai mode yang sedang aktif.
>>>>>>> Stashed changes

    Args:
        frame: Frame video dalam format numpy array (BGR, dari OpenCV).

    Returns:
        Satu DetectionResult per orang yang terdeteksi, urut dari confidence
        tertinggi. List kosong jika model benar-benar tidak menemukan siapa pun.

    Semua kotak dikembalikan, bukan hanya yang paling yakin. Dulu hanya kotak
    ber-confidence tertinggi yang dipakai, sehingga orang yang berdiri jelas
    menutupi orang yang tergeletak di frame yang sama: yang jatuh tidak pernah
    sampai ke state machine. Memilih mana yang menentukan keputusan adalah tugas
    detection_pipeline.

    Catatan: penyaringan memakai DETECTION_MIN_CONF (sangat rendah), BUKAN
    CONFIDENCE_THRESHOLD. Keputusan "cukup yakin atau tidak" dibuat di
    detection_pipeline supaya cabang UNCERTAIN benar-benar berfungsi, dan supaya
    deteksi berkeyakinan rendah tetap bisa digambar di stream untuk diagnosa.
    """
    model = load_model()
    settings = get_settings()

    with _infer_lock:
        results = model(frame, verbose=False, conf=settings.DETECTION_MIN_CONF)

    if not results or len(results[0].boxes) == 0:
        return []

    # Ambil deteksi dengan confidence tertinggi
    boxes = results[0].boxes
<<<<<<< Updated upstream
    best_idx = boxes.conf.argmax().item()

    cls_id = int(boxes.cls[best_idx].item())
    confidence = float(boxes.conf[best_idx].item())
    bbox = boxes.xyxy[best_idx].tolist()

    posture = _CLASS_MAP.get(cls_id, PostureClass.NORMAL)

    return DetectionResult(
        posture=posture,
        confidence=confidence,
        bbox=bbox,
    )
=======
    urutan = sorted(range(len(boxes)), key=lambda i: float(boxes.conf[i].item()), reverse=True)

    keypoints = None
    if mode == MODE_POSE:
        keypoints = getattr(results[0], "keypoints", None)
        if keypoints is None or keypoints.data is None:
            # Bukan model pose, atau keypoint-nya tidak keluar.
            return []

    luas_frame = float(frame.shape[0] * frame.shape[1])

    hasil: list[DetectionResult] = []
    for idx in urutan:
        confidence = float(boxes.conf[idx].item())
        bbox = boxes.xyxy[idx].tolist()

        x1, y1, x2, y2 = bbox
        aspect_ratio = max(1.0, x2 - x1) / max(1.0, y2 - y1)
        # Kotak melebar = calon orang berbaring, yang tidak boleh ikut tersaring.
        melebar = aspect_ratio > _AR_REBAH

        # Saring benda yang bukan orang: terlalu tidak yakin, atau terlalu kecil.
        batas_yakin = min(settings.PERSON_MIN_CONF, settings.TRIGGER_MIN_CONF) if melebar             else settings.PERSON_MIN_CONF
        if confidence < batas_yakin:
            continue
        luas_kotak = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if luas_kotak / luas_frame < settings.MIN_BOX_AREA_FRAC:
            continue

        if mode == MODE_POSE:
            if len(keypoints.data) <= idx:
                continue
            kpts = keypoints.data[idx].cpu().numpy()

            # Tanpa cukup sendi yang terbaca, ini bukan manusia (kursi, colokan).
            terlihat = int((kpts[:, 2] >= _KP_TERLIHAT).sum())
            butuh = min(settings.MIN_VISIBLE_KEYPOINTS, settings.MIN_KEYPOINTS_PEMICU)                 if melebar else settings.MIN_VISIBLE_KEYPOINTS
            if terlihat < butuh:
                continue

            postur, mutu = _postur_dari_pose(kpts, aspect_ratio)
            # Yang dilaporkan adalah yang paling lemah di antara "ini benar orang"
            # dan "posturnya terbaca jelas" -- KECUALI untuk berbaring.
            #
            # Orang yang tergeletak justru yang bahu dan pinggulnya paling sulit
            # terbaca (tertutup, miring, menghadap kamera), jadi `mutu` mendekati
            # nol padahal kotaknya terdeteksi baik. Kalau mutu ikut dilaporkan,
            # postur pemicu selalu jatuh ke UNCERTAIN, timer tidak pernah maju, dan
            # alarm yang menjadi tujuan utama sistem tidak pernah berbunyi. Untuk
            # berbaring, yang dipercaya adalah keyakinan bahwa kotak itu orang.
            if postur == PostureClass.LYING_ON_GROUND and mutu < _KP_MIN_CONF:
                dilaporkan = confidence
            else:
                dilaporkan = min(confidence, mutu)
            hasil.append(DetectionResult(
                posture=postur,
                confidence=dilaporkan,
                bbox=bbox,
                keypoints=kpts.tolist(),
            ))
        else:
            cls_id = int(boxes.cls[idx].item())
            hasil.append(DetectionResult(
                posture=_CLASS_MAP.get(cls_id, PostureClass.NORMAL),
                confidence=confidence,
                bbox=bbox,
            ))

    return hasil
>>>>>>> Stashed changes


def unload_model() -> None:
    """Unload model dari memori (untuk cleanup)."""
    global _model
    with _load_lock:
        _model = None

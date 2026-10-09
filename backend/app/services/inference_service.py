"""
inference_service.py
====================
Menjalankan inference pada frame video untuk menentukan postur
(normal / transitional / lying_on_ground).

Ada dua mode yang bisa dipilih dari halaman Pengaturan:

    bbox  — model custom kita (EXP-006, best.pt). Kelas postur dibaca
            langsung dari keluaran model.
    pose  — YOLO11-Pose. Model ini hanya mendeteksi 17 keypoint tubuh;
            posturnya DIHITUNG dari sudut tulang belakang (EXP-009).

Keduanya mengembalikan DetectionResult yang sama, jadi state machine,
timer, debounce, dan cooldown tidak perlu tahu mode mana yang sedang aktif.

Label mapping untuk mode bbox (UR Fall Detection Dataset):
    0: normal          — orang tidak terbaring (berdiri/berjalan/duduk)
    1: transitional    — pose sementara (sedang jatuh / transisi)
    2: lying_on_ground — orang terbaring di lantai
"""

import math
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.models.schemas import DetectionResult, PostureClass

from app.core.logging import get_logger
log = get_logger("app.services.inference_service")


# ---- Mode yang tersedia ------------------------------------
# Dipakai juga oleh GET /api/settings/ untuk mengisi dropdown, supaya daftar
# mode hanya ditulis di satu tempat.
MODE_BBOX = "bbox"
MODE_POSE = "pose"

MODE_INFO = [
    {
        "id": MODE_POSE,
        "label": "Pose Estimation",
        "description": "YOLO11-Pose. Postur dihitung dari sudut tulang belakang, "
                       "jadi kasur dan sofa tidak terbaca sebagai orang jatuh.",
        "recommended": True,
    },
    {
        "id": MODE_BBOX,
        "label": "Bounding Box",
        "description": "Model custom EXP-006. Kelas postur dibaca langsung dari "
                       "keluaran model, tanpa perhitungan tambahan.",
        "recommended": False,
    },
]
MODE_IDS = {m["id"] for m in MODE_INFO}


# Label mapping mode bbox — harus sesuai dengan data.yaml di ml/
_CLASS_MAP = {
    0: PostureClass.NORMAL,
    1: PostureClass.TRANSITIONAL,
    2: PostureClass.LYING_ON_GROUND,
}

# Model disimpan per mode. Sekali dimuat ia tetap di cache, supaya bolak-balik
# ganti mode saat demo tidak memuat ulang berkas .pt setiap kali. Yang belum
# pernah dipilih tidak ikut memakan memori.
_models: dict[str, object] = {}
_mode: Optional[str] = None

# Setiap kamera menjalankan inference lewat asyncio.to_thread, jadi beberapa thread
# bisa masuk ke sini bersamaan begitu ada lebih dari satu kamera.
#
# _load_lock mencegah model dimuat berkali-kali. Tanpa ini, empat kamera yang
# menyala bersamaan sama-sama lolos pengecekan "belum ada di cache" dan
# masing-masing membuat salinan YOLO sendiri -- terbukti di log: "Model loaded"
# lima kali.
#
# _infer_lock membuat pemanggilan model berurutan. Objek YOLO milik ultralytics
# menyimpan state internal (predictor) yang dipakai ulang antar panggilan, jadi
# memanggilnya dari beberapa thread sekaligus tidak aman. Lagi pula inference
# berjalan di CPU: menjalankan empat sekaligus hanya memperebutkan core yang sama.
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


# ---- Mode aktif --------------------------------------------

def mode_aktif() -> str:
    """Mode yang sedang dipakai. Jatuh ke bawaan config kalau belum pernah diset."""
    global _mode
    if _mode is None:
        bawaan = get_settings().DETECTION_MODE
        _mode = bawaan if bawaan in MODE_IDS else MODE_POSE
    return _mode


def set_mode(mode: str) -> None:
    """Ganti mode detektor. Model mode baru dimuat malas saat frame pertama."""
    global _mode
    if mode not in MODE_IDS:
        raise ValueError(f"Mode tidak dikenal: {mode!r}. Pilihan: {sorted(MODE_IDS)}")
    with _load_lock:
        if _mode == mode:
            return
        _mode = mode
    log.info(f"🔀 Mode deteksi diganti ke '{mode}'")


# ---- Pemuatan model ----------------------------------------

def _muat(mode: str):
    """Ambil model untuk satu mode, muat dari berkas kalau belum ada di cache."""
    model = _models.get(mode)
    if model is not None:
        return model

    with _load_lock:
        # Diperiksa ulang di dalam lock: thread lain bisa saja sudah memuatnya
        # selagi kita menunggu giliran.
        model = _models.get(mode)
        if model is not None:
            return model

        from ultralytics import YOLO

        settings = get_settings()

        if mode == MODE_POSE:
            path = settings.POSE_MODEL_PATH
            if not Path(path).exists():
                # Berkas rilis standar Ultralytics, jadi aman diunduh otomatis.
                # Tetap dicatat di log supaya kalau ini terjadi saat demo tanpa
                # internet, penyebab gagalnya langsung kelihatan.
                log.info(f"⚠️ Model pose tidak ada di '{path}'.")
                log.info("   Ultralytics akan mengunduh 'yolo11n-pose.pt' (butuh internet).")
                path = "yolo11n-pose.pt"
        else:
            path = settings.MODEL_PATH
            if not Path(path).exists():
                log.info(f"⚠️ Model custom belum ditemukan di '{path}'.")
                log.info("   Menggunakan base model 'yolo11n.pt' sebagai fallback sementara (mode demo).")
                log.info("   [DEMO MODE] Untuk mensimulasikan JATUH, tunjukkan 'cell phone' ke kamera!")
                path = "yolo11n.pt"

                global _CLASS_MAP
                _CLASS_MAP = {
                    0: PostureClass.NORMAL,             # Person -> Normal
                    67: PostureClass.LYING_ON_GROUND,   # Cell phone -> Jatuh
                }

        _models[mode] = YOLO(path)
        log.info(f"✅ Model '{mode}' loaded: {path}")
        return _models[mode]


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

# Ambang hasil kalibrasi EXP-009, dalam derajat terhadap lantai
# (0 = rebah mendatar, 90 = tegak berdiri).
_SUDUT_REBAH = 20.0
_SUDUT_REBAH_LONGGAR = 32.0   # dipakai kalau kotaknya jelas melebar
_SUDUT_TRANSISI = 60.0
_AR_REBAH = 1.15
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
        # Bahu atau pinggul tidak terbaca -- sudutnya ditebak dari bentuk kotak.
        #
        # `mutu` sengaja tidak dinaikkan di sini. Karena _KP_MIN_CONF (0,25) ada
        # di bawah CONFIDENCE_THRESHOLD (0,5), tebakan ini SELALU dibaca pipeline
        # sebagai UNCERTAIN. Konsekuensinya disengaja: di mode pose, jatuh hanya
        # dikonfirmasi kalau skeletonnya benar-benar terbaca. Saat tidak terbaca,
        # timer DITAHAN (bukan direset), jadi hitungan dilanjutkan begitu sendinya
        # terlihat lagi. Posturnya tetap dihitung supaya kotaknya bisa digambar
        # di stream untuk diagnosa.
        sudut = 90.0 if aspect_ratio < 0.8 else (20.0 if aspect_ratio > 1.3 else 50.0)

    if sudut < _SUDUT_REBAH or (aspect_ratio > _AR_REBAH and sudut < _SUDUT_REBAH_LONGGAR):
        postur = PostureClass.LYING_ON_GROUND
    elif sudut < _SUDUT_TRANSISI or aspect_ratio > _AR_TRANSISI:
        postur = PostureClass.TRANSITIONAL
    else:
        postur = PostureClass.NORMAL

    return postur, mutu


# ---- Inference ---------------------------------------------

def run_inference(frame: np.ndarray) -> Optional[DetectionResult]:
    """Jalankan inference pada satu frame, memakai mode yang sedang aktif.

    Args:
        frame: Frame video dalam format numpy array (BGR, dari OpenCV).

    Returns:
        DetectionResult dengan postur terdeteksi, confidence, dan bounding box.
        None jika model benar-benar tidak menemukan apa pun.

    Catatan: penyaringan memakai DETECTION_MIN_CONF (sangat rendah), BUKAN
    CONFIDENCE_THRESHOLD. Keputusan "cukup yakin atau tidak" dibuat di
    detection_pipeline supaya cabang UNCERTAIN benar-benar berfungsi, dan supaya
    deteksi berkeyakinan rendah tetap bisa digambar di stream untuk diagnosa.
    """
    mode = mode_aktif()
    model = _muat(mode)
    settings = get_settings()

    with _infer_lock:
        results = model(frame, verbose=False, conf=settings.DETECTION_MIN_CONF)

    if not results or len(results[0].boxes) == 0:
        return None

    boxes = results[0].boxes
    best_idx = int(boxes.conf.argmax().item())
    confidence = float(boxes.conf[best_idx].item())
    bbox = boxes.xyxy[best_idx].tolist()

    if mode == MODE_POSE:
        keypoints = getattr(results[0], "keypoints", None)
        if keypoints is None or keypoints.data is None or len(keypoints.data) <= best_idx:
            # Bukan model pose, atau keypoint-nya tidak keluar untuk kotak ini.
            return None

        x1, y1, x2, y2 = bbox
        aspect_ratio = max(1.0, x2 - x1) / max(1.0, y2 - y1)
        kpts = keypoints.data[best_idx].cpu().numpy()

        postur, mutu = _postur_dari_pose(kpts, aspect_ratio)
        # Yang dilaporkan adalah yang paling lemah di antara "ini benar orang"
        # dan "posturnya terbaca jelas".
        return DetectionResult(
            posture=postur,
            confidence=min(confidence, mutu),
            bbox=bbox,
            keypoints=kpts.tolist(),
        )

    cls_id = int(boxes.cls[best_idx].item())
    return DetectionResult(
        posture=_CLASS_MAP.get(cls_id, PostureClass.NORMAL),
        confidence=confidence,
        bbox=bbox,
    )


def unload_model() -> None:
    """Unload semua model dari memori (untuk cleanup).

    Mode aktif ikut dilupakan supaya pemanggilan berikutnya membacanya ulang dari
    settings -- penting agar pengujian tidak saling mewarisi mode.
    """
    global _mode
    with _load_lock:
        _models.clear()
        _mode = None

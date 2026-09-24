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

from pathlib import Path
from typing import Optional

import numpy as np

from app.core.config import get_settings
from app.models.schemas import DetectionResult, PostureClass

# Label mapping — harus sesuai dengan data.yaml di ml/
_CLASS_MAP = {
    0: PostureClass.NORMAL,
    1: PostureClass.TRANSITIONAL,
    2: PostureClass.LYING_ON_GROUND,
}

# Singleton model instance
_model = None


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

    from ultralytics import YOLO

    settings = get_settings()
    path = model_path or settings.MODEL_PATH

    if not Path(path).exists():
        raise FileNotFoundError(
            f"Model tidak ditemukan: {path}. "
            "Pastikan sudah menjalankan training terlebih dahulu."
        )

    _model = YOLO(path)
    print(f"✅ Model loaded: {path}")
    return _model


def run_inference(frame: np.ndarray) -> Optional[DetectionResult]:
    """Jalankan inference pada satu frame.

    Args:
        frame: Frame video dalam format numpy array (BGR, dari OpenCV).

    Returns:
        DetectionResult dengan postur terdeteksi, confidence, dan bounding box.
        None jika tidak ada deteksi.
    """
    model = load_model()
    settings = get_settings()

    results = model(frame, verbose=False, conf=settings.CONFIDENCE_THRESHOLD)

    if not results or len(results[0].boxes) == 0:
        return None

    # Ambil deteksi dengan confidence tertinggi
    boxes = results[0].boxes
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


def unload_model() -> None:
    """Unload model dari memori (untuk cleanup)."""
    global _model
    _model = None

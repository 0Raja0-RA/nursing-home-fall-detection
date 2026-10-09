"""
tune_pose_fall.py
=================
EXP-009: Pose Kinematic Threshold Tuning & Benchmark on UR Fall Dataset.

Langkah Kerja:
1. Ekstraksi fitur sendi (Spine Angle, Aspect Ratio, Confidence) pada Validation Set (254 gambar).
2. Grid Search otomatis untuk menemukan kombinasi threshold sudut optimal:
   - fall_angle: [20°, 25°, 30°, 35°, 40°, 45°]
   - trans_angle: [45°, 50°, 55°, 60°, 65°]
   - aspect_ratio: [1.0, 1.15, 1.25, 1.35]
   - Objektif: Memaksimalkan Macro F1 & Recall kasus jatuh (safety-first).
3. Evaluasi akhir pada Test Set (320 gambar) menggunakan threshold terbaik.
4. Menghasilkan Confusion Matrix dan komparasi head-to-head dengan EXP-006.

Penggunaan:
    python ml/scripts/tune_pose_fall.py
"""

import argparse
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np
from ultralytics import YOLO

CLASS_NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}


def calculate_spine_angle(kpts: np.ndarray) -> float:
    """Menghitung sudut kemiringan tulang belakang terhadap bidang horizontal (0° - 90°)."""
    l_sh, r_sh = kpts[5][:2], kpts[6][:2]
    l_hip, r_hip = kpts[11][:2], kpts[12][:2]

    mid_sh = ((l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2)
    mid_hip = ((l_hip[0] + r_hip[0]) / 2, (l_hip[1] + r_hip[1]) / 2)

    dx = mid_sh[0] - mid_hip[0]
    dy = mid_sh[1] - mid_hip[1]

    rad = math.atan2(abs(dy), abs(dx))
    return math.degrees(rad)


def get_ground_truth(label_file: Path) -> int | None:
    """Membaca label kelas ground truth dari file .txt YOLO."""
    if not label_file.exists():
        return None
    with open(label_file, "r") as f:
        lines = [line.strip().split() for line in f if line.strip()]
    if not lines:
        return None
    # Ambil label dari deteksi pertama
    return int(lines[0][0])


def extract_sample_features(img_path: Path, label_path: Path, model: YOLO, conf_thresh: float = 0.25):
    """Mengekstrak fitur pose dan ground truth dari satu gambar."""
    gt = get_ground_truth(label_path)
    if gt is None:
        return None

    results = model(str(img_path), verbose=False, conf=conf_thresh)
    if not results or len(results[0].boxes) == 0:
        # Fallback jika model sama sekali tidak mendeteksi orang di frame
        return {
            "img": img_path.name,
            "gt": gt,
            "detected": False,
            "angle": 90.0,
            "aspect_ratio": 0.5,
            "conf": 0.0,
        }

    # Ambil orang dengan confidence tertinggi
    boxes = results[0].boxes
    best_idx = int(boxes.conf.argmax().item())
    conf = float(boxes.conf[best_idx].item())
    bbox = boxes.xyxy[best_idx].tolist()
    kpts = results[0].keypoints.data[best_idx].cpu().numpy()

    x1, y1, x2, y2 = bbox
    w = max(1.0, x2 - x1)
    h = max(1.0, y2 - y1)
    aspect_ratio = w / h

    # Periksa confidence sendi bahu & pinggul
    sh_conf = (kpts[5][2] + kpts[6][2]) / 2
    hip_conf = (kpts[11][2] + kpts[12][2]) / 2

    if sh_conf > 0.25 and hip_conf > 0.25:
        angle = calculate_spine_angle(kpts)
    else:
        # Fallback geometris dari aspect ratio jika bahu/pinggul tertutup
        angle = 90.0 if aspect_ratio < 0.8 else (20.0 if aspect_ratio > 1.3 else 50.0)

    return {
        "img": img_path.name,
        "gt": gt,
        "detected": True,
        "angle": angle,
        "aspect_ratio": aspect_ratio,
        "conf": conf,
    }


def predict_class(angle: float, aspect_ratio: float, fall_angle: float, trans_angle: float, ar_thresh: float) -> int:
    """Mengklasifikasikan postur berdasarkan kombinasi threshold sudut & aspect ratio."""
    # 2: lying_on_ground, 1: transitional, 0: normal
    if angle < fall_angle or (aspect_ratio > ar_thresh and angle < (fall_angle + 12.0)):
        return 2
    elif angle < trans_angle or aspect_ratio > 0.95:
        return 1
    else:
        return 0


def calculate_metrics(y_true: list[int], y_pred: list[int]):
    """Menghitung Confusion Matrix, Precision, Recall, dan F1 per kelas."""
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1

    total = len(y_true)
    accuracy = np.trace(cm) / total if total > 0 else 0.0

    precisions = {}
    recalls = {}
    f1s = {}

    for c in range(3):
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

        precisions[c] = p
        recalls[c] = r
        f1s[c] = f1

    macro_f1 = sum(f1s.values()) / 3
    macro_precision = sum(precisions.values()) / 3
    macro_recall = sum(recalls.values()) / 3

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "per_class": {
            CLASS_NAMES[c]: {"precision": precisions[c], "recall": recalls[c], "f1": f1s[c]}
            for c in range(3)
        },
        "cm": cm,
    }


def main():
    parser = argparse.ArgumentParser(description="Tuning Pose Thresholds on UR Fall Dataset")
    parser.add_argument("--data-dir", type=str, default="ml/data/processed", help="Path dataset processed")
    parser.add_argument("--model", type=str, default="yolo11n-pose.pt", help="Base model pose")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    val_img_dir = data_dir / "images" / "val"
    val_lbl_dir = data_dir / "labels" / "val"
    test_img_dir = data_dir / "images" / "test"
    test_lbl_dir = data_dir / "labels" / "test"

    print("=" * 65)
    print("🔬 [EXP-009] GRID SEARCH KINEMATIC THRESHOLD TUNING (YOLO11-POSE)")
    print("=" * 65)
    print(f"📁 Dataset Directory : {data_dir}")
    print(f"🤖 Model Architecture: {args.model}\n")

    model = YOLO(args.model)

    # ------------------------------------------------------------
    # STEP 1: Ekstraksi Fitur Validation Set
    # ------------------------------------------------------------
    val_images = sorted(list(val_img_dir.glob("*.jpg")) + list(val_img_dir.glob("*.png")))
    print(f"⏳ Mengekstrak fitur dari {len(val_images)} gambar Validation Set...")
    t0 = time.time()

    val_features = []
    for img_p in val_images:
        lbl_p = val_lbl_dir / f"{img_p.stem}.txt"
        feat = extract_sample_features(img_p, lbl_p, model)
        if feat:
            val_features.append(feat)

    print(f"✅ Selesai mengekstrak {len(val_features)} sampel val dalam {time.time() - t0:.2f} detik!\n")

    # ------------------------------------------------------------
    # STEP 2: Grid Search Parameter Optimization
    # ------------------------------------------------------------
    print("🔍 Menjalankan Grid Search untuk mencari sudut derajat optimal...")
    fall_angle_candidates = [20.0, 25.0, 30.0, 33.0, 35.0, 38.0, 40.0]
    trans_angle_candidates = [45.0, 48.0, 50.0, 53.0, 55.0, 58.0, 60.0]
    ar_candidates = [1.05, 1.15, 1.25, 1.35]

    y_val_true = [f["gt"] for f in val_features]

    best_score = -1.0
    best_params = {}
    best_val_metrics = None

    for fa in fall_angle_candidates:
        for ta in trans_angle_candidates:
            if ta <= fa:
                continue
            for ar in ar_candidates:
                y_val_pred = [
                    predict_class(f["angle"], f["aspect_ratio"], fa, ta, ar)
                    for f in val_features
                ]
                m = calculate_metrics(y_val_true, y_val_pred)

                # Formula Skor Prioritas:
                # Keselamatan lansia no 1 -> Lying Recall diberi bobot tertinggi (50%) + Macro F1 (50%)
                lying_r = m["per_class"]["lying_on_ground"]["recall"]
                macro_f1 = m["macro_f1"]
                score = (0.5 * lying_r) + (0.5 * macro_f1)

                if score > best_score:
                    best_score = score
                    best_params = {"fall_angle": fa, "trans_angle": ta, "aspect_ratio": ar}
                    best_val_metrics = m

    print("✨ HASIL OPTIMALISASI VALIDATION SET:")
    print(f"  • Optimal Fall Angle Threshold  : < {best_params['fall_angle']:.1f}°")
    print(f"  • Optimal Trans Angle Threshold : < {best_params['trans_angle']:.1f}°")
    print(f"  • Optimal Aspect Ratio Threshold: > {best_params['aspect_ratio']:.2f}")
    print(f"  • Val Accuracy                  : {best_val_metrics['accuracy'] * 100:.2f}%")
    print(f"  • Val Macro F1                  : {best_val_metrics['macro_f1'] * 100:.2f}%")
    print(f"  • Val Lying Recall              : {best_val_metrics['per_class']['lying_on_ground']['recall'] * 100:.2f}%\n")

    # ------------------------------------------------------------
    # STEP 3: Evaluasi Independen pada Test Set (320 Gambar)
    # ------------------------------------------------------------
    test_images = sorted(list(test_img_dir.glob("*.jpg")) + list(test_img_dir.glob("*.png")))
    print(f"🧪 Menjalankan evaluasi independen pada {len(test_images)} gambar Test Set...")
    t1 = time.time()

    test_features = []
    for img_p in test_images:
        lbl_p = test_lbl_dir / f"{img_p.stem}.txt"
        feat = extract_sample_features(img_p, lbl_p, model)
        if feat:
            test_features.append(feat)

    elapsed_test = time.time() - t1
    avg_latency_ms = (elapsed_test / len(test_features)) * 1000 if test_features else 0.0

    y_test_true = [f["gt"] for f in test_features]
    y_test_pred = [
        predict_class(
            f["angle"],
            f["aspect_ratio"],
            best_params["fall_angle"],
            best_params["trans_angle"],
            best_params["aspect_ratio"],
        )
        for f in test_features
    ]

    test_metrics = calculate_metrics(y_test_true, y_test_pred)

    print("\n" + "=" * 65)
    print("📊 HASIL RESMI TEST SET EXP-009 (KINEMATIC POSE ESTIMATION):")
    print("=" * 65)
    print(f"• Test Accuracy   : {test_metrics['accuracy'] * 100:.2f}%")
    print(f"• Macro F1-Score  : {test_metrics['macro_f1'] * 100:.2f}%")
    print(f"• Macro Precision : {test_metrics['macro_precision'] * 100:.2f}%")
    print(f"• Macro Recall    : {test_metrics['macro_recall'] * 100:.2f}%")
    print(f"• Inference Speed : {avg_latency_ms:.2f} ms (~{1000/avg_latency_ms:.1f} FPS)")
    print("-" * 65)
    print("Breakdown per Kelas (Test Set):")
    for c_name, scores in test_metrics["per_class"].items():
        print(f"  - {c_name:<16}: Precision = {scores['precision']*100:6.2f}% | Recall = {scores['recall']*100:6.2f}% | F1 = {scores['f1']*100:6.2f}%")
    print("-" * 65)
    print("Confusion Matrix (Baris: Ground Truth, Kolom: Prediksi):")
    print("               Pred: Normal  Trans  Lying")
    for i, row in enumerate(test_metrics["cm"]):
        print(f"  Actual {CLASS_NAMES[i]:<12}: {row[0]:6d} {row[1]:6d} {row[2]:6d}")
    print("=" * 65)

    # Simpan hasil ke JSON untuk rekam jejak
    out_json = {
        "experiment_id": "EXP-009",
        "model": args.model,
        "best_params": best_params,
        "val_metrics": {k: v for k, v in best_val_metrics.items() if k != "cm"},
        "test_metrics": {
            "accuracy": test_metrics["accuracy"],
            "macro_f1": test_metrics["macro_f1"],
            "macro_precision": test_metrics["macro_precision"],
            "macro_recall": test_metrics["macro_recall"],
            "latency_ms": avg_latency_ms,
            "per_class": test_metrics["per_class"],
            "cm": test_metrics["cm"].tolist(),
        },
    }

    out_file = Path("ml/training/exp009_results.json")
    with open(out_file, "w") as f:
        json.dump(out_json, f, indent=2)

    print(f"\n💾 Rekam jejak evaluasi berhasil disimpan di: {out_file.resolve()}")


if __name__ == "__main__":
    main()

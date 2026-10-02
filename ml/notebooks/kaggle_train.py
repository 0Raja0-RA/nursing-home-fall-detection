"""
kaggle_train.py
===============
Template script training YOLO11 (EXP-006: Hybrid Optimization)
untuk dijalankan di Kaggle Notebook (GPU T4 x1).

Dataset Path:
/kaggle/input/datasets/rajarahmanaziiz/fall-detection-dataset
(Format folder langsung tanpa perlu unzip)
"""

# ============================================================
# CELL 1: Install & Setup Environment
# ============================================================
# !pip install -q ultralytics

import os
from pathlib import Path
import torch
import yaml
from ultralytics import YOLO

print(f"PyTorch Version : {torch.__version__}")
print(f"CUDA Available  : {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device Name     : {torch.cuda.get_device_name(0)}")

# ============================================================
# CELL 2: Deteksi Lokasi Dataset (Direct Folder / Tanpa Unzip)
# ============================================================
# Path utama sesuai dataset Kaggle pengguna
primary_dataset_path = Path("/kaggle/input/datasets/rajarahmanaziiz/fall-detection-dataset")
fallback_candidates = [
    primary_dataset_path,
    Path("/kaggle/input/fall-detection-dataset"),
    Path("/kaggle/input/urfall-yolo-dataset"),
]

dataset_dir = None

# Cek path utama terlebih dahulu
for candidate in fallback_candidates:
    if candidate.exists():
        if (candidate / "images").exists():
            dataset_dir = candidate
            break
        # Jika bersarang satu tingkat di dalam subfolder
        sub_images = list(candidate.glob("**/images"))
        if sub_images:
            dataset_dir = sub_images[0].parent
            break

# Fallback otomatis jika nama folder input di Kaggle berbeda
if not dataset_dir:
    kaggle_input = Path("/kaggle/input")
    found_images = list(kaggle_input.glob("**/images"))
    if found_images:
        dataset_dir = found_images[0].parent

if dataset_dir:
    print(f"✅ Dataset berhasil ditemukan di: {dataset_dir}")
    print(f"   Train images : {len(list((dataset_dir / 'images' / 'train').glob('*')))} file")
    print(f"   Val images   : {len(list((dataset_dir / 'images' / 'val').glob('*')))} file")
    print(f"   Test images  : {len(list((dataset_dir / 'images' / 'test').glob('*')))} file")
else:
    raise FileNotFoundError("❌ Folder dataset tidak ditemukan di /kaggle/input! Periksa input dataset Anda.")

# ============================================================
# CELL 3: Buat data.yaml di /kaggle/working/data.yaml
# ============================================================
work_dir = Path("/kaggle/working")
kaggle_yaml_path = work_dir / "data.yaml"

data_yaml_content = {
    "path": str(dataset_dir.resolve()),
    "train": "images/train",
    "val": "images/val",
    "test": "images/test",
    "nc": 3,
    "names": {
        0: "normal",
        1: "transitional",
        2: "lying_on_ground"
    }
}

with open(kaggle_yaml_path, "w") as f:
    yaml.dump(data_yaml_content, f, default_flow_style=False)

print(f"\n✓ File data.yaml berhasil dibuat di: {kaggle_yaml_path}")
print("-" * 35)
print(open(kaggle_yaml_path).read())
print("-" * 35)

# ============================================================
# CELL 4: Training EXP-006 (The Hybrid Optimization)
# ============================================================
# Konsep EXP-006:
# 1. Base model yolo11n (2.58M params) - terbukti tahan overfit
# 2. Optimizer AdamW + Cosine Annealing (lr0=0.001) - stabilitas presisi
# 3. Epochs 70 + Patience 30 - memaksimalkan recall (keselamatan lansia)
# 4. Augmentasi Real-World (Night / Low-light & Random Erasing / Occlusion)
# 5. Class Loss Weight (cls=1.0) - mempertajam pembedaan lying vs transitional

print("🚀 Memulai Training EXP-006 (Hybrid Optimizer & Night Augmentation)...")

model = YOLO("yolo11n.pt")

results = model.train(
    data=str(kaggle_yaml_path),
    epochs=70,
    patience=30,
    batch=16,
    imgsz=640,
    optimizer="AdamW",
    lr0=0.001,
    lrf=0.01,
    cos_lr=True,
    cls=1.0,            # Penalti loss klasifikasi dinaikkan untuk ketegasan kelas
    # Augmentasi simulasi kondisi nyata panti jompo:
    hsv_v=0.6,          # Simulasi variasi cahaya minim / malam hari
    hsv_s=0.7,
    hsv_h=0.015,
    bgr=0.2,            # Simulasi mode infrared/monokrom CCTV malam hari
    erasing=0.4,        # Simulasi tubuh tertutup selimut/kursi (occlusion)
    flipud=0.0,         # Dilarang flip vertikal (arah gravitasi lantai krusial)
    fliplr=0.5,         # Horizontal flip mirror aman
    mosaic=1.0,
    close_mosaic=10,
    project="/kaggle/working/models",
    name="exp006_hybrid_adamw",
    exist_ok=True,
    save=True
)

print("\n🎉 Training EXP-006 Selesai!")
print(f"Hasil tersimpan di: {results.save_dir}")

# ============================================================
# CELL 5: Evaluasi Test Set & Metrik Akhir
# ============================================================
print("\n🔍 Menjalankan evaluasi pada Test Set...")
metrics = model.val(data=str(kaggle_yaml_path), split="test")

print("\n" + "=" * 50)
print("📊 HASIL METRIK TEST SET EXP-006:")
print("=" * 50)
print(f"• Test mAP50    : {metrics.box.map50 * 100:.2f}%")
print(f"• Test mAP50-95 : {metrics.box.map * 100:.2f}%")
print(f"• Test Precision: {metrics.box.mp * 100:.2f}%")
print(f"• Test Recall   : {metrics.box.mr * 100:.2f}%")
print("=" * 50)
print("\n📁 Model bobot terbaik:")
print(f"{results.save_dir}/weights/best.pt")

"""
kaggle_train.py
===============
Template script training YOLO11 (EXP-008: Scale-Up Model Capacity & High Resolution)
untuk dijalankan di Kaggle Notebook (GPU T4 x1 / P100).

Eksperimen : EXP-008
Model      : yolo11s.pt (Small - 9.4M parameter)
Resolusi   : imgsz=800 (Resolusi tinggi untuk menangkap postur halus)
Hypothesis : Mengatasi kekeliruan postur (transitional vs normal/lying) dan
             distraksi perabotan/cahaya ekstrem dengan kapasitas model lebih besar
             serta resolusi piksel lebih detail.
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
primary_dataset_path = Path("/kaggle/input/datasets/rajarahmanaziiz/fall-detection-dataset")
fallback_candidates = [
    primary_dataset_path,
    Path("/kaggle/input/fall-detection-dataset"),
    Path("/kaggle/input/urfall-yolo-dataset"),
]

dataset_dir = None

for candidate in fallback_candidates:
    if candidate.exists():
        if (candidate / "images").exists():
            dataset_dir = candidate
            break
        sub_images = list(candidate.glob("**/images"))
        if sub_images:
            dataset_dir = sub_images[0].parent
            break

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
# CELL 4: Training EXP-008 (yolo11s.pt + imgsz=800 + Robust Augs)
# ============================================================
# Fitur Utama EXP-008:
# 1. Base Model: yolo11s.pt (Small - 9.4M params) -> 3.5x kapasitas dari Nano
# 2. Input Size: 800x800 -> detail tubuh manusia saat berdiri/duduk lebih tajam
# 3. Label Smoothing: 0.05 -> meredam keraguan model pada kelas 'transitional'
# 4. Class Loss Weight (cls=1.2) -> fokus ekstra membedakan 3 kelas postur
# 5. Night/Glare Augmentations: hsv_v=0.6, hsv_s=0.7, erasing=0.4, scale=0.5

print("🚀 [EXP-008] Memulai Training YOLO11s (Resolution 800x800)...")

model = YOLO("yolo11s.pt")

results = model.train(
    data=str(kaggle_yaml_path),
    epochs=70,
    patience=25,
    batch=16,           # Sesuai kapasitas VRAM 16GB GPU T4 di resolusi 800
    imgsz=800,          # Skala resolusi tinggi
    optimizer="AdamW",
    lr0=0.001,
    lrf=0.01,
    cos_lr=True,
    cls=1.2,            # Bobot klasifikasi dinaikkan untuk ketepatan postur
    label_smoothing=0.05, # Mengurangi ambiguitas transitional
    # Robust augmentations (atasi silau, bayangan & background clutter):
    hsv_v=0.6,          # Variasi kecerahan drastis (simulasi pencahayaan kamar/silau)
    hsv_s=0.7,          # Variasi saturasi warna
    hsv_h=0.015,
    bgr=0.2,            # Channel flip simulasi tone IR / CCTV
    erasing=0.4,        # Cutout sebagian tubuh (simulasi tertutup selimut/meja)
    scale=0.5,          # Multi-scale zoom (orang dekat vs jauh dari kamera)
    flipud=0.0,
    fliplr=0.5,
    mosaic=1.0,
    close_mosaic=10,
    project="/kaggle/working/models",
    name="exp008_yolo11s_imgsz800",
    exist_ok=True,
    save=True
)

best_model_path = Path(results.save_dir) / "weights" / "best.pt"
print(f"\n✅ Training selesai! Model terbaik disimpan di: {best_model_path}")

# ============================================================
# CELL 5: Evaluasi Test Set Model Akhir
# ============================================================
print("\n🔍 Menjalankan evaluasi pada Test Set untuk EXP-008...")
eval_model = YOLO(str(best_model_path))
metrics = eval_model.val(data=str(kaggle_yaml_path), split="test", imgsz=800)

print("\n" + "=" * 55)
print("📊 HASIL EVALUASI TEST SET EXP-008 (YOLO11s @ 800x800):")
print("=" * 55)
print(f"• Test mAP50        : {metrics.box.map50 * 100:.2f}%")
print(f"• Test mAP50-95     : {metrics.box.map * 100:.2f}%")
print(f"• Test Precision    : {metrics.box.mp * 100:.2f}%")
print(f"• Test Recall       : {metrics.box.mr * 100:.2f}%")
print("-" * 55)

# Tampilkan metrik per-kelas jika tersedia
if hasattr(metrics.box, 'maps') and len(metrics.box.maps) == 3:
    class_names = ["normal", "transitional", "lying_on_ground"]
    for i, name in enumerate(class_names):
        print(f"  - {name:<16}: mAP50-95 = {metrics.box.maps[i] * 100:.2f}%")

print("=" * 55)
print(f"\n📁 File bobot terbaik siap diunduh:")
print(f"   {best_model_path}")

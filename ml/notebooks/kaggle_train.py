"""
kaggle_train.py
===============
Template script training YOLO11 untuk dijalankan di Kaggle Notebook (GPU T4 / P100).

Cara Pakai di Kaggle:
---------------------
1. Upload 'urfall_yolo_dataset.zip' ke Kaggle Datasets (beri nama misal: 'urfall-yolo-dataset').
2. Buat Notebook baru di Kaggle, aktifkan GPU T4 di menu: Settings -> Accelerator -> GPU T4 x1.
3. Tambahkan dataset tadi lewat menu: + Add Data -> Your Datasets -> urfall-yolo-dataset.
4. Salin kode di bawah ini ke dalam cell Kaggle dan jalankan!
"""

# ============================================================
# CELL 1: Install & Setup Environment
# ============================================================
# !pip install -q ultralytics

import os
import shutil
import zipfile
from pathlib import Path
from ultralytics import YOLO
import yaml

# Cek GPU
import torch
print(f"CUDA Available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"Device Name   : {torch.cuda.get_device_name(0)}")

# ============================================================
# CELL 2: Ekstrak Dataset di Workspace Kaggle
# ============================================================
# Path input dataset dari Kaggle (sesuaikan dengan nama dataset yang kamu buat)
kaggle_input_dir = Path("/kaggle/input")
work_dir = Path("/kaggle/working")
dataset_dir = work_dir / "dataset"

# Cari file zip dataset di input
zip_candidates = list(kaggle_input_dir.glob("*/*.zip")) + list(kaggle_input_dir.glob("*.zip"))

if zip_candidates:
    zip_path = zip_candidates[0]
    print(f"Mengekstrak {zip_path} ke {dataset_dir}...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dataset_dir)
    print("Ekstraksi selesai!")
else:
    # Jika dataset di-upload sebagai folder tanpa zip
    possible_dir = list(kaggle_input_dir.glob("*/images"))
    if possible_dir:
        dataset_dir = possible_dir[0].parent
        print(f"Dataset ditemukan di: {dataset_dir}")
    else:
        print("[PERINGATAN] Dataset zip tidak ditemukan, periksa /kaggle/input!")

# ============================================================
# CELL 3: Buat data.yaml dengan Path Kaggle
# ============================================================
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

kaggle_yaml_path = work_dir / "data.yaml"
with open(kaggle_yaml_path, "w") as f:
    yaml.dump(data_yaml_content, f, default_flow_style=False)

print(f"File data.yaml berhasil dibuat di: {kaggle_yaml_path}")
print(open(kaggle_yaml_path).read())

# ============================================================
# CELL 4: Training Baseline YOLO11
# ============================================================
print("Memulai training baseline YOLO11...")

model = YOLO("yolo11n.pt")  # Base model nano

results = model.train(
    data=str(kaggle_yaml_path),
    epochs=50,
    batch=16,
    imgsz=640,
    patience=15,
    lr0=0.01,
    lrf=0.01,
    optimizer="auto",
    flipud=0.0,       # Matikan vertical flip untuk deteksi jatuh
    fliplr=0.5,       # Mirror horizontal kiri-kanan
    mosaic=1.0,
    project="/kaggle/working/models",
    name="baseline_yolo11n",
    exist_ok=True,
    save=True
)

print("\nTraining Baseline Selesai!")
print(f"Hasil tersimpan di: {results.save_dir}")

# ============================================================
# CELL 5: Evaluasi Test Set & Simpan Model
# ============================================================
# Validasi akhir menggunakan test set
metrics = model.val(data=str(kaggle_yaml_path), split="test")

print("\n--- HASIL METRIK TEST SET ---")
print(f"mAP50-95 : {metrics.box.map:.4f}")
print(f"mAP50    : {metrics.box.map50:.4f}")
print(f"Precision: {metrics.box.mp:.4f}")
print(f"Recall   : {metrics.box.mr:.4f}")

# Model terbaik siap di-download dari output Kaggle:
# /kaggle/working/models/baseline_yolo11n/weights/best.pt

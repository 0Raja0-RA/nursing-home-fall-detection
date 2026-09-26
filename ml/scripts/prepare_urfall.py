"""
prepare_urfall.py
=================
Pipeline preprocessing lengkap untuk UR Fall Detection Dataset:
1. Membaca CSV ground truth (urfall-cam0-falls.csv & urfall-cam0-adls.csv).
2. Membaca gambar RGB Cam0 langsung dari file ZIP di Downloads (tanpa boros disk).
3. Melakukan 'Smart Deduplication' (pHash) untuk mengatasi class imbalance:
   - 'normal': dedup agresif (buang frame statis).
   - 'lying_on_ground': dedup moderat (buang frame rebahan yang identik).
   - 'transitional' (falling): TIDAK DI-DEDUP sama sekali (fase kritis sangat berharga).
4. Auto-Annotation Bounding Box menggunakan pre-trained YOLO11 (deteksi objek 'person').
5. Melakukan Group Split 70% Train / 15% Val / 15% Test berbasis sequence video (mencegah data leakage).
6. Menyimpan ke format standar YOLO (images/ & labels/) + data.yaml.
7. Opsional: Mengompresi hasil ke file .zip siap upload ke Kaggle / Hugging Face.

Penggunaan:
    python ml/scripts/prepare_urfall.py --downloads-dir "C:/Users/Raja/Downloads" --zip-output
"""

import argparse
import csv
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Progress bar fallback jika tqdm belum terinstall
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc="", **kwargs):
        print(f"--> {desc}...")
        return iterable


# ============================================================
# Pemetaan Kelas UR Fall ke YOLO
# ============================================================
# -1 : person is not lying -> 0 (normal)
#  0 : temporary pose      -> 1 (transitional)
#  1 : lying on the ground -> 2 (lying_on_ground)
UR_FALL_TO_YOLO = {
    -1: 0,  # normal
    0: 1,   # transitional
    1: 2    # lying_on_ground
}

CLASS_NAMES = ["normal", "transitional", "lying_on_ground"]


def compute_phash(img_gray: np.ndarray, hash_size: int = 8) -> np.ndarray:
    """Hitung perceptual hash (pHash 64-bit) untuk perbandingan kemiripan gambar."""
    resized = cv2.resize(img_gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    """Hitung selisih hamming distance antara 2 hash."""
    return int(np.count_nonzero(h1 != h2))


def parse_csv_labels(csv_path: Path) -> Dict[str, Dict[int, int]]:
    """
    Baca CSV UR Fall dan buat lookup table:
    { sequence_name: { frame_number: label_id } }
    Contoh: labels['fall-01'][10] = -1
    """
    labels: Dict[str, Dict[int, int]] = {}
    if not csv_path.exists():
        print(f"[WARN] File CSV tidak ditemukan: {csv_path}")
        return labels

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 3:
                continue
            seq_name = row[0].strip()
            try:
                frame_num = int(row[1].strip())
                label_val = int(row[2].strip())
                if seq_name not in labels:
                    labels[seq_name] = {}
                labels[seq_name][frame_num] = label_val
            except ValueError:
                continue
    return labels


def determine_split(seq_name: str, is_fall: bool) -> str:
    """
    Group Split berdasarkan nomor sequence video:
    - 70% Train, 15% Val, 15% Test
    Mencegah frame dari video yang sama bocor antar split (Data Leakage).
    """
    match = re.search(r"\d+", seq_name)
    num = int(match.group(0)) if match else 1

    if is_fall:
        # 30 sequence fall
        if num <= 21:
            return "train"   # 21 video (70%)
        elif num <= 25:
            return "val"     # 4 video (13.3%)
        else:
            return "test"    # 5 video (16.7%)
    else:
        # 40 sequence adl
        if num <= 28:
            return "train"   # 28 video (70%)
        elif num <= 34:
            return "val"     # 6 video (15%)
        else:
            return "test"    # 6 video (15%)


def extract_frame_number_from_filename(filename: str) -> Optional[int]:
    """Ekstrak angka frame dari nama file gambar, misal 'fall-01-cam0-rgb-015.png' -> 15."""
    match = re.search(r"-(\d+)\.png$", filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def main():
    parser = argparse.ArgumentParser(description="Pipeline Preprocessing Dataset UR Fall ke format YOLO11.")
    parser.add_argument(
        "--downloads-dir",
        type=str,
        default=r"C:\Users\Raja\Downloads",
        help="Folder tempat file zip dan csv UR Fall berada."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="ml/data/processed",
        help="Direktori output dataset YOLO."
    )
    parser.add_argument(
        "--phash-threshold",
        type=int,
        default=6,
        help="Threshold Hamming distance pHash untuk mendeteksi frame kembar (default: 6)."
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold untuk pre-trained person detector (default: 0.25)."
    )
    parser.add_argument(
        "--zip-output",
        action="store_true",
        help="Kompres folder hasil ke 'ml/data/urfall_yolo_dataset.zip' setelah selesai."
    )
    parser.add_argument(
        "--skip-cam1",
        action="store_true",
        default=True,
        help="Hanya gunakan Cam0 (front/wall view) yang sinkron dengan ground truth CSV."
    )
    args = parser.parse_args()

    downloads_path = Path(args.downloads_dir).resolve()
    output_path = Path(args.output_dir).resolve()

    print("=" * 65)
    print("🚀 MEMULAI PIPELINE PREPROCESSING UR FALL DETECTION KE YOLO11")
    print("=" * 65)
    print(f"• Downloads Path : {downloads_path}")
    print(f"• Output Path    : {output_path}")
    print(f"• Dedup Threshold: {args.phash_threshold} (hanya untuk normal & lying)")
    print("=" * 65)

    # 1. Pastikan library Ultralytics terpasang
    try:
        from ultralytics import YOLO
        print("📦 Memuat pre-trained YOLO11 (yolo11n.pt) untuk auto-annotation...")
        detector = YOLO("yolo11n.pt")
    except ImportError:
        print("\n[ERROR] Library 'ultralytics' belum terinstall!")
        print("Silakan install terlebih dahulu dengan perintah:")
        print("    pip install ultralytics opencv-python numpy\n")
        sys.exit(1)

    # 2. Baca file CSV
    falls_csv = downloads_path / "urfall-cam0-falls.csv"
    adls_csv = downloads_path / "urfall-cam0-adls.csv"

    print("📖 Membaca CSV ground truth...")
    fall_labels = parse_csv_labels(falls_csv)
    adl_labels = parse_csv_labels(adls_csv)

    print(f"   ✓ Fall Sequences dimuat: {len(fall_labels)} sequences")
    print(f"   ✓ ADL Sequences dimuat : {len(adl_labels)} sequences")

    # 3. Cari semua file zip Cam0
    fall_zips = sorted(list(downloads_path.glob("fall-*-cam0-rgb.zip")))
    adl_zips = sorted(list(downloads_path.glob("adl-*-cam0-rgb.zip")))

    if not fall_zips and not adl_zips:
        print(f"\n[ERROR] Tidak ditemukan file 'fall-*-cam0-rgb.zip' atau 'adl-*-cam0-rgb.zip' di {downloads_path}!")
        sys.exit(1)

    print(f"📦 Ditemukan {len(fall_zips)} zip Fall dan {len(adl_zips)} zip ADL.")

    # 4. Siapkan struktur direktori output
    splits = ["train", "val", "test"]
    for s in splits:
        (output_path / "images" / s).mkdir(parents=True, exist_ok=True)
        (output_path / "labels" / s).mkdir(parents=True, exist_ok=True)

    # Statistik penghitung
    stats = {
        "total_extracted": 0,
        "dropped_dedup": 0,
        "no_person_detected": 0,
        "saved_per_split": Counter(),
        "saved_per_class": Counter()
    }

    all_tasks = [(f_zip, True) for f_zip in fall_zips] + [(a_zip, False) for a_zip in adl_zips]

    print("\n⚡ Memproses frame langsung dari ZIP (Smart Dedup + Auto-BBox)...")

    for zip_path, is_fall in tqdm(all_tasks, desc="Memproses video sequence"):
        # Ambil nama sequence, misal 'fall-01-cam0-rgb.zip' -> 'fall-01'
        zip_stem = zip_path.stem
        seq_name = zip_stem.replace("-cam0-rgb", "")
        split = determine_split(seq_name, is_fall)
        label_lookup = fall_labels.get(seq_name, {}) if is_fall else adl_labels.get(seq_name, {})

        last_saved_hash: Optional[np.ndarray] = None

        with zipfile.ZipFile(zip_path, "r") as z:
            # Ambil semua file .png dan urutkan
            png_names = sorted([n for n in z.namelist() if n.lower().endswith(".png")])

            for img_name in png_names:
                stats["total_extracted"] += 1
                frame_num = extract_frame_number_from_filename(img_name)
                if frame_num is None:
                    continue

                # Ambil label kelas dari CSV
                # Default untuk ADL jika frame tidak terdaftar di CSV adalah -1 (normal)
                raw_label = label_lookup.get(frame_num, -1 if not is_fall else None)
                if raw_label is None:
                    continue

                yolo_class_id = UR_FALL_TO_YOLO.get(raw_label, 0)
                class_str = CLASS_NAMES[yolo_class_id]

                # Baca byte gambar langsung dari memori tanpa tulis ke disk
                img_bytes = z.read(img_name)
                img_array = np.frombuffer(img_bytes, dtype=np.uint8)
                img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img_bgr is None:
                    continue

                img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                curr_hash = compute_phash(img_gray)

                # --- SMART DEDUPLICATION ---
                if last_saved_hash is not None:
                    dist = hamming_distance(last_saved_hash, curr_hash)

                    # Aturan 1: Kelas 'transitional' (sedang jatuh) TIDAK PERNAH DI-DROP
                    if yolo_class_id == 1:
                        pass
                    # Aturan 2: Kelas 'normal' di-dedup agresif
                    elif yolo_class_id == 0 and dist <= args.phash_threshold:
                        stats["dropped_dedup"] += 1
                        continue
                    # Aturan 3: Kelas 'lying_on_ground' di-dedup moderat
                    elif yolo_class_id == 2 and dist <= args.phash_threshold:
                        stats["dropped_dedup"] += 1
                        continue

                # --- AUTO-ANNOTATION (YOLO11 Deteksi Orang) ---
                h_img, w_img = img_bgr.shape[:2]
                results = detector(img_bgr, conf=args.conf, classes=[0], verbose=False)
                boxes = results[0].boxes

                if len(boxes) == 0:
                    # Tidak ada orang terdeteksi pada threshold ini
                    stats["no_person_detected"] += 1
                    continue

                # Ambil deteksi orang dengan confidence tertinggi
                best_box = None
                best_conf = -1.0
                for box in boxes:
                    c = float(box.conf[0])
                    if c > best_conf:
                        best_conf = c
                        best_box = box

                # Ekstrak koordinat normalisasi (x_center, y_center, width, height)
                xywhn = best_box.xywhn[0].cpu().numpy()
                x_center, y_center, width, height = xywhn

                # Tentukan nama file tujuan yang unik
                base_name = f"{seq_name}_f{frame_num:04d}"
                out_img_file = output_path / "images" / split / f"{base_name}.jpg"
                out_lbl_file = output_path / "labels" / split / f"{base_name}.txt"

                # Simpan gambar sebagai JPG (kualitas tinggi 95) untuk efisiensi ukuran
                cv2.imwrite(str(out_img_file), img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

                # Tulis file anotasi YOLO format: <class> <x> <y> <w> <h>
                with open(out_lbl_file, "w", encoding="utf-8") as f_lbl:
                    f_lbl.write(f"{yolo_class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

                # Update status
                last_saved_hash = curr_hash
                stats["saved_per_split"][split] += 1
                stats["saved_per_class"][class_str] += 1

    # 5. Tulis file data.yaml
    data_yaml_content = f"""# ============================================================
# Dataset YOLO11: UR Fall Detection
# Diproses secara otomatis via ml/scripts/prepare_urfall.py
# ============================================================

path: {output_path.as_posix()}
train: images/train
val: images/val
test: images/test

# Jumlah kelas
nc: 3

# Nama kelas (sesuai ground-truth UR Fall)
names:
  0: normal
  1: transitional
  2: lying_on_ground
"""
    yaml_file = output_path / "data.yaml"
    with open(yaml_file, "w", encoding="utf-8") as f_yaml:
        f_yaml.write(data_yaml_content)

    print("\n" + "=" * 65)
    print("🎉 PREPROCESSING SELESAI!")
    print("=" * 65)
    print(f"• Total frame diperiksa : {stats['total_extracted']}")
    print(f"• Frame dibuang (Dedup) : {stats['dropped_dedup']} (hemat resource & anti-overfit!)")
    print(f"• Frame tanpa deteksi   : {stats['no_person_detected']}")
    print("-" * 65)
    print("📊 Sebaran Data per Split:")
    for s in splits:
        count = stats["saved_per_split"][s]
        pct = (count / sum(stats["saved_per_split"].values()) * 100) if stats["saved_per_split"] else 0
        print(f"   - {s.upper():<5}: {count:5d} gambar ({pct:5.1f}%)")
    print("-" * 65)
    print("🏷️  Sebaran Data per Kelas Postur:")
    for c_name in CLASS_NAMES:
        c_count = stats["saved_per_class"][c_name]
        print(f"   - {c_name:<16}: {c_count:5d} gambar")
    print("-" * 65)
    print(f"✓ File konfigurasi tersimpan di: {yaml_file}")

    # 6. Kompres ke ZIP jika diminta
    if args.zip_output:
        zip_target = output_path.parent / "urfall_yolo_dataset.zip"
        print(f"\n📦 Mengompresi dataset ke: {zip_target}...")
        shutil.make_archive(str(zip_target.with_suffix("")), "zip", output_path)
        zip_size_mb = os.path.getsize(zip_target) / (1024 * 1024)
        print(f"✅ ZIP siap di-upload ke Kaggle / Hugging Face! (Ukuran: {zip_size_mb:.1f} MB)")
        print(f"   Path: {zip_target}")


if __name__ == "__main__":
    main()

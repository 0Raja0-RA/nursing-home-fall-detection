"""
prepare_dataset.py
=================
Preprocessing UR Fall Detection (cam0) -> format YOLO11.

1. Baca CSV ground truth (urfall-cam0-falls.csv & urfall-cam0-adls.csv).
2. Baca PNG RGB cam0 langsung dari ZIP (tanpa ekstrak ke disk).
3. Subsampling temporal PER KELAS (bukan pHash):
     normal       -> 1 dari tiap --normal-stride frame
     transitional -> semua frame dipertahankan
     lying        -> 1 dari tiap --lying-stride frame
4. Auto-annotation bbox 'person' memakai detektor COCO (--detector).
5. Split per video (fall 1-21/22-25/26-30, ADL 1-28/29-34/35-40).
6. Simpan images/ + labels/ + data.yaml + dataset_manifest.json.

Penggunaan:
    python prepare_urfall.py --raw-dir "D:/.../Dataset/raw" --output-dir "D:/.../Dataset/processed_urfall"
"""
import argparse
import csv
import json
import os
import re
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Optional

import cv2
import numpy as np

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc="", **kwargs):
        print(f"--> {desc}...")
        return iterable

# UR Fall: -1 = tidak berbaring, 0 = pose sementara, 1 = berbaring di lantai
UR_FALL_TO_YOLO = {-1: 0, 0: 1, 1: 2}
CLASS_NAMES = ["normal", "transitional", "lying_on_ground"]
EXPECTED_FALL_SEQS = 30
EXPECTED_ADL_SEQS = 40


def parse_csv_labels(csv_path: Path) -> Dict[str, Dict[int, int]]:
    """CSV -> { 'fall-01': { frame_number: label } }. Kolom: seq, frame, label, ..."""
    labels: Dict[str, Dict[int, int]] = {}
    if not csv_path.exists():
        print(f"[WARN] File CSV tidak ditemukan: {csv_path}")
        return labels
    with open(csv_path, mode="r", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            m = re.match(r"(fall|adl)-\d+", row[0].strip(), re.IGNORECASE)
            if not m:
                continue
            seq_name = m.group(0).lower()
            try:
                frame_num = int(row[1].strip())
                label_val = int(row[2].strip())
            except ValueError:
                continue
            labels.setdefault(seq_name, {})[frame_num] = label_val
    return labels


def determine_split(seq_name: str, is_fall: bool) -> str:
    """Split per nomor sequence video (mencegah kebocoran antar split)."""
    match = re.search(r"\d+", seq_name)
    num = int(match.group(0)) if match else 1
    if is_fall:
        return "train" if num <= 21 else ("val" if num <= 25 else "test")
    return "train" if num <= 28 else ("val" if num <= 34 else "test")


def extract_frame_number_from_filename(filename: str) -> Optional[int]:
    """'fall-01-cam0-rgb-015.png' -> 15"""
    match = re.search(r"-(\d+)\.png$", filename, re.IGNORECASE)
    return int(match.group(1)) if match else None


def keep_by_stride(seen: Counter, cls: int, stride: int) -> bool:
    """Ambil frame ke-0, ke-stride, ke-2*stride... per kelas, per video."""
    idx = seen[cls]
    seen[cls] += 1
    return idx % stride == 0


def main():
    parser = argparse.ArgumentParser(description="Preprocessing UR Fall (cam0) ke format YOLO11.")
    parser.add_argument("--raw-dir", type=str, required=True,
                        help=r"Folder raw, mis. D:\PENS\Semester 5\projek sistem cerdas\Dataset\raw")
    parser.add_argument("--output-dir", type=str, default="D:\PENS\Semester 5\projek sistem cerdas\nursing-home-fall-detection\ml\data\processed_urfall")
    parser.add_argument("--normal-stride", type=int, default=5,
                        help="Ambil 1 dari tiap N frame normal (default 5).")
    parser.add_argument("--lying-stride", type=int, default=3,
                        help="Ambil 1 dari tiap N frame lying (default 3).")
    parser.add_argument("--detector", type=str, default="yolo11n.pt",
                        help="Bobot detektor COCO untuk auto-bbox (mis. yolo11m.pt).")
    parser.add_argument("--conf", type=float, default=0.25,
                        help="Confidence detektor untuk frame normal.")
    parser.add_argument("--conf-hard", type=float, default=0.15,
                        help="Confidence lebih rendah untuk frame transitional/lying.")
    parser.add_argument("--zip-output", action="store_true")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Izinkan jumlah zip != 30 fall / 40 ADL (hanya untuk uji coba kecil).")
    args = parser.parse_args()

    if args.normal_stride < 1 or args.lying_stride < 1:
        sys.exit("[FATAL] stride harus >= 1")
    strides = {0: args.normal_stride, 1: 1, 2: args.lying_stride}

    raw = Path(args.raw_dir).resolve()
    output_path = Path(args.output_dir).resolve()

    print("=" * 65)
    print("MEMULAI PREPROCESSING UR FALL -> YOLO11")
    print("=" * 65)
    print(f"• Raw Path     : {raw}")
    print(f"• Output Path  : {output_path}")
    print(f"• Stride       : normal={args.normal_stride}, transitional=1, lying={args.lying_stride}")
    print(f"• Detektor     : {args.detector} (conf={args.conf}, conf-hard={args.conf_hard})")
    print("=" * 65)

    # --- Pengaman sebelum menghapus apa pun ---
    if output_path == raw or output_path in raw.parents:
        sys.exit(f"[FATAL] --output-dir ({output_path}) tidak boleh sama dengan atau induk dari --raw-dir.")

    # --- Detektor ---
    try:
        from ultralytics import YOLO
        print(f"Memuat detektor {args.detector} ...")
        detector = YOLO(args.detector)
    except ImportError:
        sys.exit("[ERROR] Library 'ultralytics' belum terinstall: pip install ultralytics opencv-python numpy")

    # --- CSV + zip ---
    falls_csv = raw / "csv" / "features" / "urfall-cam0-falls.csv"
    adls_csv = raw / "csv" / "features" / "urfall-cam0-adls.csv"
    zip_dir = raw / "rgb_zip"
    if not zip_dir.is_dir():
        sys.exit(f"[FATAL] Folder zip tidak ada: {zip_dir}")
    fall_zips = sorted(zip_dir.glob("fall-*-cam0-rgb.zip"))
    adl_zips = sorted(zip_dir.glob("adl-*-cam0-rgb.zip"))

    fall_labels = parse_csv_labels(falls_csv)
    adl_labels = parse_csv_labels(adls_csv)
    print(f"CSV dimuat: {len(fall_labels)} fall seq, {len(adl_labels)} ADL seq")
    if not fall_labels or not adl_labels:
        sys.exit(f"[FATAL] CSV kosong: {falls_csv} | {adls_csv}")
    print("   contoh key CSV:", list(fall_labels)[:3], list(adl_labels)[:3])

    print(f"Zip ditemukan: {len(fall_zips)} fall, {len(adl_zips)} ADL")
    if not args.allow_partial and (len(fall_zips) != EXPECTED_FALL_SEQS or len(adl_zips) != EXPECTED_ADL_SEQS):
        sys.exit(f"[FATAL] Diharapkan {EXPECTED_FALL_SEQS} fall + {EXPECTED_ADL_SEQS} ADL zip di {zip_dir}.")
    if not fall_zips and not adl_zips:
        sys.exit("[FATAL] Tidak ada zip yang diproses.")

    for z in fall_zips:
        s = z.stem.replace("-cam0-rgb", "")
        if s not in fall_labels:
            sys.exit(f"[FATAL] {s} tidak ada di CSV fall. Key contoh: {list(fall_labels)[:3]}")
    for z in adl_zips:
        s = z.stem.replace("-cam0-rgb", "")
        if s not in adl_labels:
            sys.exit(f"[FATAL] {s} tidak ada di CSV ADL. Key contoh: {list(adl_labels)[:3]}")

    # --- Siapkan output (bersihkan hanya jika itu hasil run sebelumnya) ---
    if output_path.exists():
        ours = (output_path / "data.yaml").exists() or (output_path / "images").exists()
        if any(output_path.iterdir()) and not ours:
            sys.exit(f"[FATAL] {output_path} tidak kosong dan bukan hasil run sebelumnya. Hapus/ganti manual.")
        shutil.rmtree(output_path)

    splits = ["train", "val", "test"]
    for s in splits:
        (output_path / "images" / s).mkdir(parents=True, exist_ok=True)
        (output_path / "labels" / s).mkdir(parents=True, exist_ok=True)

    stats = {
        "frames_seen": 0,
        "skipped_no_label": 0,
        "skipped_unknown_label": 0,
        "skipped_unreadable": 0,
        "dropped_stride": Counter(),
        "no_person": Counter(),
        "saved": Counter(),          # kunci: (split, kelas)
    }
    seqs = defaultdict(set)          # (split, kelas) -> set nama video

    all_tasks = [(z, True) for z in fall_zips] + [(z, False) for z in adl_zips]
    print("\nMemproses frame dari ZIP (stride per kelas + auto-bbox)...")

    for zip_path, is_fall in tqdm(all_tasks, desc="Memproses video sequence"):
        seq_name = zip_path.stem.replace("-cam0-rgb", "")
        split = determine_split(seq_name, is_fall)
        label_lookup = fall_labels[seq_name] if is_fall else adl_labels[seq_name]
        seen = Counter()  # penghitung stride per kelas, di-reset per video

        with zipfile.ZipFile(zip_path, "r") as z:
            png_names = sorted(n for n in z.namelist() if n.lower().endswith(".png"))
            for img_name in png_names:
                stats["frames_seen"] += 1
                frame_num = extract_frame_number_from_filename(img_name)
                if frame_num is None:
                    stats["skipped_unreadable"] += 1
                    continue

                # Fall: frame tanpa label dilewati. ADL: default normal (-1).
                raw_label = label_lookup.get(frame_num, None if is_fall else -1)
                if raw_label is None:
                    stats["skipped_no_label"] += 1
                    continue
                cls = UR_FALL_TO_YOLO.get(raw_label)
                if cls is None:
                    stats["skipped_unknown_label"] += 1
                    continue
                class_str = CLASS_NAMES[cls]

                # Subsampling temporal per kelas (sebelum decode, hemat waktu)
                if not keep_by_stride(seen, cls, strides[cls]):
                    stats["dropped_stride"][class_str] += 1
                    continue

                img_bgr = cv2.imdecode(np.frombuffer(z.read(img_name), dtype=np.uint8), cv2.IMREAD_COLOR)
                if img_bgr is None:
                    stats["skipped_unreadable"] += 1
                    continue

                # Auto-annotation: conf lebih rendah untuk kelas yang pasti ada orangnya & sulit dideteksi
                conf = args.conf if cls == 0 else args.conf_hard
                boxes = detector(img_bgr, conf=conf, classes=[0], verbose=False)[0].boxes
                if len(boxes) == 0:
                    stats["no_person"][class_str] += 1
                    continue
                best = max(boxes, key=lambda b: float(b.conf[0]))
                x_c, y_c, w, h = best.xywhn[0].cpu().numpy()

                base_name = f"urfall_{seq_name}_f{frame_num:04d}"
                cv2.imwrite(str(output_path / "images" / split / f"{base_name}.jpg"),
                            img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                with open(output_path / "labels" / split / f"{base_name}.txt", "w", encoding="utf-8") as f_lbl:
                    f_lbl.write(f"{cls} {x_c:.6f} {y_c:.6f} {w:.6f} {h:.6f}\n")

                stats["saved"][(split, class_str)] += 1
                seqs[(split, class_str)].add(seq_name)

    # --- data.yaml (tanpa 'path': Ultralytics memakai folder tempat file ini berada) ---
    yaml_file = output_path / "data.yaml"
    yaml_file.write_text(
        "# Dataset YOLO11: UR Fall (cam0). Dibuat oleh ml/scripts/prepare_urfall.py\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "nc: 3\n"
        "names:\n"
        "  0: normal\n"
        "  1: transitional\n"
        "  2: lying_on_ground\n",
        encoding="utf-8",
    )

    # --- Ringkasan & manifest ---
    totals = Counter()
    for (s, c), n in stats["saved"].items():
        totals[c] += n

    manifest = {
        "source": "urfall-cam0",
        "params": vars(args),
        "frames_seen": stats["frames_seen"],
        "skipped": {
            "no_label": stats["skipped_no_label"],
            "unknown_label": stats["skipped_unknown_label"],
            "unreadable": stats["skipped_unreadable"],
        },
        "dropped_by_stride": dict(stats["dropped_stride"]),
        "no_person_by_class": dict(stats["no_person"]),
        "counts": {
            s: {c: {"frames": stats["saved"][(s, c)], "videos": len(seqs[(s, c)])} for c in CLASS_NAMES}
            for s in splits
        },
        "totals": dict(totals),
    }
    (output_path / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 65)
    print("PREPROCESSING SELESAI")
    print("=" * 65)
    print(f"• Frame diperiksa        : {stats['frames_seen']}")
    print(f"• Dilewati (tanpa label) : {stats['skipped_no_label']}  | label tak dikenal: {stats['skipped_unknown_label']}"
          f"  | tak terbaca: {stats['skipped_unreadable']}")
    print(f"• Dibuang oleh stride    : {dict(stats['dropped_stride'])}")
    print(f"• Dibuang (tanpa orang)  : {dict(stats['no_person'])}")
    print("-" * 65)
    print("Frame tersimpan per split x kelas  (jumlah frame / jumlah video):")
    print(f"{'split':<7}" + "".join(f"{c:>20}" for c in CLASS_NAMES))
    for s in splits:
        print(f"{s:<7}" + "".join(
            f"{str(stats['saved'][(s, c)]) + ' / ' + str(len(seqs[(s, c)])):>20}" for c in CLASS_NAMES))
    print("-" * 65)
    print(f"Total per kelas: { {c: totals[c] for c in CLASS_NAMES} }")
    print(f"Konfigurasi: {yaml_file}")
    print(f"Manifest   : {output_path / 'dataset_manifest.json'}")

    # --- Pemeriksaan sebelum zip ---
    empty = [c for c in CLASS_NAMES if totals[c] == 0]
    if empty:
        sys.exit(f"[FATAL] Kelas kosong: {empty}. Cek CSV, indeks frame, atau detektor (lihat 'tanpa orang').")

    for s in ("val", "test"):
        for c in ("transitional", "lying_on_ground"):
            n, v = stats["saved"][(s, c)], len(seqs[(s, c)])
            if n < 30 or v < 3:
                print(f"[WARN] {s}/{c}: {n} frame dari {v} video. Evaluasi kelas ini rapuh (data gate: >=30 frame DAN >=3 video).")
    if totals["normal"] < totals["lying_on_ground"]:
        print("[WARN] Frame normal lebih sedikit dari lying. Pertimbangkan --normal-stride lebih kecil.")

    if args.zip_output:
        zip_target = output_path.parent / "urfall_yolo_dataset.zip"
        print(f"\nMengompresi ke: {zip_target} ...")
        shutil.make_archive(str(zip_target.with_suffix("")), "zip", output_path)
        print(f"ZIP siap upload ke Kaggle ({os.path.getsize(zip_target) / (1024 * 1024):.1f} MB): {zip_target}")


if __name__ == "__main__":
    main()
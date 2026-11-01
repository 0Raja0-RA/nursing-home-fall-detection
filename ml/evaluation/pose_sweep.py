"""
pose_sweep.py
=============
Mengukur kualitas keluaran pose SEBELUM klasifikasi postur, pada gambar penuh atau potongan orang.

Metrik di ml/common/pose.py:score_frame adalah proxy terhadap bbox label (dataset tidak punya label
keypoint), jadi keakuratan titik tetap perlu dicek lewat grid. Mode crop memakai bbox label sebagai
pengganti detektor sempurna (oracle crop): hasilnya BATAS ATAS dan waktunya belum termasuk detektor.

Skrip berhenti jika GPU tidak tersedia (kecuali --allow-cpu).

Keluaran di --out:
  summary.csv                       : metrik per konfigurasi (per kelas dan per kamera lying)
  frames.csv                        : hasil per frame per konfigurasi
  grid_crop_menang / full_menang / sama_gagal .png : pembanding REFERENCE vs --grid-crop

Contoh (dari akar repo, dengan .venv aktif):
  python -m ml.evaluation.pose_sweep --split val --out ml/outputs/oracle_crop
  python -m ml.evaluation.pose_sweep --split val --configs full:yolo11n-pose.pt:640:0.25:0:0 full:yolo11m-pose.pt:1280:0.25:0:0

Format config: full|crop:model:imgsz:conf:rotasi:margin (rotasi 1 = coba juga gambar diputar 90 derajat)
"""

import argparse
import collections
import csv
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from ml.common.labels import CLASS_NAMES, camera_of, read_box, sample_frames
from ml.common.pose import predict, score_frame
from ml.common.viz import crop_window, header, render

DEFAULT_CONFIGS = [
    "full:yolo11n-pose.pt:640:0.25:0:0",
    "full:yolo11n-pose.pt:640:0.25:1:0",
    "full:yolo11m-pose.pt:640:0.25:0:0",
    "full:yolo11m-pose.pt:640:0.25:1:0",  # pembanding utama
    "crop:yolo11n-pose.pt:320:0.25:0:0.2",
    "crop:yolo11n-pose.pt:640:0.25:0:0.2",
    "crop:yolo11n-pose.pt:640:0.25:1:0.2",
    "crop:yolo11m-pose.pt:320:0.25:0:0.2",
    "crop:yolo11m-pose.pt:640:0.25:0:0.1",
    "crop:yolo11m-pose.pt:640:0.25:0:0.2",
    "crop:yolo11m-pose.pt:640:0.25:0:0.4",
    "crop:yolo11m-pose.pt:640:0.25:1:0.2",
]
REFERENCE = "full:yolo11m-pose.pt:640:0.25:1:0"


def select_device(allow_cpu: bool):
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}", flush=True)
        return 0
    if allow_cpu:
        print("PERINGATAN: berjalan di CPU, angka waktu tidak bisa dipakai.", flush=True)
        return "cpu"
    sys.exit(f"CUDA tidak tersedia pada {sys.executable}. Aktifkan .venv lalu jalankan ulang.")


def parse_config(text: str) -> dict:
    mode, name, imgsz, conf, rotate, margin = text.split(":")
    return {"text": text, "mode": mode, "model": name, "imgsz": int(imgsz), "conf": float(conf),
            "rotate": rotate == "1", "margin": float(margin)}


def run_config(model, img, box, cfg, device):
    """-> deteksi dalam koordinat gambar penuh, dipotong ke sekitar box jika mode crop."""
    if cfg["mode"] == "full":
        return predict(model, img, cfg["imgsz"], cfg["conf"], cfg["rotate"], device)

    h, w = img.shape[:2]
    bw, bh = box[2] - box[0], box[3] - box[1]
    m = cfg["margin"] * max(bw, bh)
    x1, y1 = int(max(0, box[0] - m)), int(max(0, box[1] - m))
    x2, y2 = int(min(w, box[2] + m)), int(min(h, box[3] + m))
    dets = predict(model, img[y1:y2, x1:x2], cfg["imgsz"], cfg["conf"], cfg["rotate"], device)

    shifted = []
    for c, b, k in dets:
        k2 = k.copy()
        k2[:, 0] += x1
        k2[:, 1] += y1
        shifted.append((c, b + np.array([x1, y1, x1, y1]), k2))
    return shifted


def good(score: dict) -> bool:
    return score["top1"] and score["core"]


def short_label(text: str) -> str:
    cfg = parse_config(text)
    return f"{cfg['mode']} {cfg['model'][6]} {cfg['imgsz']}" + (" +rot" if cfg["rotate"] else "")


def write_grid(path: Path, files: list[Path], results: dict, grid_configs: list[str], lbl_dir: Path, limit: int):
    rows = []
    step = max(1, len(files) // limit)
    for f in files[::step][:limit]:
        img = cv2.imread(str(f))
        h, w = img.shape[:2]
        cls, box = read_box(lbl_dir / f"{f.stem}.txt", w, h)
        window = crop_window(box, w, h)
        panels = [render(img, window, *results[t][f], short_label(t)) for t in grid_configs]
        body = np.hstack(panels)
        rows.append(np.vstack([header(f"{f.stem}   GT: {CLASS_NAMES[cls]}", body.shape[1]), body]))
    if rows:
        cv2.imwrite(str(path), np.vstack(rows))
    print(f"{path.name}: {len(files)} frame, ditampilkan {len(rows)}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Sweep kualitas pose: gambar penuh vs oracle crop")
    ap.add_argument("--data-dir", default="ml/data/processed_final")
    ap.add_argument("--split", default="val", help="Pilih konfigurasi di val; test hanya untuk konfirmasi akhir")
    ap.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS)
    ap.add_argument("--grid-crop", default="crop:yolo11m-pose.pt:320:0.25:0:0.2", help="Konfigurasi crop lawan REFERENCE di grid")
    ap.add_argument("--per-class", type=int, default=150, help="Maks frame normal/transitional (lying dipakai semua)")
    ap.add_argument("--limit", type=int, default=0, help="Hanya N frame, untuk uji cepat")
    ap.add_argument("--grid-rows", type=int, default=12)
    ap.add_argument("--allow-cpu", action="store_true")
    ap.add_argument("--out", default="ml/outputs/pose_sweep")
    args = ap.parse_args()

    device = select_device(args.allow_cpu)
    img_dir = Path(args.data_dir) / "images" / args.split
    lbl_dir = Path(args.data_dir) / "labels" / args.split
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    samples, n_lying = sample_frames(img_dir, lbl_dir, args.per_class)
    if args.limit:
        samples = samples[:: max(1, len(samples) // args.limit)][: args.limit]
    print(f"Sampel {args.split}: {len(samples)} (lying di split {n_lying})", flush=True)

    models, results, summary, frame_rows = {}, {}, [], []
    for text in args.configs:
        cfg = parse_config(text)
        model = models.setdefault(cfg["model"], YOLO(cfg["model"]))
        tally = collections.defaultdict(collections.Counter)
        results[text] = {}
        elapsed, timed = 0.0, 0

        for n, f in enumerate(samples):
            img = cv2.imread(str(f))
            h, w = img.shape[:2]
            cls, box = read_box(lbl_dir / f"{f.stem}.txt", w, h)
            t0 = time.perf_counter()
            dets = run_config(model, img, box, cfg, device)
            if n > 0:  # frame pertama memuat model ke GPU, tidak dihitung
                elapsed += time.perf_counter() - t0
                timed += 1
            score = score_frame(dets, box)
            results[text][f] = (dets, score)

            n_kpts = 0
            if score["top1"]:
                top = max(dets, key=lambda d: d[0])
                n_kpts = int((top[2][:, 2] > 0.25).sum())
            for key in (f"cls{cls}", f"lying_{camera_of(f.name)}" if cls == 2 else None):
                if key:
                    tally[key].update(n=1, found=int(score["found"]), top1=int(score["top1"]),
                                      core=int(good(score)), kpts=n_kpts, extra=score["extra"])
            frame_rows.append({"config": text, "img": f.name, "gt": cls, "camera": camera_of(f.name),
                               "found": int(score["found"]), "top1": int(score["top1"]),
                               "core": int(good(score)), "n_kpts": n_kpts, "extra": score["extra"]})

        used = str(model.predictor.device)
        if device == 0 and "cuda" not in used:
            sys.exit(f"Model berjalan di {used}, bukan GPU. Hentikan run ini.")
        ms = elapsed / max(1, timed) * 1000
        row = {"config": text, "ms_per_frame": round(ms, 1)}
        for key, t in sorted(tally.items()):
            row[f"{key}_n"] = t["n"]
            for metric in ("found", "top1", "core"):
                row[f"{key}_{metric}"] = round(t[metric] / t["n"], 3)
            row[f"{key}_kpts"] = round(t["kpts"] / t["n"], 1)
            row[f"{key}_extra"] = round(t["extra"] / t["n"], 3)
        summary.append(row)

        parts = [f"{CLASS_NAMES[c][:5]} core={row[f'cls{c}_core']:.3f} kpts={row[f'cls{c}_kpts']:.1f}"
                 for c in (2, 1, 0) if f"cls{c}_core" in row]
        print(f"{text:<40} {used:<7} {ms:7.1f} ms | " + " | ".join(parts), flush=True)

    fields = sorted({k for r in summary for k in r}, key=lambda k: (k not in ("config", "ms_per_frame"), k))
    with open(out / "summary.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    with open(out / "frames.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(frame_rows[0]))
        writer.writeheader()
        writer.writerows(frame_rows)

    if REFERENCE in results and args.grid_crop in results:
        grid_configs = [REFERENCE, args.grid_crop]
        groups = {"grid_crop_menang": [], "grid_full_menang": [], "grid_sama_gagal": []}
        for f in samples:
            full_ok, crop_ok = good(results[REFERENCE][f][1]), good(results[args.grid_crop][f][1])
            if crop_ok and not full_ok:
                groups["grid_crop_menang"].append(f)
            elif full_ok and not crop_ok:
                groups["grid_full_menang"].append(f)
            elif not full_ok and not crop_ok:
                groups["grid_sama_gagal"].append(f)
        for name, files in groups.items():
            write_grid(out / f"{name}.png", files, results, grid_configs, lbl_dir, args.grid_rows)
    print(f"Tersimpan di: {out.resolve()}")


if __name__ == "__main__":
    main()

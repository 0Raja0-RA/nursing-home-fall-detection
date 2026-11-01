"""Tahap 1 (GPU, sekali per model): ekstrak fitur pose untuk SEMUA frame Data Baru (train + val + test).

Inferensi memakai ambang confidence terendah (0,05) dan menyimpan hanya fitur mentah (termasuk 17 keypoint: x/lebar, y/tinggi, conf). Semua pilihan ambang dan aturan
dilakukan di Tahap 2 (pose_grouped_cv.py, CPU), sehingga satu kali ekstraksi cukup untuk seluruh eksperimen aturan.

Contoh:
  python ml/archive/scripts/pose_extract_features.py --weights yolo11n-pose.pt --imgsz 640
  python ml/archive/scripts/pose_extract_features.py --weights yolo11m-pose.pt --imgsz 1280 --batch 2
  python ml/archive/scripts/pose_extract_features.py --weights yolo11n-pose.pt --imgsz 640 --limit 20 --device cpu   # uji cepat
"""
import argparse
import csv
import math
import re
from pathlib import Path

from tqdm.auto import tqdm
from ultralytics import YOLO

DATA = Path(r"C:\Project_2026\Falling Detection\ml\data\processed_final")
OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_classifier_cv"
OUT.mkdir(exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--weights", default="yolo11n-pose.pt")
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--conf", type=float, default=0.05, help="ambang terendah yang disimpan")
ap.add_argument("--batch", type=int, default=8)
ap.add_argument("--device", default=None)
ap.add_argument("--limit", type=int, default=0, help="uji cepat: hanya N gambar pertama per split")
ap.add_argument("--data-dir", default=str(DATA))
ap.add_argument("--out", default=None)
a = ap.parse_args()

data = Path(a.data_dir)
tag = f"{Path(a.weights).stem}_{a.imgsz}"
dst = Path(a.out) if a.out else OUT / f"pose_features_{tag}.csv"


def video_of(stem):                       # sama dengan ml/evaluation/eval_lying.py
    m = re.match(r"mcf_s(\d+)_c\d_f\d+$", stem)
    if m:
        return f"mcf-s{m.group(1)}"
    m = re.match(r"urfall_((?:fall|adl)-\d+)_f\d+$", stem)
    return f"urfall-{m.group(1)}" if m else stem


def camera_of(stem):
    m = re.match(r"mcf_s\d+_(c\d)_", stem)
    return m.group(1) if m else "cam0"


model = YOLO(a.weights)
items = []
for sp in ("train", "val", "test"):
    ims = sorted((data / "images" / sp).glob("*.jpg"))
    items += [(sp, p) for p in (ims[:a.limit] if a.limit else ims)]
print(f"{len(items)} gambar | model {a.weights} @{a.imgsz} | conf {a.conf} -> {dst}")

kw = dict(imgsz=a.imgsz, conf=a.conf, verbose=False)
if a.device:
    kw["device"] = a.device
rows = []
bar = tqdm(total=len(items), desc=f"{tag}", unit="img", dynamic_ncols=True)
for i in range(0, len(items), a.batch):
    ch = items[i:i + a.batch]
    for (sp, p), r in zip(ch, model([str(x[1]) for x in ch], **kw)):
        gt = int((data / "labels" / sp / (p.stem + ".txt")).read_text().split()[0])
        row = dict(split=sp, img=p.name, video=video_of(p.stem), source="mcf" if p.name.startswith("mcf_") else "urfall",
                   camera=camera_of(p.stem), gt=gt, top_conf=0.0, n_boxes=0, joints_ok=0, angle=float("nan"),
                   ar=0.5, box_h=0.0, box_w=0.0,
                   **{f"k{j}{c}": float("nan") for j in range(17) for c in ("x", "y", "c")})
        if len(r.boxes):
            b = int(r.boxes.conf.argmax())
            H, W = r.orig_shape
            x1, y1, x2, y2 = r.boxes.xyxy[b].tolist()
            row.update(top_conf=round(float(r.boxes.conf[b]), 4), n_boxes=len(r.boxes),
                       ar=round(max(1.0, x2 - x1) / max(1.0, y2 - y1), 4),
                       box_h=round((y2 - y1) / H, 4), box_w=round((x2 - x1) / W, 4))
            k = r.keypoints.data[b].cpu().numpy()
            for j in range(17):
                row[f"k{j}x"], row[f"k{j}y"], row[f"k{j}c"] = round(float(k[j][0]) / W, 4), round(float(k[j][1]) / H, 4), round(float(k[j][2]), 3)
            if (k[5][2] + k[6][2]) / 2 > 0.25 and (k[11][2] + k[12][2]) / 2 > 0.25:
                sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
                hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
                row.update(joints_ok=1, angle=round(math.degrees(math.atan2(abs(sy - hy), abs(sx - hx))), 3))
        rows.append(row)
    bar.update(len(ch))
bar.close()

with open(dst, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("tersimpan:", dst, f"({len(rows)} baris)")

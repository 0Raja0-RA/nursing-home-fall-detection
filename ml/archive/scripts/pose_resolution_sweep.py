"""Apakah kegagalan deteksi pose pada frame lying MCF berkurang dengan resolusi/model lebih besar?

Frame uji: semua gambar lying (264) di test Data Baru. Metrik: persentase gambar yang punya >=1 orang
terdeteksi, dan yang punya bahu+pinggul terbaca (sendi cukup untuk menghitung sudut).
"""
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from ultralytics import YOLO

ROOT = Path(r"C:\Project_2026\Falling Detection")
NEW = ROOT / "ml" / "data" / "processed_final"
OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_resolution"

imgs = []
for l in sorted((NEW / "labels" / "test").glob("*.txt")):
    t = l.read_text().split()
    if t and t[0] == "2":
        imgs.append(NEW / "images" / "test" / (l.stem + ".jpg"))
print("frame lying test:", len(imgs))


def cam_of(p):
    m = re.match(r"mcf_s\d+_(c\d+)_", p.name)
    return m.group(1) if m else "cam0"


def run(weights, imgsz, conf=0.25):
    model = YOLO(weights)
    det = joint = 0
    percam = defaultdict(lambda: [0, 0])
    angles = []
    for i in range(0, len(imgs), 16):
        chunk = imgs[i:i + 16]
        for p, r in zip(chunk, model([str(x) for x in chunk], imgsz=imgsz, conf=conf, verbose=False)):
            c = cam_of(p)
            percam[c][0] += 1
            if len(r.boxes) == 0:
                continue
            det += 1
            percam[c][1] += 1
            b = int(r.boxes.conf.argmax())
            k = r.keypoints.data[b].cpu().numpy()
            if (k[5][2] + k[6][2]) / 2 > 0.25 and (k[11][2] + k[12][2]) / 2 > 0.25:
                joint += 1
                sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
                hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
                angles.append(math.degrees(math.atan2(abs(sy - hy), abs(sx - hx))))
    a = np.array(angles) if angles else np.array([90.0])
    return det, joint, (a < 40).sum(), dict(percam)


rows = []
for weights in ("yolo11n-pose.pt", "yolo11m-pose.pt"):
    for imgsz in (640, 960, 1280):
        try:
            det, joint, low, percam = run(weights, imgsz)
        except Exception as e:  # unduhan bobot gagal, dsb.
            print(weights, imgsz, "GAGAL:", str(e)[:120])
            continue
        n = len(imgs)
        print(f"{weights:18s} imgsz={imgsz:4d} | orang terdeteksi {det:3d}/{n} ({det/n:.0%}) | sendi bahu+pinggul terbaca {joint:3d} ({joint/n:.0%}) | sudut<40: {low} ({low/n:.0%})")
        print("    per kamera terdeteksi:", {c: f"{v[1]}/{v[0]}" for c, v in sorted(percam.items())})
        rows.append((weights, imgsz, det, joint, int(low), n))

import csv
with open(OUT / "pose_resolution_sweep.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["weights", "imgsz", "terdeteksi", "sendi_terbaca", "sudut_lt40", "n"])
    w.writerows(rows)

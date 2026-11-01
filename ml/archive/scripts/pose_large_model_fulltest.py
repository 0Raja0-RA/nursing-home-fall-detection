"""yolo11m-pose @1280 vs yolo11n-pose @640 pada SELURUH test Data Baru (3.401 gambar).
Mengukur recall/precision lying (aturan sudut sama seperti EXP-009) dan latensi per gambar.
"""
import csv
import math
import re
import time
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm
from ultralytics import YOLO

NEW = Path(r"C:\Project_2026\Falling Detection\ml\data\processed_final")
OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_resolution"
imgs = sorted((NEW / "images" / "test").glob("*.jpg"))
gt = {p.name: int((NEW / "labels" / "test" / (p.stem + ".txt")).read_text().split()[0]) for p in imgs}


def feats(weights, imgsz):
    model = YOLO(weights)
    model([str(imgs[0])], imgsz=imgsz, verbose=False)           # pemanasan
    rows, t0 = [], time.time()
    bar = tqdm(total=len(imgs), desc=f"{weights} @{imgsz}", unit="img", dynamic_ncols=True)
    for i in range(0, len(imgs), 4):
        ch = imgs[i:i + 4]
        bar.update(len(ch))
        for p, r in zip(ch, model([str(x) for x in ch], imgsz=imgsz, conf=0.25, verbose=False)):
            row = dict(img=p.name, gt=gt[p.name], detected=0, angle=90.0, ar=0.5)
            if len(r.boxes):
                b = int(r.boxes.conf.argmax())
                x1, y1, x2, y2 = r.boxes.xyxy[b].tolist()
                ar = max(1.0, x2 - x1) / max(1.0, y2 - y1)
                k = r.keypoints.data[b].cpu().numpy()
                if (k[5][2] + k[6][2]) / 2 > 0.25 and (k[11][2] + k[12][2]) / 2 > 0.25:
                    sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
                    hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
                    ang = math.degrees(math.atan2(abs(sy - hy), abs(sx - hx)))
                else:
                    ang = 90.0 if ar < 0.8 else (20.0 if ar > 1.3 else 50.0)
                row.update(detected=1, angle=ang, ar=ar)
            rows.append(row)
    bar.close()
    return rows, (time.time() - t0) / len(imgs) * 1000


def lying(rows, fa, r):
    return np.array([(x["angle"] < fa) or (x["ar"] > r and x["angle"] < fa + 12) for x in rows])


y = np.array([x == 2 for x in gt.values()])
for name, w, s in (("n-pose@640", "yolo11n-pose.pt", 640), ("m-pose@1280", "yolo11m-pose.pt", 1280)):
    rows, ms = feats(w, s)
    with open(OUT / f"pose_large_model_{name.replace('@', '_').replace('-', '_')}_features.csv", "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    det = np.mean([r["detected"] for r in rows if r["gt"] == 2])
    print(f"\n== {name} | {ms:.0f} ms/gambar (termasuk baca disk) | lying terdeteksi {det:.0%}")
    for fa, r in ((20, 1.15), (40, 1.25)):
        p = lying(rows, fa, r)
        tp, fp = (p & y).sum(), (p & ~y).sum()
        src = np.array([x["img"].startswith("mcf_") for x in rows])
        print(f"   aturan {fa}/{r}: lying R={tp/y.sum():.1%} P={tp/max(1, tp+fp):.1%}  TP={tp} FP={fp} | "
              f"R urfall={((p&y&~src).sum()/max(1,(y&~src).sum())):.0%} R mcf={((p&y&src).sum()/max(1,(y&src).sum())):.0%}")

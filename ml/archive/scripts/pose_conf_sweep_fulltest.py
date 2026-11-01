"""Pose pada SELURUH test Data Baru dengan sapuan ambang confidence: recall DAN alarm palsu lying.

Inferensi dijalankan sekali pada ambang terendah (0,05); tiap ambang di --conf kemudian disaring dari hasil yang sama.
Aturan sudut sama dengan EXP-009: lying jika sudut < fall_angle, atau (AR > ar dan sudut < fall_angle + 12).
Gambar tanpa deteksi (conf teratas < ambang) dianggap sudut 90 (normal), seperti EXP-009.

Contoh:
  python ml/archive/scripts/pose_conf_sweep_fulltest.py
  python ml/archive/scripts/pose_conf_sweep_fulltest.py --weights yolo11n-pose.pt yolo26n-pose.pt --imgsz 640
"""
import argparse
import csv
import math
from pathlib import Path

import numpy as np
from tqdm.auto import tqdm
from ultralytics import YOLO

NEW = Path(r"C:\Project_2026\Falling Detection\ml\data\processed_final")
OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_conf_sweep"
OUT.mkdir(exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--weights", nargs="*", default=["yolo11n-pose.pt", "yolo26n-pose.pt", "yolo26m-pose.pt"])
ap.add_argument("--imgsz", type=int, default=640)
ap.add_argument("--conf", nargs="*", type=float, default=[0.25, 0.10, 0.05])
ap.add_argument("--batch", type=int, default=8)
a = ap.parse_args()
confs = sorted(set(a.conf), reverse=True)

imgs = sorted((NEW / "images" / "test").glob("*.jpg"))
gt = np.array([int((NEW / "labels" / "test" / (p.stem + ".txt")).read_text().split()[0]) for p in imgs])
is_mcf = np.array([p.name.startswith("mcf_") for p in imgs])
y = gt == 2
print(f"test: {len(imgs)} gambar | lying: {y.sum()} | ambang: {confs} | imgsz {a.imgsz}")

rules = {"20/1.15 (lama)": (20.0, 1.15), "40/1.25 (grid data baru)": (40.0, 1.25)}
rows = []
for w in a.weights:
    model = YOLO(w)
    model([str(imgs[0])], imgsz=a.imgsz, verbose=False)
    top_conf = np.zeros(len(imgs)); ang_ok = np.full(len(imgs), 90.0); ar = np.full(len(imgs), 0.5)
    bar = tqdm(total=len(imgs), desc=f"{w} @{a.imgsz}", unit="img", dynamic_ncols=True)
    for i in range(0, len(imgs), a.batch):
        ch = imgs[i:i + a.batch]
        for j, r in enumerate(model([str(x) for x in ch], imgsz=a.imgsz, conf=min(confs), verbose=False)):
            k = i + j
            if len(r.boxes) == 0:
                continue
            b = int(r.boxes.conf.argmax())
            top_conf[k] = float(r.boxes.conf[b])
            x1, y1, x2, y2 = r.boxes.xyxy[b].tolist()
            ar[k] = max(1.0, x2 - x1) / max(1.0, y2 - y1)
            kp = r.keypoints.data[b].cpu().numpy()
            if (kp[5][2] + kp[6][2]) / 2 > 0.25 and (kp[11][2] + kp[12][2]) / 2 > 0.25:
                sx, sy = (kp[5][0] + kp[6][0]) / 2, (kp[5][1] + kp[6][1]) / 2
                hx, hy = (kp[11][0] + kp[12][0]) / 2, (kp[11][1] + kp[12][1]) / 2
                ang_ok[k] = math.degrees(math.atan2(abs(sy - hy), abs(sx - hx)))
            else:
                ang_ok[k] = 90.0 if ar[k] < 0.8 else (20.0 if ar[k] > 1.3 else 50.0)
        bar.update(len(ch))
    bar.close()
    np.savez(OUT / f"pose_conf_sweep_{w.replace('.pt', '')}_{a.imgsz}.npz", top_conf=top_conf, angle=ang_ok, ar=ar, gt=gt, mcf=is_mcf)
    for c in confs:
        det = top_conf >= c
        angle = np.where(det, ang_ok, 90.0)
        arr = np.where(det, ar, 0.5)
        for rn, (fa, r_) in rules.items():
            p = (angle < fa) | ((arr > r_) & (angle < fa + 12))
            tp, fp = int((p & y).sum()), int((p & ~y).sum())
            rec = tp / y.sum(); prec = tp / max(1, tp + fp)
            rec_m = (p & y & is_mcf).sum() / max(1, (y & is_mcf).sum())
            rec_u = (p & y & ~is_mcf).sum() / max(1, (y & ~is_mcf).sum())
            rows.append([w, a.imgsz, c, rn, round(det[y].mean(), 3), round(rec, 3), round(prec, 3), tp, fp, round(rec_u, 3), round(rec_m, 3)])
            tqdm.write(f"{w:16s} conf={c:<4} aturan {rn:24s} | lying terdeteksi {det[y].mean():.0%} | recall {rec:.1%} "
                       f"precision {prec:.1%} (TP {tp}, FP {fp}) | UR {rec_u:.0%} MCF {rec_m:.0%}")

dst = OUT / "pose_conf_sweep_fulltest.csv"
with open(dst, "w", newline="") as fh:
    wr = csv.writer(fh)
    wr.writerow(["weights", "imgsz", "conf", "aturan", "lying_terdeteksi", "recall", "precision", "TP", "FP", "recall_urfall", "recall_mcf"])
    wr.writerows(rows)
print("tersimpan:", dst)

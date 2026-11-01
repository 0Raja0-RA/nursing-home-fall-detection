"""YOLO26 tanpa training pada 264 frame lying di test Data Baru (analog pose_resolution_sweep.py untuk YOLO11).

Dua mode:
  pose   : yolo*-pose pada beberapa resolusi -> % frame lying yang orangnya terdeteksi, sendi terbaca,
           sudut < 40 derajat, dan latensi per gambar (batch 1).
  person : detektor orang (kelas person) untuk membuat kotak otomatis -> % frame lying yang orangnya ditemukan.
           Dipakai untuk menilai alat pembuat kotak dataset v2.1.

Ambang confidence: inferensi dijalankan SEKALI pada ambang terendah, lalu hasilnya disaring ke tiap ambang di --conf.
Ini penting karena skor model end-to-end (NMS-free, seperti YOLO26) terkalibrasi berbeda dari YOLO11, sehingga satu
ambang (0,25) bisa tidak adil bagi salah satunya.

Contoh:
  python ml/archive/scripts/yolo26_zero_shot.py --mode pose
  python ml/archive/scripts/yolo26_zero_shot.py --mode pose --weights yolo26m-pose.pt --imgsz 1280 --conf 0.25 0.1 0.05
  python ml/archive/scripts/yolo26_zero_shot.py --mode person
"""
import argparse
import csv
import math
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from tqdm.auto import tqdm
from ultralytics import YOLO

NEW = Path(r"C:\Project_2026\Falling Detection\ml\data\processed_final")
OUT = Path(__file__).resolve().parents[2] / "outputs" / "yolo26_zero_shot"
OUT.mkdir(exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["pose", "person"], default="pose")
ap.add_argument("--weights", nargs="*", default=None)
ap.add_argument("--imgsz", nargs="*", type=int, default=[640, 960, 1280])
ap.add_argument("--conf", nargs="*", type=float, default=[0.25, 0.10, 0.05], help="daftar ambang yang dilaporkan")
ap.add_argument("--batch", type=int, default=4)       # kecil agar GPU 4 GB tidak kehabisan memori
a = ap.parse_args()
confs = sorted(set(a.conf), reverse=True)

if a.weights is None:
    a.weights = (["yolo11n-pose.pt", "yolo26n-pose.pt", "yolo26s-pose.pt", "yolo26m-pose.pt"] if a.mode == "pose"
                 else ["yolo11n.pt", "yolo11m.pt", "yolo26n.pt", "yolo26s.pt", "yolo26m.pt"])

imgs = []
for l in sorted((NEW / "labels" / "test").glob("*.txt")):
    t = l.read_text().split()
    if t and t[0] == "2":
        imgs.append(NEW / "images" / "test" / (l.stem + ".jpg"))
print(f"frame lying test: {len(imgs)} | mode: {a.mode} | ambang dilaporkan: {confs}")


def cam_of(p):
    m = re.match(r"mcf_s\d+_(c\d+)_", p.name)
    return m.group(1) if m else "cam0"


def run(weights, imgsz, pbar):
    model = YOLO(weights)
    kw = dict(imgsz=imgsz, conf=min(confs), verbose=False)
    if a.mode == "person":
        kw["classes"] = [0]
    model([str(imgs[0])], **kw)                                  # pemanasan
    top = []                                                     # per gambar: (conf tertinggi, sendi_ok, sudut, kamera)
    for i in range(0, len(imgs), a.batch):
        ch = imgs[i:i + a.batch]
        for p, r in zip(ch, model([str(x) for x in ch], **kw)):
            if len(r.boxes) == 0:
                top.append((0.0, False, 90.0, cam_of(p)))
                continue
            b = int(r.boxes.conf.argmax())
            cf = float(r.boxes.conf[b])
            ok, ang = False, 90.0
            if a.mode == "pose":
                k = r.keypoints.data[b].cpu().numpy()
                if (k[5][2] + k[6][2]) / 2 > 0.25 and (k[11][2] + k[12][2]) / 2 > 0.25:
                    ok = True
                    sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
                    hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
                    ang = math.degrees(math.atan2(abs(sy - hy), abs(sx - hx)))
            top.append((cf, ok, ang, cam_of(p)))
        pbar.update(len(ch))
    # latensi batch 1 pada 40 gambar pertama dengan ambang resmi (tertinggi)
    kw["conf"] = max(confs)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t0 = time.time()
    for p in imgs[:40]:
        model(str(p), **kw)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    return top, (time.time() - t0) / 40 * 1000


rows = []
n = len(imgs)
combos = [(w, s) for w in a.weights for s in a.imgsz]
outer = tqdm(total=len(combos), desc="Konfigurasi", unit="cfg", position=0, dynamic_ncols=True)
for w, s in combos:
    outer.set_postfix_str(f"{w} @{s}")
    pbar = tqdm(total=n, desc=f"  {w} @{s}", unit="img", position=1, leave=False, dynamic_ncols=True)
    try:
        top, ms = run(w, s, pbar)
    except Exception as e:                                        # OOM, bobot tidak ada, dsb.
        tqdm.write(f"{w:16s} imgsz={s:4d} GAGAL: {str(e)[:100]}")
        torch.cuda.empty_cache()
        pbar.close(); outer.update(1)
        continue
    pbar.close()
    for c in confs:
        det = sum(1 for t in top if t[0] >= c)
        joint = sum(1 for t in top if t[0] >= c and t[1])
        low = sum(1 for t in top if t[0] >= c and t[1] and t[2] < 40)
        extra = f" | sendi {joint}/{n} ({joint/n:.0%}) | sudut<40: {low}/{n} ({low/n:.0%})" if a.mode == "pose" else ""
        tqdm.write(f"{w:16s} imgsz={s:4d} conf={c:<4} | orang terdeteksi {det}/{n} ({det/n:.0%}){extra} | {ms:.0f} ms/gambar")
        rows.append([a.mode, w, s, c, det, joint, low, n, round(ms, 1)])
    percam = defaultdict(lambda: [0, 0])
    for t in top:
        percam[t[3]][0] += 1
        percam[t[3]][1] += int(t[0] >= confs[0])
    tqdm.write(f"     per kamera (conf={confs[0]}): " + str({c: f"{v[1]}/{v[0]}" for c, v in sorted(percam.items())}))
    torch.cuda.empty_cache()
    outer.update(1)
outer.close()

dst = OUT / f"yolo26_zero_shot_{a.mode}_conf.csv"
with open(dst, "w", newline="") as fh:
    wr = csv.writer(fh)
    wr.writerow(["mode", "weights", "imgsz", "conf", "terdeteksi", "sendi_terbaca", "sudut_lt40", "n", "ms_per_gambar"])
    wr.writerows(rows)
print("tersimpan:", dst)

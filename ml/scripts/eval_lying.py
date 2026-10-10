#!/usr/bin/env python3
"""
eval_lying.py  ->  ml/scripts/eval_lying.py
===========================================
Evaluasi "lying vs bukan-lying" yang SAMA untuk model 2 kelas dan 3 kelas,
supaya uji A/B bisa diputuskan dengan satu aturan.

Tiap gambar test punya satu orang/satu label. Skor gambar = confidence tertinggi
dari kotak berkelas lying_on_ground (0 bila tak ada). Kelas model dicari lewat
NAMA ('lying_on_ground'), jadi model 2 kelas (id 1) dan 3 kelas (id 2) sama-sama jalan.

Ground truth selalu dari dataset 3 kelas (0 normal, 1 transitional, 2 lying):
  - tabel UTAMA  : lying vs normal saja (frame bersih, tanpa transitional)
  - tabel DIAGNOSTIK: berapa % frame transitional yang diprediksi lying
    (transitional ambigu, jadi hanya diagnostik, BUKAN dihitung sebagai false positive utama)

Interval kepercayaan: bootstrap per VIDEO/SKENARIO (bukan per frame), karena frame
dari satu kejadian saling berkorelasi; sampel efektif = jumlah kejadian.

Contoh (di Kaggle, setelah training):
  python eval_lying.py --weights runs/exp_2cls/weights/best.pt \
      --gt-dir /kaggle/input/<dataset-3kelas> --out eval_2cls.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

THRESHOLDS = (0.10, 0.25, 0.40, 0.50, 0.60, 0.75)
GT_NORMAL, GT_TRANS, GT_LYING = 0, 1, 2
LYING_NAME = "lying_on_ground"


def video_of(stem: str) -> str:
    m = re.match(r"mcf_s(\d+)_c\d_f\d+$", stem)
    if m:
        return f"mcf-s{m.group(1)}"
    m = re.match(r"urfall_((?:fall|adl)-\d+)_f\d+$", stem)
    if m:
        return f"urfall-{m.group(1)}"
    return stem  # tak dikenal: tiap frame jadi kelompok sendiri


def average_precision(pos: np.ndarray, neg: np.ndarray) -> float:
    """AP lying-vs-normal; skor sama (mis. banyak 0) dihitung sebagai satu ambang."""
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ap, prev_recall = 0.0, 0.0
    for t in np.unique(np.concatenate([pos, neg]))[::-1]:
        tp, fp = int((pos >= t).sum()), int((neg >= t).sum())
        recall = tp / len(pos)
        ap += (recall - prev_recall) * tp / (tp + fp)
        prev_recall = recall
    return float(ap)


def metrics(scores: np.ndarray, gt: np.ndarray, thr: float) -> dict:
    s_l, s_n, s_t = scores[gt == GT_LYING], scores[gt == GT_NORMAL], scores[gt == GT_TRANS]
    tp, fp = int((s_l >= thr).sum()), int((s_n >= thr).sum())
    return {
        "recall": tp / len(s_l) if len(s_l) else float("nan"),
        "precision": tp / (tp + fp) if tp + fp else float("nan"),
        "fp_normal": fp,
        "fpr_normal": fp / len(s_n) if len(s_n) else float("nan"),
        "trans_as_lying": float((s_t >= thr).mean()) if len(s_t) else float("nan"),
        "ap": average_precision(s_l, s_n),
    }


def evaluate(scores, gt, videos, n_boot=500, seed=0):
    scores, gt, videos = np.asarray(scores, float), np.asarray(gt, int), np.asarray(videos)
    out = {"n": {"lying": int((gt == GT_LYING).sum()), "normal": int((gt == GT_NORMAL).sum()),
                 "transitional": int((gt == GT_TRANS).sum()),
                 "video_lying": len(set(videos[gt == GT_LYING]))},
           "thresholds": {}, "ap": average_precision(scores[gt == GT_LYING], scores[gt == GT_NORMAL])}
    by_vid = defaultdict(list)
    for i, v in enumerate(videos):
        by_vid[v].append(i)
    vids = sorted(by_vid)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(n_boot):
        pick = rng.choice(len(vids), size=len(vids), replace=True)
        idx = np.concatenate([by_vid[vids[k]] for k in pick])
        boots.append(idx)
    ap_b = [average_precision(scores[i][gt[i] == GT_LYING], scores[i][gt[i] == GT_NORMAL]) for i in boots]
    out["ap_ci"] = [float(np.nanpercentile(ap_b, 2.5)), float(np.nanpercentile(ap_b, 97.5))]
    for t in THRESHOLDS:
        m = metrics(scores, gt, t)
        rb = [metrics(scores[i], gt[i], t) for i in boots]
        for key in ("recall", "precision"):
            vals = [r[key] for r in rb if not np.isnan(r[key])]
            m[f"{key}_ci"] = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else [float("nan")] * 2
        out["thresholds"][f"{t:.2f}"] = m
    return out


def predict_scores(weights, images, imgsz, device, batch):
    from ultralytics import YOLO  # import di sini: skrip bisa diuji tanpa ultralytics
    model = YOLO(weights)
    ids = [k for k, v in model.names.items() if v == LYING_NAME]
    if len(ids) != 1:
        sys.exit(f"[FATAL] kelas '{LYING_NAME}' tidak ditemukan pada model: {model.names}")
    lid, scores = ids[0], []
    for i in range(0, len(images), batch):
        for r in model.predict([str(p) for p in images[i:i + batch]], conf=0.05, imgsz=imgsz,
                               device=device, verbose=False):
            b = r.boxes
            if b is None or len(b) == 0:
                scores.append(0.0)
                continue
            cls, conf = b.cls.cpu().numpy().astype(int), b.conf.cpu().numpy()
            scores.append(float(conf[cls == lid].max()) if (cls == lid).any() else 0.0)
    return np.array(scores)


def print_report(res, title):
    n = res["n"]
    print(f"\n=== {title} ===")
    print(f"test: lying={n['lying']} (dari {n['video_lying']} video/skenario), normal={n['normal']}, transitional={n['transitional']}")
    print(f"AP lying-vs-normal = {res['ap']:.3f}  (95% CI per-video: {res['ap_ci'][0]:.3f} - {res['ap_ci'][1]:.3f})")
    print(f"{'conf':>5} {'recall':>8} {'[CI]':>15} {'precision':>10} {'[CI]':>15} {'FP normal':>10} {'FPR':>7} {'trans->lying':>13}")
    for t, m in res["thresholds"].items():
        print(f"{t:>5} {m['recall']:>8.3f} [{m['recall_ci'][0]:.2f},{m['recall_ci'][1]:.2f}] "
              f"{m['precision']:>10.3f} [{m['precision_ci'][0]:.2f},{m['precision_ci'][1]:.2f}] "
              f"{m['fp_normal']:>10d} {m['fpr_normal']:>7.3f} {m['trans_as_lying']:>13.3f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evaluasi lying vs bukan-lying (2 kelas / 3 kelas)")
    ap.add_argument("--weights", required=True, type=Path)
    ap.add_argument("--gt-dir", required=True, type=Path, help="Folder dataset 3 kelas (punya images/test, labels/test)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--device", default="0")
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--out", type=Path, default=Path("eval_lying.json"))
    a = ap.parse_args(argv)

    img_dir, lbl_dir = a.gt_dir / "images" / "test", a.gt_dir / "labels" / "test"
    images = sorted(img_dir.glob("*.jpg"))
    if not images:
        sys.exit(f"[FATAL] tidak ada gambar di {img_dir}")
    gt, videos = [], []
    for p in images:
        lf = lbl_dir / f"{p.stem}.txt"
        if not lf.is_file():
            sys.exit(f"[FATAL] label hilang: {lf}")
        gt.append(int(lf.read_text().split()[0]))
        videos.append(video_of(p.stem))
    if set(gt) - {GT_NORMAL, GT_TRANS, GT_LYING} or GT_TRANS not in gt:
        sys.exit("[FATAL] --gt-dir harus dataset 3 kelas (kelas 0/1/2 semuanya ada)")
    scores = predict_scores(a.weights, images, a.imgsz, a.device, a.batch)
    res = evaluate(scores, gt, videos, n_boot=a.boot)
    res["weights"] = str(a.weights)
    a.out.write_text(json.dumps(res, indent=2))
    print_report(res, str(a.weights))
    print(f"\nTersimpan: {a.out}")


if __name__ == "__main__":
    main()

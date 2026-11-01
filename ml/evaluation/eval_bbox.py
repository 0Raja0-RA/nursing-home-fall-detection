"""
eval_bbox_on_dataset.py
=======================
Menguji model bounding box (mis. EXP-006 best.pt) pada split test dataset apa pun
dengan CARA EVALUASI YANG SAMA seperti tune_pose_fall.py (EXP-009): satu orang per
gambar (deteksi berkeyakinan tertinggi) -> kelas prediksi -> confusion matrix.
Dengan begitu hasil bbox dan pose bisa dibandingkan pada gambar yang sama.

Gambar tanpa deteksi dicatat terpisah ('none') dan, agar sebanding dengan pose,
dihitung sebagai kelas normal pada metrik utama.

Penggunaan:
    python ml/evaluation/eval_bbox.py --data-dir "ml/data/processed_final" \
        --weights ml/models/fall_detection/weights/best.pt \
        --out ml/outputs/bbox_on_new_data/exp_bbox_on_new_results.json \
        --csv ml/outputs/bbox_on_new_data/exp_bbox_on_new_predictions.csv
"""

import argparse
import csv
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from ultralytics import YOLO

CLASS_NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}


def source_of(name: str) -> str:
    return "mcf" if name.startswith("mcf_") else "urfall"


def camera_of(name: str) -> str:
    m = re.match(r"mcf_s\d+_(c\d+)_", name)
    return m.group(1) if m else "cam0"


def metrics(y_true, y_pred):
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    out = {"n": int(cm.sum()), "accuracy": float(np.trace(cm) / max(1, cm.sum())), "cm": cm.tolist(), "per_class": {}}
    f1s = []
    for c in range(3):
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        f1s.append(f1)
        out["per_class"][CLASS_NAMES[c]] = {"precision": float(p), "recall": float(r), "f1": float(f1), "support": int(cm[c, :].sum())}
    out["macro_f1"] = float(np.mean(f1s))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="ml/data/processed_final")
    ap.add_argument("--weights", default="ml/models/fall_detection/weights/best.pt")
    ap.add_argument("--split", default="test")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--out", default="ml/outputs/bbox_on_new_data/exp_bbox_on_new_results.json")
    ap.add_argument("--csv", default=None, help="Simpan prediksi per gambar")
    a = ap.parse_args()

    root = Path(a.data_dir).resolve()
    model = YOLO(a.weights)
    imgs = sorted((root / "images" / a.split).glob("*.jpg"))
    print(f"Model {a.weights} | {len(imgs)} gambar {a.split} dari {root}")

    rows = []
    t0 = time.time()
    for i in range(0, len(imgs), 32):
        chunk = imgs[i:i + 32]
        for p, r in zip(chunk, model([str(x) for x in chunk], conf=a.conf, verbose=False)):
            lbl = root / "labels" / a.split / (p.stem + ".txt")
            txt = lbl.read_text().split() if lbl.exists() else []
            if not txt:
                continue
            gt = int(txt[0])
            if len(r.boxes):
                b = int(r.boxes.conf.argmax())
                pred, conf = int(r.boxes.cls[b]), float(r.boxes.conf[b])
                lying_conf = float(r.boxes.conf[r.boxes.cls == 2].max()) if (r.boxes.cls == 2).any() else 0.0
            else:
                pred, conf, lying_conf = -1, 0.0, 0.0
            rows.append(dict(img=p.name, source=source_of(p.name), camera=camera_of(p.name), gt=gt, pred=pred, conf=conf, lying_conf=lying_conf))
    ms = (time.time() - t0) / max(1, len(rows)) * 1000
    print(f"{len(rows)} gambar dievaluasi, {ms:.1f} ms/gambar (termasuk baca disk)")

    def sel(f):
        return [r for r in rows if f(r)]

    def run(rs):
        yt = [r["gt"] for r in rs]
        yp = [0 if r["pred"] < 0 else r["pred"] for r in rs]      # tanpa deteksi -> normal (sebanding dg pose)
        m = metrics(yt, yp)
        lying = [r for r in rs if r["gt"] == 2]
        m["lying_not_detected"] = sum(1 for r in lying if r["pred"] < 0)
        m["lying_detected_as_lying"] = sum(1 for r in lying if r["pred"] == 2)
        m["lying_support"] = len(lying)
        return m

    result = {"weights": a.weights, "dataset": str(root), "split": a.split, "conf": a.conf, "ms_per_image": ms,
              "all": run(rows), "per_source": {}, "per_camera_mcf": {}}
    for s in ("urfall", "mcf"):
        rs = sel(lambda r: r["source"] == s)
        if rs:
            result["per_source"][s] = run(rs)
    for c in sorted({r["camera"] for r in rows if r["source"] == "mcf"}):
        result["per_camera_mcf"][c] = run(sel(lambda r: r["source"] == "mcf" and r["camera"] == c))

    def line(name, m):
        L = m["per_class"]["lying_on_ground"]
        print(f"  {name:8s} n={m['n']:5d} acc={m['accuracy']*100:5.1f}% macroF1={m['macro_f1']*100:5.1f}% | "
              f"lying n={m['lying_support']:3d}  R={L['recall']*100:5.1f}% P={L['precision']*100:5.1f}%  "
              f"(tak terdeteksi {m['lying_not_detected']})")

    print("\nRINGKASAN (kelas lying):")
    line("SEMUA", result["all"])
    for s, m in result["per_source"].items():
        line(s, m)
    print("\nPER KAMERA MCF:")
    for c, m in result["per_camera_mcf"].items():
        line(c, m)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print("\nhasil:", out.resolve())
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("prediksi per gambar:", Path(a.csv).resolve())


if __name__ == "__main__":
    main()

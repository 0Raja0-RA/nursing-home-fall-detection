"""
pose_visualize.py
=================
Visualisasi perbandingan keluaran pose dengan dua mode:

  thresholds : BEFORE vs AFTER threshold postur + prediksi vs ground truth (GIF satu kamera atau grid frame salah)
  configs    : banyak konfigurasi model/imgsz/conf/rotasi pada frame yang sama (grid per kamera + GIF per kejadian)

Warna border pada mode configs (proxy dari bbox label, bukan bukti titiknya tepat):
  hijau = orang benar + bahu & pinggul terbaca di dalam bbox
  kuning = orang ditemukan tetapi bukan deteksi teratas, atau sendi inti tidak terbaca
  merah = orang tidak ditemukan

Contoh (dari akar repo, dengan .venv aktif):
  python -m ml.evaluation.pose_visualize thresholds --prefix mcf_s19_c1
  python -m ml.evaluation.pose_visualize thresholds --prefix mcf_s19_c1 --before 0.25,40,60,1.25 --after 0.05,40,60,1.25
  python -m ml.evaluation.pose_visualize thresholds --mode misses --max-frames 24
  python -m ml.evaluation.pose_visualize configs --split val

Format --before/--after: conf,fall_angle,trans_angle,aspect_ratio
"""

import argparse
import collections
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

from ml.common.labels import CLASS_NAMES, camera_of, get_ground_truth, read_box
from ml.common.pose import calculate_spine_angle, predict, predict_class, score_frame
from ml.common.viz import crop_window, header, render

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]
CLASS_COLOR = {0: (113, 204, 46), 1: (0, 215, 255), 2: (50, 50, 255)}  # BGR
THRESHOLD_PANEL_W = 480

# (label, model, imgsz, conf, rotasi); config pertama menjadi baseline
CONFIGS = [
    ("n 640 (sekarang)", "yolo11n-pose.pt", 640, 0.25, False),
    ("n 640 conf .10", "yolo11n-pose.pt", 640, 0.10, False),
    ("n 640 + rotasi", "yolo11n-pose.pt", 640, 0.25, True),
    ("m 640", "yolo11m-pose.pt", 640, 0.25, False),
    ("m 1280", "yolo11m-pose.pt", 1280, 0.25, False),
    ("m 640 + rotasi", "yolo11m-pose.pt", 640, 0.25, True),
]


def save_gif(frames: list[np.ndarray], target: Path, fps: float):
    pil = [Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)) for fr in frames]
    pil[0].save(target, save_all=True, append_images=pil[1:], duration=int(1000 / fps), loop=0)


# ---------------------------------------------------------------- mode thresholds
def parse_threshold_cfg(text: str) -> dict:
    conf, fa, ta, ar = (float(v) for v in text.split(","))
    return {"conf": conf, "fall": fa, "trans": ta, "ar": ar}


def analyse(model, img: np.ndarray, cfg: dict) -> dict:
    """Pose lalu sudut/AR dengan fallback yang sama seperti pipeline EXP-009."""
    res = model(img, verbose=False, conf=cfg["conf"])[0]
    if len(res.boxes) == 0:
        return {"detected": False, "angle": 90.0, "ar": 0.5, "kpts": None, "bbox": None, "src": "no person -> fallback 90"}

    i = int(res.boxes.conf.argmax().item())
    x1, y1, x2, y2 = res.boxes.xyxy[i].tolist()
    ar = max(1.0, x2 - x1) / max(1.0, y2 - y1)
    kpts = res.keypoints.data[i].cpu().numpy()
    if (kpts[5][2] + kpts[6][2]) / 2 > 0.25 and (kpts[11][2] + kpts[12][2]) / 2 > 0.25:
        angle, src = calculate_spine_angle(kpts), "shoulder-hip"
    else:
        angle = 90.0 if ar < 0.8 else (20.0 if ar > 1.3 else 50.0)
        src = "bbox fallback (hip/shoulder hidden)"
    return {"detected": True, "angle": angle, "ar": ar, "kpts": kpts, "bbox": (x1, y1, x2, y2), "src": src}


def render_threshold_panel(img: np.ndarray, info: dict, cfg: dict, gt: int, title: str):
    pred = predict_class(info["angle"], info["ar"], cfg["fall"], cfg["trans"], cfg["ar"])
    wrong = pred != gt
    out = img.copy()
    h, w = out.shape[:2]

    if info["detected"]:
        x1, y1, x2, y2 = map(int, info["bbox"])
        cv2.rectangle(out, (x1, y1), (x2, y2), CLASS_COLOR[pred], 2)
        k = info["kpts"]
        for a, b in SKELETON:
            if k[a][2] > 0.25 and k[b][2] > 0.25:
                cv2.line(out, (int(k[a][0]), int(k[a][1])), (int(k[b][0]), int(k[b][1])), (230, 230, 230), 2)
        for j in range(17):
            if k[j][2] > 0.25:
                cv2.circle(out, (int(k[j][0]), int(k[j][1])), 4, (0, 255, 255), -1)
        if (k[5][2] + k[6][2]) / 2 > 0.25 and (k[11][2] + k[12][2]) / 2 > 0.25:
            sh = (int((k[5][0] + k[6][0]) / 2), int((k[5][1] + k[6][1]) / 2))
            hp = (int((k[11][0] + k[12][0]) / 2), int((k[11][1] + k[12][1]) / 2))
            cv2.line(out, sh, hp, (255, 0, 255), 4)

    out = cv2.resize(out, (THRESHOLD_PANEL_W, int(h * THRESHOLD_PANEL_W / w)))
    if wrong:
        cv2.rectangle(out, (0, 0), (out.shape[1] - 1, out.shape[0] - 1), (0, 0, 255), 6)

    lines = [
        f"{title}  conf>{cfg['conf']:.2f}  fall<{cfg['fall']:.0f} trans<{cfg['trans']:.0f}",
        f"GT: {CLASS_NAMES[gt]}   PRED: {CLASS_NAMES[pred]}  {'WRONG' if wrong else 'ok'}",
        f"angle={info['angle']:.0f} deg  AR={info['ar']:.2f}",
        info["src"],
    ]
    bar = np.full((88, out.shape[1], 3), 25, np.uint8)
    for n, text in enumerate(lines):
        color = (80, 80, 255) if (n == 1 and wrong) else ((0, 200, 255) if (n == 3 and not info["detected"]) else (235, 235, 235))
        cv2.putText(bar, text, (6, 18 + 21 * n), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return np.vstack([out, bar]), wrong


def run_thresholds(args):
    before, after = parse_threshold_cfg(args.before), parse_threshold_cfg(args.after)
    img_dir = Path(args.data_dir) / "images" / args.split
    lbl_dir = Path(args.data_dir) / "labels" / args.split
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.model)

    files = sorted(img_dir.glob("*.jpg"))
    if args.prefix:
        files = [f for f in files if f.name.startswith(args.prefix)]
    if not files:
        sys.exit("Tidak ada gambar yang cocok.")

    candidates = files
    if args.mode == "misses":
        candidates = [f for f in files if get_ground_truth(lbl_dir / f"{f.stem}.txt") == 2]
        candidates = candidates[:: max(1, len(candidates) // 400)]  # batasi biaya inferensi
    elif len(files) > args.max_frames:
        candidates = [files[round(i * (len(files) - 1) / (args.max_frames - 1))] for i in range(args.max_frames)]

    frames, n, before_wrong, after_wrong = [], 0, 0, 0
    for f in candidates:
        gt = get_ground_truth(lbl_dir / f"{f.stem}.txt")
        if gt is None:
            continue
        img = cv2.imread(str(f))
        left, wl = render_threshold_panel(img, analyse(model, img, before), before, gt, "BEFORE")
        right, wr = render_threshold_panel(img, analyse(model, img, after), after, gt, "AFTER")
        body = np.hstack([left, right])
        n += 1
        before_wrong += int(wl)
        after_wrong += int(wr)
        if args.mode == "gif" or wl or wr:
            frames.append(np.vstack([header(f.name, body.shape[1]), body]))

    print(f"Frame dianalisis: {n} | salah BEFORE: {before_wrong} | salah AFTER: {after_wrong}")
    if not frames:
        sys.exit("Tidak ada frame untuk disimpan.")

    if args.mode == "gif":
        target = out_dir / f"{args.prefix or 'seq'}_before_after.gif"
        save_gif(frames, target, args.fps)
    else:
        frames = frames[: args.max_frames]
        h, w = max(fr.shape[0] for fr in frames), frames[0].shape[1]
        rows = []
        for r in range(0, len(frames), 2):
            row = [np.pad(fr, ((0, h - fr.shape[0]), (0, 0), (0, 0))) for fr in frames[r:r + 2]]
            if len(row) < 2:
                row.append(np.zeros((h, w, 3), np.uint8))
            rows.append(np.hstack(row))
        target = out_dir / "lying_misses_grid.png"
        cv2.imwrite(str(target), np.vstack(rows))
    print(f"Tersimpan: {target.resolve()}")


# ------------------------------------------------------------------- mode configs
class Runner:
    """Inferensi dengan cache supaya frame yang sama tidak dihitung dua kali."""

    def __init__(self):
        self.models = {}
        self.cache = {}

    def run(self, path: Path, idx: int):
        key = (path, idx)
        if key not in self.cache:
            _, name, imgsz, conf, rotate = CONFIGS[idx]
            model = self.models.setdefault(name, YOLO(name))
            self.cache[key] = predict(model, cv2.imread(str(path)), imgsz, conf, rotate)
        return self.cache[key]


def compose(runner, path: Path, lbl_dir: Path, cols=len(CONFIGS)) -> np.ndarray:
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    cls, box = read_box(lbl_dir / f"{path.stem}.txt", w, h)
    window = crop_window(box, w, h)
    panels = []
    for i, cfg in enumerate(CONFIGS):
        dets = runner.run(path, i)
        panels.append(render(img, window, dets, score_frame(dets, box), cfg[0]))
    rows = [np.hstack(panels[r:r + cols]) for r in range(0, len(panels), cols)]
    body = np.vstack(rows)
    return np.vstack([header(f"{path.stem}   GT: {CLASS_NAMES[cls]}", body.shape[1]), body])


def even(items: list, n: int) -> list:
    if len(items) <= n:
        return list(items)
    if n == 1:
        return [items[len(items) // 2]]
    return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]


def run_configs(args):
    img_dir = Path(args.data_dir) / "images" / args.split
    lbl_dir = Path(args.data_dir) / "labels" / args.split
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    runner = Runner()

    by_class = collections.defaultdict(lambda: collections.defaultdict(list))
    labels = {}
    for f in sorted(img_dir.glob("*.jpg")):
        cls = get_ground_truth(lbl_dir / f"{f.stem}.txt")
        if cls is not None:
            labels[f] = cls
            by_class[cls][camera_of(f.name)].append(f)

    failed, passed = [], []
    for cam, files in sorted(by_class[2].items()):
        bad, ok = [], []
        for f in files:
            img = cv2.imread(str(f))
            h, w = img.shape[:2]
            _, box = read_box(lbl_dir / f"{f.stem}.txt", w, h)
            s = score_frame(runner.run(f, 0), box)
            (ok if s["top1"] and s["core"] else bad).append(f)
        print(f"lying {cam}: baseline gagal {len(bad)} / berhasil {len(ok)}", flush=True)
        failed += even(bad, 2)
        passed += even(ok, 1)

    other = []
    for cls in (0, 1):
        for cam in ("c1", "c3", "c6", "urfall"):
            other += even(by_class[cls].get(cam, []), 1)

    for name, files in (("grid_lying_baseline_gagal", failed), ("grid_lying_baseline_ok", passed),
                        ("grid_normal_transitional", other)):
        if not files:
            print(f"{name}: tidak ada frame, dilewati")
            continue
        cv2.imwrite(str(out / f"{name}.png"), np.vstack([compose(runner, f, lbl_dir) for f in files]))
        print(f"Tersimpan: {out / name}.png ({len(files)} frame)", flush=True)

    for prefix in args.sequences:
        files = [f for f in labels if f.name.startswith(prefix)]
        if not files:
            print(f"{prefix}: tidak ada di split {args.split}, dilewati")
            continue
        chosen = []
        for cls in (0, 1, 2):
            chosen += even([f for f in files if labels[f] == cls], args.per_class)
        chosen.sort(key=lambda f: f.name)
        target = out / f"seq_{prefix}.gif"
        save_gif([compose(runner, f, lbl_dir, cols=3) for f in chosen], target, args.fps)
        print(f"Tersimpan: {target} ({len(chosen)} frame)", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Visualisasi perbandingan keluaran pose")
    sub = ap.add_subparsers(dest="command", required=True)

    th = sub.add_parser("thresholds", help="BEFORE vs AFTER threshold postur")
    th.add_argument("--data-dir", default="ml/data/processed_final")
    th.add_argument("--split", default="test")
    th.add_argument("--model", default="yolo11n-pose.pt")
    th.add_argument("--prefix", default=None, help="Awalan nama file, mis. mcf_s19_c1 (mode gif)")
    th.add_argument("--mode", choices=["gif", "misses"], default="gif")
    th.add_argument("--before", default="0.25,35,55,1.25", help="conf,fall,trans,ar (default = demo_pose_fall.py)")
    th.add_argument("--after", default="0.25,40,60,1.25", help="conf,fall,trans,ar (default = tuning data baru)")
    th.add_argument("--max-frames", type=int, default=60)
    th.add_argument("--fps", type=float, default=3.0)
    th.add_argument("--out", default="ml/outputs/viz")
    th.set_defaults(func=run_thresholds)

    cf = sub.add_parser("configs", help="Banyak konfigurasi pose pada frame yang sama")
    cf.add_argument("--data-dir", default="ml/data/processed_final")
    cf.add_argument("--split", default="val")
    cf.add_argument("--sequences", nargs="*", default=["mcf_s15_c3", "mcf_s16_c2", "mcf_s17_c1", "mcf_s18_c7", "urfall_fall-23"],
                    help="Awalan nama file untuk GIF")
    cf.add_argument("--per-class", type=int, default=8, help="Frame per kelas dalam tiap GIF")
    cf.add_argument("--fps", type=float, default=2.0)
    cf.add_argument("--out", default="ml/outputs/viz/config_compare")
    cf.set_defaults(func=run_configs)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

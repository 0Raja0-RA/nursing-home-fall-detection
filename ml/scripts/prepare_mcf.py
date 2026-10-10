#!/usr/bin/env python3
"""
prepare_mcf.py  ->  ml/scripts/prepare_mcf.py
=============================================
Mengubah Multiple Cameras Fall Dataset (MCF, Univ. Montreal) menjadi dataset
YOLO 3 kelas (0 normal, 1 transitional, 2 lying_on_ground).

Alur per skenario (chute01..chute24):
  1. Baca anotasi kamera acuan (annotations.csv) -> segmen (start, end, kode).
  2. Petakan kode -> kelas lewat label_map.yaml.
  3. Pangkas "guard band" di batas antar-kelas (label tidak presisi di transisi).
  4. Ambil frame dengan stride per kelas (BUKAN dedup hash).
  5. Sinkronkan ke kamera lain:  f_cam = f_ref + delay[cam] - delay[ref]
     (rumus ini sudah divalidasi visual di S01 dan S10 dengan mcf_check.py).
  6. Bbox otomatis dari detektor person COCO (yolo11n.pt). Frame tanpa deteksi dibuang.
  7. Split PER SKENARIO (bukan per frame / per kamera) supaya tidak bocor.

Kamera tambahan hanya bermakna kalau sinkron. Skenario di --ref-only
(default: 24) hanya memakai kamera acuan, karena tabel delay S24 tidak cocok
dengan jumlah frame video (lihat mcf_check.py inspect).

Contoh pakai (dari root repo):
  # uji cepat, 2 skenario
  py ml/scripts/prepare_mcf.py --root ml/data/mcf/dataset --scenarios 1 10 \
        --output-dir ml/data/processed_mcf_test
  # penuh
  py ml/scripts/prepare_mcf.py --root ml/data/mcf/dataset
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import yaml

CLASS_NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}
TRANSITIONAL = 1
COLORS = {0: (46, 204, 113), 1: (0, 165, 255), 2: (0, 0, 230)}  # BGR
N_CAMS = 8
GATE_MIN_FRAMES = 30
GATE_MIN_SCENARIOS = 3


# --------------------------------------------------------------------------
# Pembacaan tabel
# --------------------------------------------------------------------------
def load_label_map(path: Path) -> dict[int, int]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = {int(k): int(v) for k, v in cfg["code_to_class"].items()}
    bad = {k: v for k, v in m.items() if v not in CLASS_NAMES}
    if bad:
        sys.exit(f"[FATAL] label_map.yaml berisi kelas di luar 0..2: {bad}")
    return m


def load_annotations(path: Path, label_map: dict[int, int]) -> dict[int, dict]:
    """-> {scenario: {'ref_cam': int, 'segments': [(start, end, code), ...]}}"""
    ann: dict[int, dict] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        need = {"scenario", "ref_cam", "start", "end", "code"}
        if not rd.fieldnames or not need.issubset(rd.fieldnames):
            sys.exit(f"[FATAL] {path} harus punya kolom {sorted(need)}; "
                     f"ditemukan: {rd.fieldnames}")
        for row in rd:
            s = int(row["scenario"])
            d = ann.setdefault(s, {"ref_cam": int(row["ref_cam"]), "segments": []})
            if int(row["ref_cam"]) != d["ref_cam"]:
                sys.exit(f"[FATAL] S{s:02d}: ref_cam tidak konsisten di annotations.csv")
            code = int(row["code"])
            if code not in label_map:
                sys.exit(f"[FATAL] S{s:02d}: kode {code} tidak ada di label_map.yaml")
            d["segments"].append((int(row["start"]), int(row["end"]), code))
    for d in ann.values():
        d["segments"].sort()
    return ann


def load_delays(path: Path) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = [f"cam{c}" for c in range(1, N_CAMS + 1)]
        if not rd.fieldnames or not set(cols).issubset(rd.fieldnames):
            sys.exit(f"[FATAL] {path} harus punya kolom scenario,{','.join(cols)}")
        for row in rd:
            out[int(row["scenario"])] = [int(row[c]) for c in cols]
    return out


# --------------------------------------------------------------------------
# Lokasi video
# --------------------------------------------------------------------------
def find_scenario_dir(root: Path, s: int) -> Path | None:
    name = f"chute{s:02d}"
    if root.name == name and root.is_dir():
        return root
    direct = root / name
    if direct.is_dir():
        return direct
    for p in root.rglob(name):
        if p.is_dir():
            return p
    return None


def find_video(root: Path, s: int, cam: int) -> Path | None:
    sdir = find_scenario_dir(root, s)
    if sdir is None:
        return None
    for p in sorted(sdir.rglob("*")):
        if p.is_file() and p.suffix.lower() == ".avi":
            m = re.search(r"cam\D*0*(\d+)", p.stem, re.IGNORECASE)
            if m and int(m.group(1)) == cam:
                return p
    return None


# --------------------------------------------------------------------------
# Perencanaan frame (murni logika, mudah diuji)
# --------------------------------------------------------------------------
def plan_ref_frames(segments, label_map, strides, guard):
    """Kembalikan list (frame_ref, kelas).

    Guard band: pada segmen kelas normal/lying, `guard` frame di sisi yang
    berbatasan dengan kelas LAIN dibuang. Segmen transitional tidak dipangkas
    (memang pendek dan memang batas).
    """
    classes = [label_map[c] for (_, _, c) in segments]
    plan = []
    for i, (start, end, _code) in enumerate(segments):
        cls = classes[i]
        lo, hi = start, end
        if cls != TRANSITIONAL:
            if i > 0 and classes[i - 1] != cls:
                lo = start + guard
            if i < len(segments) - 1 and classes[i + 1] != cls:
                hi = end - guard
        if hi < lo:
            continue
        for f in range(lo, hi + 1, strides[cls]):
            plan.append((f, cls))
    return plan


def map_to_cam(f_ref, delays, ref_cam, cam):
    """Rumus sinkronisasi yang sudah divalidasi: f_cam = f_ref + d_cam - d_ref."""
    return f_ref + delays[cam - 1] - delays[ref_cam - 1]


def split_of(s, ranges):
    for name, (a, b) in ranges.items():
        if a <= s <= b:
            return name
    return None


# --------------------------------------------------------------------------
# Video & deteksi
# --------------------------------------------------------------------------
def read_selected(video_path: Path, wanted: set[int]) -> dict[int, np.ndarray]:
    """Baca berurutan (seek AVI tidak akurat) dan simpan hanya indeks 0-based yang diminta."""
    out: dict[int, np.ndarray] = {}
    if not wanted:
        return out
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return out
    last = max(wanted)
    i = 0
    while i <= last:
        if i in wanted:
            ok, fr = cap.read()
            if not ok:
                break
            out[i] = fr
        elif not cap.grab():
            break
        i += 1
    cap.release()
    return out


def run_detector(model, frames, conf_floor, batch, imgsz=640):
    """-> per frame: list of (conf, xc, yc, w, h) ternormalisasi. Diganti saat uji."""
    res_all = []
    for i in range(0, len(frames), batch):
        chunk = frames[i:i + batch]
        res = model.predict(chunk, classes=[0], conf=conf_floor, imgsz=imgsz,
                            verbose=False)
        for r in res:
            dets = []
            if r.boxes is not None and len(r.boxes):
                xywhn = r.boxes.xywhn.cpu().numpy()
                conf = r.boxes.conf.cpu().numpy()
                for (xc, yc, w, h), c in zip(xywhn, conf):
                    dets.append((float(c), float(xc), float(yc), float(w), float(h)))
            res_all.append(dets)
    return res_all


def pick_box(dets, cls, conf, conf_hard):
    thr = conf if cls == 0 else conf_hard
    ok = [d for d in dets if d[0] >= thr]
    if not ok:
        return None
    return max(ok, key=lambda d: d[3] * d[4])  # kotak terbesar


# --------------------------------------------------------------------------
# Filter objek statis (false positive yang menetap di satu tempat)
# --------------------------------------------------------------------------
def iou_xywh(a, b):
    ax1, ay1, ax2, ay2 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1, bx2, by2 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def find_static_distractors(classes, dets, iou_thr=0.6, min_normal=3):
    """Cari kotak yang muncul di tempat SAMA pada >= min_normal frame 'normal'
    dan juga pada >= 1 frame 'lying'. Orang berjalan tidak diam di satu kotak,
    dan orang berbaring tidak punya kotak yang sama dengan orang berdiri,
    jadi kotak seperti itu adalah benda (rak, tas, kursi), bukan orang.
    classes: kelas tiap frame; dets: list deteksi tiap frame.
    Return: set (indeks_frame, indeks_deteksi) yang harus diabaikan."""
    clusters = []  # {'rep': (xc,yc,w,h), 'members': [(k, j)]}
    for k, dl in enumerate(dets):
        for j, d in enumerate(dl):
            box = d[1:]
            for cl in clusters:
                if iou_xywh(cl["rep"], box) >= iou_thr:
                    cl["members"].append((k, j))
                    break
            else:
                clusters.append({"rep": box, "members": [(k, j)]})
    bad = set()
    for cl in clusters:
        by_cls = defaultdict(set)
        for k, _ in cl["members"]:
            by_cls[classes[k]].add(k)
        if len(by_cls[0]) >= min_normal and len(by_cls[2]) >= 1:
            bad.update(cl["members"])
    return bad


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------
def make_preview(out_dir: Path, rows, filename, per_class=6, seed=0, lowest=False):
    """rows: list dict {split, stem, cls, conf}. lowest=True -> tampilkan conf TERENDAH
    (kasus terburuk yang lolos ambang), bukan sampel acak."""
    rng = random.Random(seed)
    rows_out = []
    for cls in (0, 1, 2):
        pool = [r for r in rows if r["cls"] == cls]
        if lowest:
            pool.sort(key=lambda r: r["conf"])
        else:
            rng.shuffle(pool)
        tiles = []
        for r in pool[:per_class]:
            img = cv2.imread(str(out_dir / "images" / r["split"] / (r["stem"] + ".jpg")))
            if img is None:
                continue
            h, w = img.shape[:2]
            _, xc, yc, bw, bh = (r["cls"], *r["box"])
            x1, y1 = int((xc - bw / 2) * w), int((yc - bh / 2) * h)
            x2, y2 = int((xc + bw / 2) * w), int((yc + bh / 2) * h)
            cv2.rectangle(img, (x1, y1), (x2, y2), COLORS[r["cls"]], 3)
            cv2.putText(img, f"{CLASS_NAMES[r['cls']]} conf={r['conf']:.2f} {r['stem'][4:]}",
                        (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
            tiles.append(cv2.resize(img, (360, 240)))
        while len(tiles) < per_class:
            tiles.append(np.zeros((240, 360, 3), np.uint8))
        rows_out.append(np.hstack(tiles))
    path = out_dir / filename
    cv2.imwrite(str(path), np.vstack(rows_out))
    return path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def parse_args(argv=None):
    here = Path(__file__).resolve().parent.parent  # .../ml
    p = argparse.ArgumentParser(description="MCF -> YOLO 3 kelas")
    p.add_argument("--root", required=True, type=Path,
                   help="Folder induk berisi chute01..chute24")
    p.add_argument("--annotations", type=Path, default=here / "data/mcf/annotations.csv")
    p.add_argument("--delays", type=Path, default=here / "data/mcf/frame_delay.csv")
    p.add_argument("--label-map", type=Path, default=here / "data/mcf/label_map.yaml")
    p.add_argument("--output-dir", type=Path, default=here / "data/processed_mcf")
    p.add_argument("--scenarios", type=int, nargs="+", default=list(range(1, 25)))
    p.add_argument("--cams", type=int, nargs="+", default=list(range(1, N_CAMS + 1)))
    p.add_argument("--ref-only", type=int, nargs="*", default=[24],
                   help="Skenario yang hanya memakai kamera acuan (default: 24)")
    p.add_argument("--normal-stride", type=int, default=30)
    p.add_argument("--transitional-stride", type=int, default=2)
    p.add_argument("--lying-stride", type=int, default=10)
    p.add_argument("--guard", type=int, default=12,
                   help="Frame yang dibuang di batas antar-kelas (default 12)")
    p.add_argument("--base", type=int, choices=(0, 1), default=1,
                   help="Nomor frame pertama di anotasi (default 1). Salah 1 frame tak berpengaruh.")
    p.add_argument("--train", type=int, nargs=2, default=[1, 16])
    p.add_argument("--val", type=int, nargs=2, default=[17, 20])
    p.add_argument("--test", type=int, nargs=2, default=[21, 24])
    p.add_argument("--detector", default="yolo11n.pt")
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--conf-hard", type=float, default=0.15)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--imgsz", type=int, default=640,
                   help="Resolusi inferensi detektor (naikkan ke 960/1280 untuk orang kecil/berbaring)")
    p.add_argument("--no-static-filter", action="store_true",
                   help="Matikan filter objek statis (tidak disarankan)")
    p.add_argument("--jpg-quality", type=int, default=95)
    p.add_argument("--force", action="store_true",
                   help="Hapus images/ labels/ lama di output-dir lalu tulis ulang")
    return p.parse_args(argv)


def main(argv=None, model=None):
    a = parse_args(argv)
    root = a.root.resolve()
    out = a.output_dir.resolve()
    if not root.is_dir():
        sys.exit(f"[FATAL] --root tidak ada: {root}")
    if out == root or root in out.parents:
        sys.exit("[FATAL] output-dir tidak boleh sama dengan / di dalam --root")
    for f in (a.annotations, a.delays, a.label_map):
        if not f.is_file():
            sys.exit(f"[FATAL] file tidak ditemukan: {f}")

    label_map = load_label_map(a.label_map)
    ann = load_annotations(a.annotations, label_map)
    delays = load_delays(a.delays)
    strides = {0: a.normal_stride, 1: a.transitional_stride, 2: a.lying_stride}
    ranges = {"train": tuple(a.train), "val": tuple(a.val), "test": tuple(a.test)}

    if (out / "images").exists() or (out / "labels").exists():
        if not a.force:
            sys.exit(f"[FATAL] {out} sudah berisi images/labels. Pakai --force atau output-dir baru.")
        shutil.rmtree(out / "images", ignore_errors=True)
        shutil.rmtree(out / "labels", ignore_errors=True)
    for sp in ranges:
        (out / "images" / sp).mkdir(parents=True, exist_ok=True)
        (out / "labels" / sp).mkdir(parents=True, exist_ok=True)

    if model is None:
        from ultralytics import YOLO  # impor lambat, hanya saat dibutuhkan
        model = YOLO(a.detector)
    conf_floor = min(a.conf, a.conf_hard)

    stats = defaultdict(lambda: {"frames": 0, "scen": set()})
    dropped_nodet = defaultdict(int)
    dropped_oob = defaultdict(int)
    filtered_static = defaultdict(int)
    cand_cnt = defaultdict(int)
    kept_cnt = defaultdict(int)
    box_rows = []
    missing = []
    scen_split = {}

    for s in sorted(a.scenarios):
        if s not in ann or s not in delays:
            print(f"[WARN] S{s:02d}: tidak ada di annotations/delay -> dilewati")
            continue
        split = split_of(s, ranges)
        if split is None:
            print(f"[WARN] S{s:02d}: tidak masuk rentang split manapun -> dilewati")
            continue
        scen_split[s] = split
        ref = ann[s]["ref_cam"]
        cams = [ref] if s in a.ref_only else [c for c in a.cams]
        plan = plan_ref_frames(ann[s]["segments"], label_map, strides, a.guard)
        n_done = 0
        for cam in cams:
            vp = find_video(root, s, cam)
            if vp is None:
                missing.append((s, cam))
                continue
            items = []  # (indeks0, f_cam, cls)
            for f_ref, cls in plan:
                f_cam = map_to_cam(f_ref, delays[s], ref, cam)
                idx = f_cam - a.base
                if idx < 0:
                    dropped_oob[cls] += 1
                    continue
                items.append((idx, f_cam, cls))
            frames = read_selected(vp, {i for i, _, _ in items})
            sel = [(i, fc, c) for (i, fc, c) in items if i in frames]
            for (i, fc, c) in items:
                if i not in frames:
                    dropped_oob[c] += 1
            if not sel:
                continue
            dets = run_detector(model, [frames[i] for i, _, _ in sel], conf_floor, a.batch, a.imgsz)
            dets = [[d for d in dl if d[0] >= conf_floor] for dl in dets]
            bad = set() if a.no_static_filter else find_static_distractors(
                [c for _, _, c in sel], dets)
            for k, ((i, fc, c), dl) in enumerate(zip(sel, dets)):
                cand_cnt[(cam, c)] += 1
                before = pick_box(dl, c, a.conf, a.conf_hard)
                kept = [d for j, d in enumerate(dl) if (k, j) not in bad]
                b = pick_box(kept, c, a.conf, a.conf_hard)
                if before is not None and b != before:
                    filtered_static[c] += 1
                if b is None:
                    dropped_nodet[c] += 1
                    continue
                conf_b, xc, yc, w, h = b
                kept_cnt[(cam, c)] += 1
                stem = f"mcf_s{s:02d}_c{cam}_f{fc:05d}"
                cv2.imwrite(str(out / "images" / split / f"{stem}.jpg"), frames[i],
                            [cv2.IMWRITE_JPEG_QUALITY, a.jpg_quality])
                (out / "labels" / split / f"{stem}.txt").write_text(
                    f"{c} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
                box_rows.append({"split": split, "stem": stem, "cls": c, "conf": conf_b,
                                 "box": (xc, yc, w, h), "n_cands": len(kept)})
                stats[(split, c)]["frames"] += 1
                stats[(split, c)]["scen"].add(s)
                n_done += 1
        print(f"[S{s:02d}] split={split:<5} ref_cam={ref} cams={len(cams)} "
              f"-> {n_done} frame ditulis")

    # data.yaml: sengaja TANPA 'path' -> Ultralytics memakai lokasi yaml ini.
    (out / "data.yaml").write_text(yaml.safe_dump({
        "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": 3, "names": CLASS_NAMES}, sort_keys=False), encoding="utf-8")
    manifest = {
        "source": "MCF (Multiple Cameras Fall Dataset)",
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(a).items()},
        "strides": strides, "split_ranges": ranges,
        "scenario_split": scen_split,
        "counts": {f"{sp}/{CLASS_NAMES[c]}": {"frames": st["frames"],
                                              "scenarios": sorted(st["scen"])}
                   for (sp, c), st in sorted(stats.items())},
        "dropped_no_detection": {CLASS_NAMES[c]: n for c, n in dropped_nodet.items()},
        "dropped_out_of_range": {CLASS_NAMES[c]: n for c, n in dropped_oob.items()},
        "box_changed_by_static_filter": {CLASS_NAMES[c]: n for c, n in filtered_static.items()},
        "retention_per_cam": {f"cam{k}/{CLASS_NAMES[c]}": [kept_cnt[(k, c)], cand_cnt[(k, c)]]
                              for k in range(1, N_CAMS + 1) for c in (0, 1, 2)},
        "missing_videos": missing,
    }
    (out / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2),
                                               encoding="utf-8")

    print("\n================ RINGKASAN (frame / skenario) ================")
    print(f"{'split':<6}" + "".join(f"{CLASS_NAMES[c]:>22}" for c in (0, 1, 2)))
    warns = []
    for sp in ("train", "val", "test"):
        row = f"{sp:<6}"
        for c in (0, 1, 2):
            st = stats.get((sp, c))
            n, k = (st["frames"], len(st["scen"])) if st else (0, 0)
            row += f"{n:>14} / {k:<5}"
            if n < GATE_MIN_FRAMES or k < GATE_MIN_SCENARIOS:
                warns.append(f"{sp}/{CLASS_NAMES[c]}: {n} frame, {k} skenario "
                             f"(minimal {GATE_MIN_FRAMES} frame & {GATE_MIN_SCENARIOS} skenario)")
        print(row)
    print("\nDibuang karena detektor tidak menemukan orang:",
          {CLASS_NAMES[c]: n for c, n in dropped_nodet.items()} or 0)
    print("\nRetensi per kamera (tertahan/kandidat) - cari kamera yang 'hilang' total:")
    print(f"{'kelas':<18}" + "".join(f"{'cam' + str(c):>10}" for c in range(1, N_CAMS + 1)))
    for c in (0, 1, 2):
        print(f"{CLASS_NAMES[c]:<18}" + "".join(
            f"{str(kept_cnt[(k, c)]) + '/' + str(cand_cnt[(k, c)]):>10}" for k in range(1, N_CAMS + 1)))
    print("\nFrame yang kotaknya dibuang/diganti filter objek statis:",
          {CLASS_NAMES[c]: n for c, n in filtered_static.items()} or 0)
    print("Dibuang karena di luar rentang video:",
          {CLASS_NAMES[c]: n for c, n in dropped_oob.items()} or 0)
    if missing:
        print(f"[WARN] video tidak ditemukan: {missing[:10]}{' ...' if len(missing) > 10 else ''}")
    for w in warns:
        print(f"[WARN] data kurang -> {w}")
    if box_rows:
        with open(out / "boxes.csv", "w", newline="", encoding="utf-8") as f:
            w_ = csv.writer(f)
            w_.writerow(["split", "stem", "cls", "conf", "xc", "yc", "w", "h", "n_cands"])
            for r in box_rows:
                w_.writerow([r["split"], r["stem"], r["cls"], f"{r['conf']:.3f}",
                             *[f"{x:.5f}" for x in r["box"]], r["n_cands"]])
        print(f"\nPreview acak      : {make_preview(out, box_rows, 'preview_mcf.jpg')}")
        print(f"Preview conf rendah: {make_preview(out, box_rows, 'preview_lowconf.jpg', lowest=True)}")
        for c in (0, 1, 2):
            cs = sorted(r["conf"] for r in box_rows if r["cls"] == c)
            if cs:
                print(f"  conf kotak {CLASS_NAMES[c]:<16}: min={cs[0]:.2f}  median={cs[len(cs)//2]:.2f}  "
                      f"<0.30: {sum(x < 0.30 for x in cs)}/{len(cs)}")
    print(f"Dataset: {out}")


if __name__ == "__main__":
    main()

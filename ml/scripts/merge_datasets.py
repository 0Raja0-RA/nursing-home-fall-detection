#!/usr/bin/env python3
"""
merge_datasets.py  ->  ml/scripts/merge_datasets.py
===================================================
Menggabungkan dataset YOLO hasil prepare_dataset.py (UR Fall) dan
prepare_mcf.py (MCF) menjadi satu dataset v2 untuk training di Kaggle.

Aturan:
  - Split TIDAK diacak ulang: train/val/test tiap sumber tetap di split-nya
    (split sudah dibuat per video/skenario di skrip masing-masing).
  - Pengecualian opsional: --mcf-split memindahkan file MCF antar-split
    PER SKENARIO tanpa menjalankan ulang prepare_mcf.py (yang lama).
  - Nama file harus unik (prefix urfall_ / mcf_). Bentrok -> berhenti.
  - Tiap label divalidasi (5 kolom, kelas 0..2, koordinat 0..1).
  - data.yaml sengaja tanpa 'path'.

Contoh (dari root repo):
  py ml/scripts/merge_datasets.py \
      --src ml/data/processed_urfall ml/data/processed_mcf \
      --output-dir ml/data/processed_v2 --zip
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import re
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

CLASS_NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}
SPLITS = ("train", "val", "test")


def check_label(path: Path) -> int:
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    if not lines:
        raise ValueError("label kosong")
    cls = None
    for l in lines:
        p = l.split()
        if len(p) != 5:
            raise ValueError(f"harus 5 kolom: {l!r}")
        c = int(p[0])
        v = list(map(float, p[1:]))
        if c not in CLASS_NAMES or not all(0.0 <= x <= 1.0 for x in v):
            raise ValueError(f"nilai tidak valid: {l!r}")
        cls = c if cls is None else cls
    return cls


def parse_mcf_split(text):
    """'train=1-14,val=15-18,test=19-24' -> {scenario: split}. Wajib menutup 1..24 tanpa tumpang tindih."""
    m = {}
    for part in text.split(","):
        name, rng = part.split("=")
        name = name.strip()
        if name not in SPLITS:
            sys.exit(f"[FATAL] nama split tidak dikenal: {name!r}")
        a, b = map(int, rng.split("-"))
        for sc in range(a, b + 1):
            if sc in m:
                sys.exit(f"[FATAL] skenario {sc} muncul di dua split")
            m[sc] = name
    missing = [sc for sc in range(1, 25) if sc not in m]
    if missing:
        sys.exit(f"[FATAL] skenario belum ditempatkan di split manapun: {missing}")
    return m


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gabung dataset YOLO")
    ap.add_argument("--src", nargs="+", type=Path, required=True,
                    help="Folder dataset sumber (masing-masing punya images/ & labels/)")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--mcf-split", type=str, default=None,
                    help='Atur ulang split file MCF per skenario, mis. "train=1-14,val=15-18,test=19-24"')
    ap.add_argument("--zip", action="store_true", help="Buat <output-dir>.zip untuk Kaggle")
    ap.add_argument("--force", action="store_true", help="Timpa output-dir yang sudah ada")
    a = ap.parse_args(argv)
    mcf_map = parse_mcf_split(a.mcf_split) if a.mcf_split else None

    out = a.output_dir.resolve()
    srcs = [s.resolve() for s in a.src]
    for s in srcs:
        if not (s / "images").is_dir() or not (s / "labels").is_dir():
            sys.exit(f"[FATAL] bukan dataset YOLO (tanpa images/labels): {s}")
        if out == s or s in out.parents or out in s.parents:
            sys.exit(f"[FATAL] output-dir tidak boleh tumpang tindih dengan sumber: {s}")
    if out.exists() and any(out.iterdir()):
        if not a.force:
            sys.exit(f"[FATAL] {out} tidak kosong. Pakai --force atau folder baru.")
        shutil.rmtree(out)
    for sp in SPLITS:
        (out / "images" / sp).mkdir(parents=True)
        (out / "labels" / sp).mkdir(parents=True)

    seen: set[str] = set()
    table = defaultdict(int)  # (src_name, split, cls) -> n
    skipped = defaultdict(int)
    scen_by_split = defaultdict(set)
    for src in srcs:
        for sp in SPLITS:
            img_dir, lbl_dir = src / "images" / sp, src / "labels" / sp
            if not lbl_dir.is_dir():
                continue
            for lf in sorted(lbl_dir.glob("*.txt")):
                img = img_dir / (lf.stem + ".jpg")
                if not img.is_file():
                    skipped[f"{src.name}: gambar hilang"] += 1
                    continue
                try:
                    cls = check_label(lf)
                except ValueError as e:
                    skipped[f"{src.name}: label rusak ({e})"] += 1
                    continue
                tsp = sp
                mm = re.match(r"mcf_s(\d+)_", lf.stem)
                if mcf_map and mm:
                    tsp = mcf_map[int(mm.group(1))]
                    scen_by_split[tsp].add(int(mm.group(1)))
                if lf.stem in seen:
                    sys.exit(f"[FATAL] nama bentrok antar-sumber: {lf.stem}")
                seen.add(lf.stem)
                for s_, d_ in ((img, out / "images" / tsp / img.name),
                               (lf, out / "labels" / tsp / lf.name)):
                    try:
                        os.link(s_, d_)  # hemat disk; jatuh ke salin jika beda drive
                    except OSError:
                        shutil.copy2(s_, d_)
                table[(src.name, tsp, cls)] += 1

    (out / "data.yaml").write_text(yaml.safe_dump({
        "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": 3, "names": CLASS_NAMES}, sort_keys=False), encoding="utf-8")
    (out / "dataset_manifest.json").write_text(json.dumps({
        "sources": [str(s) for s in srcs],
        "counts": {f"{k[0]}/{k[1]}/{CLASS_NAMES[k[2]]}": v for k, v in sorted(table.items())},
        "skipped": dict(skipped)}, indent=2), encoding="utf-8")

    print(f"{'sumber':<20}{'split':<7}" + "".join(f"{CLASS_NAMES[c]:>18}" for c in (0, 1, 2)))
    total = defaultdict(int)
    for src in srcs:
        for sp in SPLITS:
            row = f"{src.name:<20}{sp:<7}"
            for c in (0, 1, 2):
                n = table.get((src.name, sp, c), 0)
                total[(sp, c)] += n
                row += f"{n:>18}"
            print(row)
    print("-" * 80)
    for sp in SPLITS:
        print(f"{'GABUNGAN':<20}{sp:<7}" + "".join(f"{total[(sp, c)]:>18}" for c in (0, 1, 2)))
    if mcf_map:
        print("\nSkenario MCF per split:",
              {sp: sorted(scen_by_split[sp]) for sp in SPLITS})
    for k, v in skipped.items():
        print(f"[WARN] dilewati {v}: {k}")
    for sp in SPLITS:
        for c in (0, 1, 2):
            if total[(sp, c)] == 0:
                print(f"[WARN] {sp}/{CLASS_NAMES[c]} kosong -> evaluasi kelas ini tidak bermakna")

    if a.zip:
        zp = out.with_suffix(".zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:  # JPEG sudah terkompresi
            for f in out.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(out).as_posix())
        print(f"ZIP: {zp}  ({zp.stat().st_size / 1e6:.0f} MB)")
    print(f"Dataset v2: {out}")


if __name__ == "__main__":
    main()

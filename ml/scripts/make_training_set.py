#!/usr/bin/env python3
"""
make_training_set.py  ->  ml/scripts/make_training_set.py
=========================================================
Membuat dataset training FINAL dari ml/data/processed_v2 (3 kelas hasil audit):

  Mode default (2 kelas)  : 0 = normal, 1 = lying_on_ground   (transitional dibuang)
  --keep-transitional     : 0 = normal, 1 = transitional, 2 = lying_on_ground

Dua mode ini dipakai untuk uji A/B di Kaggle: apakah kelas transitional layak
dipertahankan? Perbedaan hanya di kelas transitional; koreksi ADL sama.

Penanganan frame lying dari sequence ADL UR Fall (orang BUKAN jatuh):
  --adl-lying-normal adl-10 adl-11   -> jadikan NORMAL (berbaring di sofa/kasur)
  --adl-lying-drop   adl-30 ...      -> buang frame lying-nya (ambigu)
  (sequence ADL lain yang berisi lying tetap LYING)

Mitigasi ketimpangan (opsional, hanya split TRAIN, hanya mode --keep-transitional):
  --transitional-keep-frac 0.5       -> simpan 50% frame transitional (acak, seed tetap)
  Ultralytics tidak punya class weight per kelas, jadi mitigasi dilakukan di level data.
  val/test TIDAK pernah disubsampel supaya metrik dua mode tetap sebanding.

Prasyarat: audit_dataset.py sudah dijalankan (menghasilkan frames_meta.csv).

Contoh (dari root repo):
  py ml/scripts/make_training_set.py --dataset ml/data/processed_v2 \
      --output-dir ml/data/processed_v2_3cls --keep-transitional \
      --adl-lying-normal adl-10 adl-11 --adl-lying-drop adl-21 ... --zip
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import yaml

NAMES_2 = {0: "normal", 1: "lying_on_ground"}
NAMES_3 = {0: "normal", 1: "transitional", 2: "lying_on_ground"}
SPLITS = ("train", "val", "test")
GROUPS = ("urfall-fall", "urfall-adl", "mcf")


def new_class(row, adl_normal, adl_drop, keep_trans):
    """-> kelas baru atau None bila frame dibuang."""
    cls, group, video = int(row["cls"]), row["group"], row["video"]
    lying = 2 if keep_trans else 1
    if cls == 1:
        return 1 if keep_trans else None
    if cls == 0:
        return 0
    # cls == 2 (lying)
    if group == "urfall-adl":
        if video in adl_drop:
            return None
        if video in adl_normal:
            return 0
    return lying


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dataset training final (2 atau 3 kelas)")
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--keep-transitional", action="store_true",
                    help="Pertahankan transitional (3 kelas). Default: dibuang (2 kelas).")
    ap.add_argument("--transitional-keep-frac", type=float, default=1.0,
                    help="Fraksi frame transitional yang disimpan di TRAIN (0-1). Hanya dengan --keep-transitional.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--adl-lying-normal", nargs="*", default=[])
    ap.add_argument("--adl-lying-drop", nargs="*", default=[])
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if not 0.0 < a.transitional_keep_frac <= 1.0:
        sys.exit("[FATAL] --transitional-keep-frac harus di (0, 1]")
    if a.transitional_keep_frac < 1.0 and not a.keep_transitional:
        sys.exit("[FATAL] --transitional-keep-frac hanya berarti dengan --keep-transitional")

    names = NAMES_3 if a.keep_transitional else NAMES_2
    ncls = len(names)

    src, out = a.dataset.resolve(), a.output_dir.resolve()
    meta_path = src / "frames_meta.csv"
    if not meta_path.is_file():
        sys.exit("[FATAL] frames_meta.csv tidak ada. Jalankan audit_dataset.py --dataset <folder> dulu.")
    if out == src or src in out.parents or out in src.parents:
        sys.exit("[FATAL] output-dir tidak boleh tumpang tindih dengan --dataset")
    both = set(a.adl_lying_normal) & set(a.adl_lying_drop)
    if both:
        sys.exit(f"[FATAL] sequence ada di dua daftar: {sorted(both)}")

    with open(meta_path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    known_adl_lying = {r["video"] for r in rows if r["group"] == "urfall-adl" and r["cls"] == "2"}
    unknown = (set(a.adl_lying_normal) | set(a.adl_lying_drop)) - known_adl_lying
    if unknown:
        sys.exit(f"[FATAL] bukan sequence ADL ber-lying di dataset ini: {sorted(unknown)}\n"
                 f"        yang ada: {sorted(known_adl_lying)}")

    # subsampling transitional (train saja), deterministik
    rng = random.Random(a.seed)
    skip_stems = set()
    if a.keep_transitional and a.transitional_keep_frac < 1.0:
        cand = sorted(r["stem"] for r in rows if r["split"] == "train" and r["cls"] == "1")
        n_keep = round(len(cand) * a.transitional_keep_frac)
        skip_stems = set(cand) - set(rng.sample(cand, n_keep))

    if out.exists() and any(out.iterdir()):
        if not a.force:
            sys.exit(f"[FATAL] {out} tidak kosong. Pakai --force atau folder baru.")
        shutil.rmtree(out)
    for sp in SPLITS:
        (out / "images" / sp).mkdir(parents=True)
        (out / "labels" / sp).mkdir(parents=True)

    adl_n, adl_d = set(a.adl_lying_normal), set(a.adl_lying_drop)
    table = defaultdict(int)  # (group, split, cls)
    dropped = defaultdict(int)
    for r in rows:
        nc = new_class(r, adl_n, adl_d, a.keep_transitional)
        if nc is None:
            dropped["transitional" if r["cls"] == "1" else "lying ADL dibuang"] += 1
            continue
        if r["stem"] in skip_stems:
            dropped["transitional (disubsampel di train)"] += 1
            continue
        sp, stem = r["split"], r["stem"]
        li, ll = src / "images" / sp / f"{stem}.jpg", src / "labels" / sp / f"{stem}.txt"
        if not li.is_file() or not ll.is_file():
            sys.exit(f"[FATAL] berkas hilang untuk {stem}")
        parts = ll.read_text().strip().split()
        (out / "labels" / sp / f"{stem}.txt").write_text(" ".join([str(nc)] + parts[1:5]) + "\n")
        dst = out / "images" / sp / f"{stem}.jpg"
        try:
            os.link(li, dst)
        except OSError:
            shutil.copy2(li, dst)
        table[(r["group"], sp, nc)] += 1

    (out / "data.yaml").write_text(yaml.safe_dump({
        "train": "images/train", "val": "images/val", "test": "images/test",
        "nc": ncls, "names": names}, sort_keys=False), encoding="utf-8")
    (out / "dataset_manifest.json").write_text(json.dumps({
        "from": str(src), "classes": names, "keep_transitional": a.keep_transitional,
        "transitional_keep_frac": a.transitional_keep_frac, "seed": a.seed,
        "adl_lying_normal": a.adl_lying_normal, "adl_lying_drop": a.adl_lying_drop,
        "dropped": dict(dropped),
        "counts": {f"{g}/{sp}/{names[c]}": n for (g, sp, c), n in sorted(table.items())}},
        indent=2), encoding="utf-8")

    lying_id = ncls - 1
    hdr = f"{'sumber':<13}{'split':<7}" + "".join(f"{names[c]:>17}" for c in range(ncls))
    print(hdr)
    tot = defaultdict(int)
    for g in GROUPS:
        for sp in SPLITS:
            line = f"{g:<13}{sp:<7}"
            for c in range(ncls):
                n = table.get((g, sp, c), 0)
                tot[(sp, c)] += n
                line += f"{n:>17}"
            print(line)
    print("-" * len(hdr))
    for sp in SPLITS:
        counts = [tot[(sp, c)] for c in range(ncls)]
        print(f"{'TOTAL':<13}{sp:<7}" + "".join(f"{n:>17}" for n in counts)
              + f"   lying = {100 * counts[lying_id] / max(1, sum(counts)):.0f}%")
    print("Dibuang:", dict(dropped))
    for sp in SPLITS:
        for c in range(ncls):
            if tot[(sp, c)] == 0:
                print(f"[WARN] split {sp} kehilangan kelas {names[c]}")
    if a.zip:
        zp = out.with_suffix(".zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
            for f in out.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(out).as_posix())
        print(f"ZIP: {zp}  ({zp.stat().st_size / 1e6:.0f} MB)")
    print(f"Dataset training final: {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
audit_dataset.py  ->  ml/scripts/audit_dataset.py
=================================================
Audit READ-ONLY untuk dataset YOLO gabungan (ml/data/processed_v2) SEBELUM training.
Tidak mengubah gambar/label. Menulis satu file: <dataset>/frames_meta.csv.

Yang dijawab (minimal, tiap poin menentukan keputusan prep):
  1. Kelas x sumber (urfall-fall / urfall-adl / mcf) x split: jumlah frame + jumlah
     video/skenario  -> apakah ada kelas yang hanya hidup di satu domain
     (risiko "shortcut" domain), dan seberapa dominan transitional.
  2. Semantik label lintas dataset: frame 'lying' dari ADL UR Fall (orang
     berbaring di sofa/kasur?) vs kode 8 MCF (sofa = normal).
  3. Komposisi normal MCF per kode (kode 8 / duduk / jongkok = hard negative).
  4. Posisi frame transitional di dalam segmennya (awal/tengah/akhir) ->
     apakah perlu dipangkas.
  5. Kebocoran: satu video/skenario tidak boleh muncul di dua split.
  6. Ukuran & rasio kotak per kelas x sumber (pembeda domain/skala).
  7. Durasi segmen lying per video: apakah aturan alarm 10 detik bisa diuji.
Opsional --sheet-*: tulis satu gambar kontak (contact sheet) berisi frame dari
satu sumber/kelas untuk dicek dengan mata (mis. frame lying dari ADL UR Fall).

Contoh (dari root repo):
  py ml/scripts/audit_dataset.py --dataset ml/data/processed_v2
  # gambar kontak frame lying dari sequence ADL tertentu
  py ml/scripts/audit_dataset.py --dataset ml/data/processed_v2 \
      --sheet-group urfall-adl --sheet-cls 2 --sheet-videos adl-10 adl-11 adl-30
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics as stt
import sys
from collections import defaultdict
from pathlib import Path

NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}
SPLITS = ("train", "val", "test")
GROUPS = ("urfall-fall", "urfall-adl", "mcf")


def load_ann(path: Path):
    ann = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d = ann.setdefault(int(r["scenario"]), {"ref": int(r["ref_cam"]), "segs": []})
            d["segs"].append((int(r["start"]), int(r["end"]), int(r["code"])))
    return ann


def load_delays(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {int(r["scenario"]): [int(r[f"cam{c}"]) for c in range(1, 9)]
                for r in csv.DictReader(f)}


def parse_stem(stem: str):
    m = re.match(r"mcf_s(\d+)_c(\d)_f(\d+)$", stem)
    if m:
        s, c, fr = map(int, m.groups())
        return {"group": "mcf", "video": f"s{s:02d}", "cam": c, "frame": fr, "scen": s}
    m = re.match(r"urfall_((fall|adl)-\d+)_f(\d+)$", stem)
    if m:
        return {"group": f"urfall-{m.group(2)}", "video": m.group(1), "cam": 0,
                "frame": int(m.group(3)), "scen": None}
    return None


def mcf_code_pos(meta, ann, dl):
    s = meta["scen"]
    if s not in ann or s not in dl:
        return None, None
    f_ref = meta["frame"] - dl[s][meta["cam"] - 1] + dl[s][ann[s]["ref"] - 1]
    for st, en, code in ann[s]["segs"]:
        if st <= f_ref <= en:
            return code, (f_ref - st) / max(1, en - st)
    return None, None


def third(p):
    return "awal" if p < 1 / 3 else "tengah" if p < 2 / 3 else "akhir"


def main(argv=None):
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="Audit dataset YOLO sebelum training")
    ap.add_argument("--dataset", required=True, type=Path)
    ap.add_argument("--annotations", type=Path, default=here / "data/mcf/annotations.csv")
    ap.add_argument("--delays", type=Path, default=here / "data/mcf/frame_delay.csv")
    ap.add_argument("--fps", type=float, default=30.0,
                    help="ASUMSI fps untuk menerjemahkan frame ke detik (belum diverifikasi)")
    ap.add_argument("--sheet-group", choices=("urfall-fall", "urfall-adl", "mcf"))
    ap.add_argument("--sheet-cls", type=int, default=2)
    ap.add_argument("--sheet-code", type=int, default=None, help="hanya MCF: kode anotasi")
    ap.add_argument("--sheet-videos", nargs="*", default=None)
    ap.add_argument("--sheet-per-video", type=int, default=4)
    a = ap.parse_args(argv)

    ds = a.dataset.resolve()
    ann = load_ann(a.annotations) if a.annotations.is_file() else {}
    dl = load_delays(a.delays) if a.delays.is_file() else {}
    if not ann or not dl:
        print("[WARN] annotations.csv / frame_delay.csv tidak ditemukan: kode MCF tidak bisa dipetakan")

    rows, bad = [], 0
    for sp in SPLITS:
        for lf in sorted((ds / "labels" / sp).glob("*.txt")):
            meta = parse_stem(lf.stem)
            line = lf.read_text().strip().splitlines()
            if meta is None or not line:
                bad += 1
                continue
            p = line[0].split()
            meta.update(split=sp, stem=lf.stem, cls=int(p[0]), w=float(p[3]), h=float(p[4]),
                        code=None, pos=None)
            if meta["group"] == "mcf":
                meta["code"], meta["pos"] = mcf_code_pos(meta, ann, dl)
            rows.append(meta)
    if not rows:
        sys.exit(f"[FATAL] tidak ada label terbaca di {ds}")

    # posisi transitional untuk UR Fall: run frame berurutan per sequence
    ur = defaultdict(list)
    for r in rows:
        if r["group"].startswith("urfall") and r["cls"] == 1:
            ur[(r["split"], r["video"])].append(r)
    for lst in ur.values():
        lst.sort(key=lambda r: r["frame"])
        runs, cur = [], [lst[0]]
        for r in lst[1:]:
            if r["frame"] - cur[-1]["frame"] > 10:
                runs.append(cur)
                cur = []
            cur.append(r)
        runs.append(cur)
        for run in runs:
            n = len(run)
            for i, r in enumerate(run):
                r["pos"] = i / max(1, n - 1)

    # ---- 1. kelas x grup x split
    print("\n=== 1. FRAME (video/skenario) per kelas x sumber x split ===")
    print(f"{'sumber':<13}{'split':<7}" + "".join(f"{NAMES[c]:>22}" for c in (0, 1, 2)))
    tot = defaultdict(int)
    for g in GROUPS:
        for sp in SPLITS:
            line = f"{g:<13}{sp:<7}"
            for c in (0, 1, 2):
                sel = [r for r in rows if r["group"] == g and r["split"] == sp and r["cls"] == c]
                vids = len({r["video"] for r in sel})
                tot[(sp, c)] += len(sel)
                tot[("all", c)] += len(sel)
                tot[(g, c)] += len(sel)
                line += f"{len(sel):>15} ({vids:>3})"
            print(line)
    print("-" * 87)
    for sp in SPLITS:
        print(f"{'TOTAL':<13}{sp:<7}" + "".join(f"{tot[(sp, c)]:>22}" for c in (0, 1, 2)))
    print("\nPorsi sumber di tiap kelas (seluruh split):")
    for c in (0, 1, 2):
        n = tot[("all", c)] or 1
        print(f"  {NAMES[c]:<16}" + "  ".join(f"{g}={100 * tot[(g, c)] / n:4.0f}%" for g in GROUPS))
    print("Porsi kelas (train saja): " + "  ".join(
        f"{NAMES[c]}={100 * tot[('train', c)] / max(1, sum(tot[('train', k)] for k in (0, 1, 2))):.0f}%"
        for c in (0, 1, 2)))

    # ---- 2. lying dari ADL UR Fall
    print("\n=== 2. Frame 'lying' dari sequence ADL UR Fall (orang BUKAN jatuh) ===")
    adl = defaultdict(int)
    for r in rows:
        if r["group"] == "urfall-adl" and r["cls"] == 2:
            adl[r["video"]] += 1
    if adl:
        print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(adl.items())))
        print("  -> bandingkan secara VISUAL dengan keputusan 'kode 8 MCF (sofa) = normal'.")
    else:
        print("  tidak ada (bagus: tidak ada kontradiksi dengan keputusan kode 8)")

    # ---- 3. normal MCF per kode
    print("\n=== 3. Frame NORMAL MCF per kode anotasi (per split) ===")
    cnt = defaultdict(int)
    for r in rows:
        if r["group"] == "mcf" and r["cls"] == 0:
            cnt[(r["code"], r["split"])] += 1
    for code in sorted({k[0] for k in cnt}, key=lambda x: (x is None, x)):
        print(f"  kode {code}: " + "  ".join(f"{sp}={cnt[(code, sp)]}" for sp in SPLITS))
    print("  (kode 8 = berbaring di sofa; kode 4-7,9 = jongkok/duduk dll. = hard negative)")

    # ---- 4. transitional awal/tengah/akhir
    print("\n=== 4. Posisi frame TRANSITIONAL dalam segmennya ===")
    for g in GROUPS:
        sel = [r for r in rows if r["group"] == g and r["cls"] == 1 and r["pos"] is not None]
        if sel:
            c3 = {k: sum(third(r["pos"]) == k for r in sel) for k in ("awal", "tengah", "akhir")}
            n = len(sel)
            print(f"  {g:<12} n={n:<5} " + "  ".join(f"{k}={100 * v / n:.0f}%" for k, v in c3.items()))
    print("  (dari uji visual kami: 'awal' = masih berdiri, 'akhir' = sudah di lantai)")

    # ---- 5. kebocoran
    print("\n=== 5. Kebocoran antar-split (video/skenario di >1 split) ===")
    where = defaultdict(set)
    for r in rows:
        where[(r["group"].split("-")[0], r["video"])].add(r["split"])
    leaks = [(k, v) for k, v in where.items() if len(v) > 1]
    print("  BOCOR: " + str(leaks) if leaks else "  tidak ada (aman)")

    # ---- 6. kotak
    print("\n=== 6. Kotak (median lebar, tinggi, rasio w/h) per kelas x sumber ===")
    for c in (0, 1, 2):
        for g in GROUPS:
            sel = [r for r in rows if r["group"] == g and r["cls"] == c]
            if sel:
                w, h = stt.median(r["w"] for r in sel), stt.median(r["h"] for r in sel)
                print(f"  {NAMES[c]:<16}{g:<13} w={w:.2f} h={h:.2f} w/h={w / h:.2f}  n={len(sel)}")

    # ---- 7. durasi lying
    print(f"\n=== 7. Durasi segmen LYING per video (fps diasumsikan {a.fps:g}) ===")
    durs = {"mcf": [], "urfall-fall": [], "urfall-adl": []}
    for sc, d in ann.items():
        tot_ = sum(en - st + 1 for st, en, code in d["segs"] if code == 3)
        if tot_:
            durs["mcf"].append((f"s{sc:02d}", tot_))
    byv = defaultdict(list)
    for r in rows:
        if r["group"].startswith("urfall") and r["cls"] == 2:
            byv[(r["group"], r["video"])].append(r["frame"])
    for (g, v), fr in byv.items():
        durs[g].append((v, max(fr) - min(fr) + 1))
    for g, lst in durs.items():
        if not lst:
            continue
        fs = sorted(x[1] for x in lst)
        med = fs[len(fs) // 2]
        n10 = sum(f / a.fps >= 10 for f in fs)
        print(f"  {g:<12} video={len(fs):<3} frame min/median/max = {fs[0]}/{med}/{fs[-1]}"
              f"  = {fs[0] / a.fps:.1f}/{med / a.fps:.1f}/{fs[-1] / a.fps:.1f} detik"
              f"   video dengan lying >= 10 detik: {n10}/{len(fs)}")
    print("  (MCF: dari anotasi kode 3 pada kamera acuan; UR Fall: rentang frame lying yang tertahan)")

    # ---- gambar kontak (opsional)
    if a.sheet_group:
        import cv2
        import numpy as np
        sel = [r for r in rows if r["group"] == a.sheet_group and r["cls"] == a.sheet_cls
               and (a.sheet_code is None or r["code"] == a.sheet_code)
               and (not a.sheet_videos or r["video"] in a.sheet_videos)]
        pervid = defaultdict(list)
        for r in sel:
            pervid[r["video"]].append(r)
        picks = []
        for v in sorted(pervid):
            lst = sorted(pervid[v], key=lambda r: r["frame"])
            k = min(a.sheet_per_video, len(lst))
            picks += [lst[int(i * (len(lst) - 1) / max(1, k - 1))] for i in range(k)]
        tiles = []
        for r in picks:
            img = cv2.imread(str(ds / "images" / r["split"] / (r["stem"] + ".jpg")))
            if img is None:
                continue
            hh, ww = img.shape[:2]
            _, xc, yc, bw, bh = map(float, (ds / "labels" / r["split"] / (r["stem"] + ".txt")
                                           ).read_text().split()[:5])
            cv2.rectangle(img, (int((xc - bw / 2) * ww), int((yc - bh / 2) * hh)),
                          (int((xc + bw / 2) * ww), int((yc + bh / 2) * hh)), (0, 0, 230), 3)
            cv2.putText(img, f"{r['video']} f{r['frame']} {r['split']}", (6, 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
            tiles.append(cv2.resize(img, (400, 300)))
        if tiles:
            while len(tiles) % 4:
                tiles.append(np.zeros((300, 400, 3), np.uint8))
            grid = np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)])
            sp = ds / f"sheet_{a.sheet_group}_c{a.sheet_cls}.jpg"
            cv2.imwrite(str(sp), grid)
            print(f"\nGambar kontak: {sp}  ({len(picks)} frame dari video: {sorted(pervid)})")
        else:
            print("\n[WARN] tidak ada frame yang cocok untuk gambar kontak")

    out = ds / "frames_meta.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["stem", "split", "group", "video", "cam", "frame", "cls", "code", "seg_pos", "w", "h"])
        for r in rows:
            wr.writerow([r["stem"], r["split"], r["group"], r["video"], r["cam"], r["frame"], r["cls"],
                         "" if r["code"] is None else r["code"],
                         "" if r["pos"] is None else f"{r['pos']:.3f}", f"{r['w']:.4f}", f"{r['h']:.4f}"])
    print(f"\nfile dilewati (nama/label tak dikenal): {bad}")
    print(f"Tabel per-frame: {out}")


if __name__ == "__main__":
    main()

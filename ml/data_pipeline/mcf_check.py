"""
mcf_check.py
============
Verifikasi dataset MCF (folder chute01..chute24) SEBELUM menulis pipeline preprocessing.

  python mcf_check.py inspect --root "D:/path/ke/folder/yang/memuat/chute01"
  python mcf_check.py sync    --root "D:/path/..." --scenario 1 --ref-cam 8 --out sync_s01.png
"""
import argparse
import re
import sys
from pathlib import Path

import cv2
import numpy as np

# Delay (frame) kamera 1..8 per skenario. Sumber: Figure 3 technical report (hal. 16),
# dengan erratum: skenario 5 kamera 5 = 18. Tabel ini ditranskripsi manual dari gambar PDF,
# jadi mode `inspect` di bawah juga berfungsi memeriksa kesalahan ketik.
DELAY = {
    1: [3, 3, 8, 4, 23, 6, 6, 0],
    2: [25, 40, 0, 16, 18, 33, 33, 6],
    3: [12, 16, 8, 16, 35, 20, 20, 0],
    4: [72, 79, 78, 0, 68, 82, 83, 56],
    5: [17, 24, 5, 11, 18, 26, 28, 0],
    6: [0, 100, 106, 90, 89, 103, 104, 89],
    7: [28, 14, 16, 0, 1, 17, 18, 20],
    8: [92, 79, 0, 81, 64, 81, 82, 56],
    9: [18, 9, 1, 19, 13, 11, 12, 0],
    10: [14, 15, 19, 33, 12, 17, 19, 0],
    11: [23, 4, 20, 14, 0, 6, 7, 12],
    12: [21, 6, 13, 8, 0, 3, 7, 0],
    13: [16, 33, 0, 7, 27, 27, 36, 13],
    14: [49, 36, 38, 0, 29, 29, 7, 14],
    15: [15, 19, 19, 15, 34, 40, 23, 0],
    16: [23, 29, 0, 2, 12, 9, 3, 3],
    17: [21, 26, 15, 0, 10, 0, 29, 18],
    18: [99, 105, 86, 0, 84, 108, 109, 77],
    19: [19, 27, 16, 19, 5, 29, 0, 20],
    20: [25, 9, 3, 10, 10, 4, 5, 0],
    21: [20, 30, 22, 3, 8, 33, 32, 0],
    22: [0, 46, 51, 41, 53, 46, 47, 34],
    23: [31, 52, 52, 45, 54, 60, 50, 0],
    24: [3, 36, 7, 0, 37, 10, 33, 1],
}
VIDEO_EXT = {".avi", ".mp4", ".mkv", ".mov"}


def find_scenario_dir(root: Path, s: int):
    name = f"chute{s:02d}"
    if root.name == name and root.is_dir():
        return root
    for p in root.rglob(name):
        if p.is_dir():
            return p
    return None


def camera_files(scn_dir: Path):
    """Petakan nomor kamera -> daftar file, dari angka TERAKHIR pada nama file."""
    vids = sorted(p for p in scn_dir.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    cams = {}
    for p in vids:
        nums = re.findall(r"\d+", p.stem)
        if nums:
            cams.setdefault(int(nums[-1]), []).append(p)
    return vids, cams


def probe(path: Path, exact: bool):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        sys.exit(f"[FATAL] Tidak bisa membuka video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if exact:  # hitung dengan membaca seluruh video (lambat, tapi pasti)
        n = 0
        while cap.grab():
            n += 1
    cap.release()
    return n, fps, w, h


def cmd_inspect(args):
    root = Path(args.root)
    scenarios = args.scenarios or list(range(1, 25))
    n_problem = 0
    for s in scenarios:
        d = find_scenario_dir(root, s)
        if d is None:
            print(f"[S{s:02d}] folder chute{s:02d} TIDAK ditemukan di bawah {root}")
            n_problem += 1
            continue
        vids, cams = camera_files(d)
        bad = [c for c in range(1, 9) if len(cams.get(c, [])) != 1]
        if bad:
            print(f"[S{s:02d}] {len(vids)} video; kamera bermasalah (0 atau >1 file): {bad}")
            print("        contoh nama file:", [v.name for v in vids][:10])
            n_problem += 1
            continue
        counts, fps_set, size_set = [], set(), set()
        for c in range(1, 9):
            n, fps, w, h = probe(cams[c][0], args.exact)
            counts.append(n)
            fps_set.add(round(fps, 2))
            size_set.add((w, h))
        m = min(counts)
        got = [n - m for n in counts]
        diff = [g - e for g, e in zip(got, DELAY[s])]
        ok = all(abs(x) <= 1 for x in diff)  # toleransi 1 frame (metadata container bisa meleset)
        n_problem += 0 if ok else 1
        print(f"[S{s:02d}] frames={counts} fps={sorted(fps_set)} size={sorted(size_set)}")
        print(f"        delay_hitung={got}")
        print(f"        delay_tabel ={DELAY[s]}  -> {'OK' if ok else 'BEDA ' + str(diff)}")
    print(f"\nSelesai. Skenario bermasalah: {n_problem} dari {len(scenarios)}")
    if n_problem:
        print("Jika BEDA: ulangi dengan --exact pada skenario itu sebelum menyimpulkan apa pun.")


def read_frames(path: Path, wanted):
    wanted = {i for i in wanted if i >= 0}
    out = {}
    if not wanted:
        return out
    cap = cv2.VideoCapture(str(path))
    last, i = max(wanted), 0
    while i <= last:
        ok, fr = cap.read()
        if not ok:
            break
        if i in wanted:
            out[i] = fr
        i += 1
    cap.release()
    return out


def cmd_sync(args):
    s, ref = args.scenario, args.ref_cam
    d = find_scenario_dir(Path(args.root), s)
    if d is None:
        sys.exit(f"[FATAL] chute{s:02d} tidak ditemukan di bawah {args.root}")
    _, cams = camera_files(d)
    sign = -1 if args.flip else 1
    D = DELAY[s]
    cw, ch = 240, 160
    header = np.zeros((24, cw * len(args.frames), 3), np.uint8)
    for j, f in enumerate(args.frames):
        cv2.putText(header, f"ref f{f}", (j * cw + 4, 17), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
    rows = [header]
    for c in range(1, 9):
        files = cams.get(c, [])
        if len(files) != 1:
            sys.exit(f"[FATAL] kamera {c}: ditemukan {len(files)} file (harus 1)")
        shift = sign * (D[c - 1] - D[ref - 1])
        report_frames = [f + shift for f in args.frames]
        got = read_frames(files[0], [rf - args.base for rf in report_frames])
        cells = []
        for rf in report_frames:
            fr = got.get(rf - args.base)
            cell = np.zeros((ch, cw, 3), np.uint8) if fr is None else cv2.resize(fr, (cw, ch))
            cv2.putText(cell, f"cam{c} f{rf}", (4, 16), cv2.FONT_HERSHEY_SIMPLEX,
                        0.5, (0, 255, 255), 1, cv2.LINE_AA)
            cells.append(cell)
        rows.append(np.hstack(cells))
    cv2.imwrite(args.out, np.vstack(rows))
    print(f"Tersimpan: {args.out}  (rumus: {'FLIP' if args.flip else 'f_ref + delay_c - delay_ref'})")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("inspect")
    a.add_argument("--root", required=True)
    a.add_argument("--scenarios", type=int, nargs="*")
    a.add_argument("--exact", action="store_true")
    a.set_defaults(fn=cmd_inspect)
    b = sub.add_parser("sync")
    b.add_argument("--root", required=True)
    b.add_argument("--scenario", type=int, default=1)
    b.add_argument("--ref-cam", type=int, default=8)   # skenario 1: acuan 11 -> 8 (erratum)
    b.add_argument("--frames", type=int, nargs="+", default=[1060, 1080, 1095, 1108, 1120])
    b.add_argument("--base", type=int, default=1, choices=[0, 1])  # nomor frame laporan mulai 0 atau 1?
    b.add_argument("--flip", action="store_true")      # uji tanda rumus yang dibalik
    b.add_argument("--out", default="sync_check.png")
    b.set_defaults(fn=cmd_sync)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
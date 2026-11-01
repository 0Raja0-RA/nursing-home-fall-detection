"""
extract_mcf_tables.py
Ekstrak tabel anotasi (hal. 17-22) dan tabel delay (hal. 16) dari technical report MCF,
terapkan erratum (Nov 2025), validasi, lalu tulis CSV.

  python extract_mcf_tables.py --report technicalReport_dataset.pdf --out-dir ml/data/mcf
"""
import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

CODE_NAMES = {1: "walking_standing_up", 2: "falling", 3: "lying_on_ground", 4: "crouching",
              5: "moving_down", 6: "moving_up", 7: "sitting", 8: "lying_on_sofa", 9: "moving_horizontally"}

# --- Erratum (Nov 28, 2025) ---
CAMERA_REF_FIX = {11: 8, 10: 7}                      # kamera 10 & 11 tidak ada; hanya 8 kamera
DELAY_FIX = {(5, 5): 18}                             # skenario 5, kamera 5: "18 7" -> 18
SEGMENT_FIX = {                                      # skenario -> (start, end) baru, urut baris tabel
    2: [(308, 394), (395, 425), (426, 600)],
    7: [(330, 490), (491, 520), (521, 680)],
    8: [(144, 350), (351, 380), (381, 520)],
    14: [(372, 590), (591, 620), (621, 929), (930, 969), (970, 1019), (1020, 1060), (1061, 1115)],
    18: [(301, 480), (481, 520), (521, 655), (656, 684), (685, 710), (711, 740)],
}


def pdftext(pdf, first, last):
    r = subprocess.run(["pdftotext", "-layout", "-f", str(first), "-l", str(last), pdf, "-"],
                       capture_output=True, text=True, check=True)
    return r.stdout


def parse_annotations(text):
    segs, scn, ref = [], None, None
    for line in text.splitlines():
        nums = re.findall(r"-?\d+", line)
        if "scenario" in line:
            continue
        if len(nums) == 5:          # baris pertama blok: skenario, kamera_acuan, start, end, kode
            scn, ref = int(nums[0]), int(nums[1])
            segs.append([scn, ref, int(nums[2]), int(nums[3]), int(nums[4])])
        elif scn is not None and re.fullmatch(r"\s+\d+\s+\d+\s+\d+\s*", line):
            segs.append([scn, ref, int(nums[0]), int(nums[1]), int(nums[2])])
    return segs


def parse_delays(text):
    rows = {}
    for line in text.splitlines():
        nums = re.findall(r"\d+", line)
        # baris data: nomor skenario + 8 delay (kasus khusus "18 7" menghasilkan 10 angka)
        if len(nums) in (9, 10) and 1 <= int(nums[0]) <= 24:
            rows[int(nums[0])] = [int(x) for x in nums[1:]]
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    segs = parse_annotations(pdftext(a.report, 17, 22))
    delays = parse_delays(pdftext(a.report, 16, 16))

    # --- delay ---
    for s, row in delays.items():
        if len(row) == 9:                              # "18 7" -> ambil 18 (kamera 5), buang 7
            assert (s, 5) in DELAY_FIX and row[4] == 18 and row[5] == 7, (s, row)
            row.pop(5)
    for (s, c), v in DELAY_FIX.items():
        assert delays[s][c - 1] == v
    assert sorted(delays) == list(range(1, 25)) and all(len(r) == 8 for r in delays.values()), "tabel delay tidak lengkap"
    for s, r in delays.items():
        assert min(r) == 0, f"skenario {s}: min delay != 0 -> {r}"

    # --- erratum anotasi ---
    by_s = {}
    for s, ref, st, en, code in segs:
        by_s.setdefault(s, []).append([ref, st, en, code])
    assert sorted(by_s) == list(range(1, 25)), sorted(by_s)
    for s, new in SEGMENT_FIX.items():
        assert len(by_s[s]) >= len(new)
        for row, (st, en) in zip(by_s[s], new):
            row[1], row[2] = st, en
    # erratum menyebut 7 segmen untuk skenario 14 dan 6 untuk 18: pastikan jumlah baris sama
    for s, new in SEGMENT_FIX.items():
        assert len(by_s[s]) == len(new), (s, len(by_s[s]), len(new))

    # --- validasi: urut, tidak tumpang tindih, kode dikenal, acuan kamera 1..8 ---
    problems = []
    for s, rows in by_s.items():
        refs = {r[0] for r in rows}
        assert len(refs) == 1
        ref = CAMERA_REF_FIX.get(rows[0][0], rows[0][0])
        if not 1 <= ref <= 8:
            problems.append(f"S{s}: kamera acuan {ref} di luar 1..8")
        prev_end = None
        for _, st, en, code in rows:
            if code not in CODE_NAMES:
                problems.append(f"S{s}: kode {code} tak dikenal")
            if st > en:
                problems.append(f"S{s}: start>end ({st},{en})")
            if prev_end is not None and st != prev_end + 1:
                problems.append(f"S{s}: celah/tumpang tindih setelah {prev_end} -> {st}")
            prev_end = en

    with open(out / "annotations.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "ref_cam", "start", "end", "code", "code_name"])
        for s in sorted(by_s):
            ref = CAMERA_REF_FIX.get(by_s[s][0][0], by_s[s][0][0])
            for _, st, en, code in by_s[s]:
                w.writerow([s, ref, st, en, code, CODE_NAMES[code]])
    with open(out / "frame_delay.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["scenario"] + [f"cam{c}" for c in range(1, 9)])
        for s in sorted(delays):
            w.writerow([s] + delays[s])

    n_rows = sum(len(v) for v in by_s.values())
    print(f"annotations.csv: {n_rows} segmen, {len(by_s)} skenario | frame_delay.csv: {len(delays)} skenario")
    print("MASALAH VALIDASI:" if problems else "Validasi struktur: tidak ada masalah.")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

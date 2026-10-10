#!/usr/bin/env python3
"""
list_misses.py  ->  ml/scripts/list_misses.py
=============================================
Analisis kesalahan (langkah 1, tanpa GPU): salin frame lying yang MELESET (skor rendah) dari video
tertentu ke satu folder supaya bisa dilihat dengan mata, plus beberapa frame lying yang BERHASIL
sebagai pembanding. Nama file diawali skor -> mudah diurutkan di File Explorer.

Contoh (PowerShell, dari akar repo):
  python ml/scripts/list_misses.py --scores "C:\\path\\eval_3cls.scores.csv" ^
      --dataset ml/data/processed_v2_3cls --videos mcf-s19 mcf-s22 --out diag/misses

Keluaran: <out>/<video>/miss_<skor>_<stem>.jpg dan hit_<skor>_<stem>.jpg, serta ringkasan di layar.
Tidak mengubah apa pun selain membuat folder <out>.
"""
import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd


def pick_even(df, n):
    """Ambil n baris tersebar merata menurut urutan stem (supaya tidak hanya 1 momen)."""
    df = df.sort_values("stem")
    if len(df) <= n:
        return df
    idx = [round(i * (len(df) - 1) / (n - 1)) for i in range(n)]
    return df.iloc[idx]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True, type=Path, help="eval_3cls.scores.csv (kolom stem,gt,video,score)")
    ap.add_argument("--dataset", required=True, type=Path, help="folder processed_v2_3cls (berisi images/test)")
    ap.add_argument("--videos", nargs="+", default=["mcf-s19", "mcf-s22"])
    ap.add_argument("--thr", type=float, default=0.1, help="skor < thr dianggap meleset")
    ap.add_argument("--n-miss", type=int, default=20, help="jumlah frame meleset per video")
    ap.add_argument("--n-hit", type=int, default=8, help="jumlah frame berhasil (skor>=0.5) per video")
    ap.add_argument("--split", default="test")
    ap.add_argument("--out", type=Path, default=Path("diag/misses"))
    a = ap.parse_args(argv)

    d = pd.read_csv(a.scores)
    print("kolom:", list(d.columns), "| baris:", len(d), "| gt:", d["gt"].value_counts().to_dict())
    L = d[d["gt"] == 2]
    if L.empty:
        sys.exit("[FATAL] tidak ada baris gt==2 (lying). Pastikan --scores adalah file yang benar.")
    img_dir = a.dataset / "images" / a.split
    if not img_dir.is_dir():
        sys.exit(f"[FATAL] folder gambar tidak ada: {img_dir}")
    for v in a.videos:
        x = L[L["video"] == v]
        miss, hit = x[x["score"] < a.thr], x[x["score"] >= 0.5]
        print(f"\n{v}: lying={len(x)} | meleset(skor<{a.thr})={len(miss)} | berhasil(>=0.5)={len(hit)}")
        out = a.out / v
        out.mkdir(parents=True, exist_ok=True)
        for tag, sub, n in (("miss", miss, a.n_miss), ("hit", hit, a.n_hit)):
            for _, r in pick_even(sub, n).iterrows():
                src = img_dir / f"{r['stem']}.jpg"
                if src.is_file():
                    shutil.copy(src, out / f"{tag}_{r['score']:.2f}_{r['stem']}.jpg")
                else:
                    print("  [lewati] tidak ada:", src)
        print("  ->", out.resolve())


if __name__ == "__main__":
    main()

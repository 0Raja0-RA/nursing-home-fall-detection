"""Tahap 2 (CPU, cepat): validasi silang per VIDEO/SKENARIO untuk aturan sudut pose.

Masukan: CSV fitur dari pose_extract_features.py (semua frame train+val+test).
Prosedur:
  1. Video (UR Fall: satu video; MCF: satu skenario beserta 8 kameranya) dibagi ke K lipatan, dengan strata
     "video berisi lying" dan "video tanpa lying" agar tiap lipatan memuat keduanya.
  2. Untuk tiap lipatan: pilih (conf, fall_angle, aspect_ratio) pada K-1 lipatan lain, lalu nilai pada lipatan yang ditahan.
     Pemilihan: recall lying tertinggi dengan syarat tingkat alarm palsu pada frame NORMAL (FPR) <= --alpha.
  3. Prediksi dari semua lipatan yang ditahan (out-of-fold) digabung, lalu dilaporkan dengan definisi evaluasi Laila
     (lying vs normal; transitional hanya diagnostik) dan interval kepercayaan bootstrap per VIDEO.
Mode --group-by camera: hanya MCF, lipatan = kelompok kamera, untuk menguji generalisasi sudut pandang.

Contoh:
  python ml/archive/scripts/pose_grouped_cv.py --features ml/outputs/pose_classifier_cv/pose_features_yolo11n-pose_640.csv
  python ml/archive/scripts/pose_grouped_cv.py --features <csv> --k 5 --alpha 0.05
  python ml/archive/scripts/pose_grouped_cv.py --features <csv> --group-by camera --k 4
"""
import argparse
import json
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_classifier_cv"
CONFS = [0.05, 0.10, 0.15, 0.25]
FALL_ANGLES = [10, 15, 20, 25, 30, 35, 40, 45, 50, 60]
AR_THRS = [1.00, 1.15, 1.25, 1.40, 99.0]       # 99 = aspect ratio tidak dipakai

ap = argparse.ArgumentParser()
ap.add_argument("--features", required=True, type=Path)
ap.add_argument("--k", type=int, default=5)
ap.add_argument("--alpha", type=float, default=0.05, help="batas FPR pada frame normal saat memilih parameter")
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--boot", type=int, default=500)
ap.add_argument("--group-by", choices=["video", "camera"], default="video")
ap.add_argument("--tag", default=None)
a = ap.parse_args()

df = pd.read_csv(a.features)
if a.group_by == "camera":
    df = df[df.source == "mcf"].reset_index(drop=True)
    df["group"] = df["camera"]
else:
    df["group"] = df["video"]
# sudut efektif: bila sendi tidak terbaca, tebak dari bentuk kotak (sama dengan EXP-009)
fallback = np.where(df["ar"] < 0.8, 90.0, np.where(df["ar"] > 1.3, 20.0, 50.0))
df["angle_eff"] = np.where(df["joints_ok"] == 1, df["angle"], fallback)
gt = df["gt"].values
top_conf, ang, arr = df["top_conf"].values, df["angle_eff"].values, df["ar"].values
is_l, is_n, is_t = gt == 2, gt == 0, gt == 1
print(f"{len(df)} frame | {df.group.nunique()} kelompok | lying {is_l.sum()} normal {is_n.sum()} transitional {is_t.sum()} | "
      f"mode {a.group_by} | K={a.k} | alpha={a.alpha}")


def predict(conf, fa, ar_thr, idx=None):
    det = top_conf >= conf
    ang_ = np.where(det, ang, 90.0)
    ar_ = np.where(det, arr, 0.5)
    p = (ang_ < fa) | ((ar_ > ar_thr) & (ang_ < fa + 12))
    return p if idx is None else p[idx]


GRID = list(product(CONFS, FALL_ANGLES, AR_THRS))
PRED = {g: predict(*g) for g in GRID}          # prediksi tiap kombinasi untuk seluruh frame (tabel kecil)


def rates(p, mask):
    l, n = mask & is_l, mask & is_n
    rec = p[l].mean() if l.any() else np.nan
    fpr = p[n].mean() if n.any() else np.nan
    return rec, fpr


def select(train_mask, alpha):
    best, best_key = None, None
    for g in GRID:
        rec, fpr = rates(PRED[g], train_mask)
        if np.isnan(rec) or np.isnan(fpr):
            continue
        key = (fpr <= alpha, rec if fpr <= alpha else -fpr, -fpr)
        if best_key is None or key > best_key:
            best, best_key = g, key
    return best


# ---- lipatan per video, bertingkat: video berisi lying vs tidak ----
rng = np.random.default_rng(a.seed)
has_l = df.groupby("group")["gt"].apply(lambda s: (s == 2).any())
fold_of = {}
for flag in (True, False):
    vids = sorted(has_l[has_l == flag].index)
    rng.shuffle(vids)
    for i, v in enumerate(vids):
        fold_of[v] = i % a.k
df["fold"] = df["group"].map(fold_of)
print("video berisi lying per lipatan:", {f: int(sum(1 for v, ff in fold_of.items() if ff == f and has_l[v])) for f in range(a.k)})

oof = np.zeros(len(df), bool)
fold_rows = []
for f in range(a.k):
    te, tr = (df.fold == f).values, (df.fold != f).values
    g = select(tr, a.alpha)
    p = PRED[g]
    oof[te] = p[te]
    r_tr, f_tr = rates(p, tr)
    r_te, f_te = rates(p, te)
    fold_rows.append(dict(fold=f, conf=g[0], fall_angle=g[1], ar=g[2], rec_train=r_tr, fpr_train=f_tr, rec_heldout=r_te, fpr_heldout=f_te,
                          n_lying_heldout=int((te & is_l).sum()), n_videos_heldout=int(df[te].group.nunique())))
folds = pd.DataFrame(fold_rows)

# ---- ringkasan out-of-fold ----
videos = df["group"].values
by_vid = {v: np.where(videos == v)[0] for v in np.unique(videos)}
vid_list = sorted(by_vid)


def summary(p, mask):
    l, n, t = mask & is_l, mask & is_n, mask & is_t
    tp, fp = int((p & l).sum()), int((p & n).sum())
    return dict(recall=tp / max(1, l.sum()), precision=tp / max(1, tp + fp), fpr_normal=fp / max(1, n.sum()),
                trans_as_lying=float(p[t].mean()) if t.any() else np.nan, tp=tp, fp_normal=fp,
                n_lying=int(l.sum()), n_normal=int(n.sum()))


def boot_ci(p, mask, key):
    r = np.random.default_rng(a.seed + 1)
    vals = []
    for _ in range(a.boot):
        pick = r.choice(len(vid_list), size=len(vid_list), replace=True)
        idx = np.concatenate([by_vid[vid_list[k]] for k in pick])
        l, n = is_l[idx], is_n[idx]
        tp, fp = (p[idx] & l).sum(), (p[idx] & n).sum()
        if key == "recall" and l.sum():
            vals.append(tp / l.sum())
        elif key == "precision" and tp + fp:
            vals.append(tp / (tp + fp))
        elif key == "fpr_normal" and n.sum():
            vals.append(fp / n.sum())
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))] if vals else [np.nan, np.nan]


allm = np.ones(len(df), bool)
result = {"features": str(a.features), "group_by": a.group_by, "k": a.k, "alpha": a.alpha, "seed": a.seed,
          "folds": folds.to_dict(orient="records")}
groups = {"SEMUA": allm}
if a.group_by == "video":
    groups["urfall"] = (df.source == "urfall").values
    groups["mcf"] = (df.source == "mcf").values
for c in sorted(df[df.source == "mcf"].camera.unique()):
    groups["mcf_" + c] = ((df.source == "mcf") & (df.camera == c)).values

print("\n=== HASIL OUT-OF-FOLD (parameter dipilih tanpa melihat video yang diuji) ===")
print(f"{'kelompok':10s} {'lying':>6s} {'recall [CI95 per video]':>26s} {'precision':>10s} {'FPR normal':>11s} {'trans->lying':>13s}")
tab = {}
for name, m in groups.items():
    s = summary(oof, m)
    ci = boot_ci(oof, m, "recall") if name == "SEMUA" else [np.nan, np.nan]
    tab[name] = s
    ci_txt = f"[{ci[0]:.2f},{ci[1]:.2f}]" if not np.isnan(ci[0]) else ""
    print(f"{name:10s} {s['n_lying']:6d} {s['recall']:10.3f} {ci_txt:>15s} {s['precision']:10.3f} {s['fpr_normal']:11.3f} {s['trans_as_lying']:13.3f}")
result["oof"] = tab
result["oof_ci"] = {k: boot_ci(oof, allm, k) for k in ("recall", "precision", "fpr_normal")}
print("CI95 per video (SEMUA): recall %s | precision %s | FPR %s" % tuple(
    "[%.2f,%.2f]" % tuple(result["oof_ci"][k]) for k in ("recall", "precision", "fpr_normal")))

print("\n=== PARAMETER TERPILIH PER LIPATAN DAN KINERJA PADA VIDEO YANG DITAHAN ===")
print(folds.round(3).to_string(index=False))
print("\nKestabilan: nilai unik conf=%s, fall_angle=%s, ar=%s" % (sorted(folds.conf.unique()), sorted(folds.fall_angle.unique()), sorted(folds.ar.unique())))

# ---- pembanding: dalam-sampel (optimis) dan aturan lama tetap ----
g_all = select(allm, a.alpha)
result["in_sample_best"] = dict(params=list(g_all), **summary(PRED[g_all], allm))
old = (0.25, 20, 1.15)
result["fixed_old_rule"] = dict(params=list(old), **summary(PRED[old], allm))
print(f"\nPembanding SEMUA: aturan lama conf0,25 20/1,15 -> recall {result['fixed_old_rule']['recall']:.3f}, "
      f"precision {result['fixed_old_rule']['precision']:.3f}, FPR {result['fixed_old_rule']['fpr_normal']:.3f}")
print(f"                  terbaik dalam-sampel {g_all} -> recall {result['in_sample_best']['recall']:.3f}, "
      f"precision {result['in_sample_best']['precision']:.3f}, FPR {result['in_sample_best']['fpr_normal']:.3f} (optimis; bukan hasil resmi)")

tag = a.tag or f"{a.features.stem}_{a.group_by}_k{a.k}"
(OUT / f"pose_grouped_cv_{tag}.json").write_text(json.dumps(result, indent=1, default=float))
pd.DataFrame({"img": df["img"], "video": df["video"], "gt": gt, "fold": df["fold"], "pred_lying": oof}).to_csv(
    OUT / f"pose_grouped_cv_{tag}_oof.csv", index=False)
print("tersimpan:", OUT / f"pose_grouped_cv_{tag}.json")

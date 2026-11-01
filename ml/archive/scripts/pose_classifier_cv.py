"""Classifier berbasis keypoint untuk lying vs normal, dievaluasi dengan validasi silang per video/skenario (CPU).

Masukan: CSV fitur dari pose_extract_features.py (17 keypoint + kotak). Tidak menjalankan model pose lagi.
Latih pada frame lying vs normal (transitional tidak dipakai melatih; hanya dilaporkan sebagai diagnostik).
Ambang skor dipilih pada lipatan latih lewat validasi silang bagian dalam: recall tertinggi dengan FPR normal <= alpha.
Fitur sengaja TIDAK memuat id kamera atau sumber data, agar mode --group-by camera menguji generalisasi sudut pandang.

Contoh:
  python ml/archive/scripts/pose_classifier_cv.py --features ml/outputs/pose_classifier_cv/pose_features_yolo11n-pose_640.csv
  python ml/archive/scripts/pose_classifier_cv.py --features <csv> --model hgb --group-by camera --k 4
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

OUT = Path(__file__).resolve().parents[2] / "outputs" / "pose_classifier_cv"
ap = argparse.ArgumentParser()
ap.add_argument("--features", required=True, type=Path)
ap.add_argument("--model", choices=["lr", "hgb"], default="lr")
ap.add_argument("--k", type=int, default=5)
ap.add_argument("--alpha", type=float, default=0.05)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--boot", type=int, default=300)
ap.add_argument("--group-by", choices=["video", "camera"], default="video")
ap.add_argument("--min-conf", type=float, default=0.05)
a = ap.parse_args()

df = pd.read_csv(a.features)
if a.group_by == "camera":
    df = df[df["source"] == "mcf"].reset_index(drop=True)
df["group"] = df["camera"] if a.group_by == "camera" else df["video"]
ASPECT = np.where(df["source"] == "mcf", 720 / 480, 640 / 480)        # x/W -> satuan tinggi gambar (geometri sebenarnya)


def kp(j):
    x = df[f"k{j}x"].values * ASPECT
    y = df[f"k{j}y"].values
    c = df[f"k{j}c"].values
    return x, y, c


def mid(a_, b_):
    xa, ya, ca = kp(a_); xb, yb, cb = kp(b_)
    return (xa + xb) / 2, (ya + yb) / 2, np.minimum(ca, cb)


def feats():
    F = {}
    F["top_conf"] = df["top_conf"].values
    F["n_boxes"] = df["n_boxes"].values
    F["box_w"] = df["box_w"].values * ASPECT
    F["box_h"] = df["box_h"].values
    F["ar"] = df["ar"].values
    F["box_diag"] = np.hypot(F["box_w"], F["box_h"])
    C = np.stack([df[f"k{j}c"].values for j in range(17)], 1)
    F["kp_conf_mean"] = np.nanmean(C, 1)
    F["kp_n_vis"] = np.nansum(C > 0.3, 1)
    sx, sy, sc = mid(5, 6); hx, hy, hc = mid(11, 12)
    ax, ay, ac = mid(15, 16); nx, ny, nc = kp(0)
    dx, dy = np.abs(sx - hx), np.abs(sy - hy)
    ok = (sc > 0.25) & (hc > 0.25)
    tor = np.hypot(dx, dy)
    F["torso_dx"] = np.where(ok, dx / (F["box_diag"] + 1e-6), np.nan)
    F["torso_dy"] = np.where(ok, dy / (F["box_diag"] + 1e-6), np.nan)
    F["torso_len"] = np.where(ok, tor / (F["box_diag"] + 1e-6), np.nan)
    F["torso_cos"] = np.where(ok, dx / (tor + 1e-6), np.nan)           # 1 = mendatar, 0 = tegak
    F["torso_head_below"] = np.where(ok & (nc > 0.25), (ny - hy) / (F["box_h"] + 1e-6), np.nan)
    ok2 = (nc > 0.25) & (ac > 0.25)
    F["body_cos"] = np.where(ok2, np.abs(nx - ax) / (np.hypot(nx - ax, ny - ay) + 1e-6), np.nan)
    F["body_len"] = np.where(ok2, np.hypot(nx - ax, ny - ay) / (F["box_diag"] + 1e-6), np.nan)
    # sebaran semua keypoint terlihat
    X = np.stack([kp(j)[0] for j in range(17)], 1); Y = np.stack([kp(j)[1] for j in range(17)], 1)
    vis = C > 0.3
    nv = vis.sum(1)
    with np.errstate(all="ignore"):
        mx = np.where(vis, X, np.nan); my = np.where(vis, Y, np.nan)
        xs = np.nanmax(mx, 1) - np.nanmin(mx, 1); ys = np.nanmax(my, 1) - np.nanmin(my, 1)
        F["ext_ratio"] = np.where(nv >= 4, xs / (ys + 1e-6), np.nan)
        # sumbu utama (PCA) keypoint terlihat
        cx = mx - np.nanmean(mx, 1, keepdims=True); cy = my - np.nanmean(my, 1, keepdims=True)
        sxx = np.nanmean(cx * cx, 1); syy = np.nanmean(cy * cy, 1); sxy = np.nanmean(cx * cy, 1)
        lam1 = 0.5 * (sxx + syy + np.sqrt((sxx - syy) ** 2 + 4 * sxy ** 2))
        lam2 = 0.5 * (sxx + syy - np.sqrt((sxx - syy) ** 2 + 4 * sxy ** 2))
        theta = 0.5 * np.arctan2(2 * sxy, sxx - syy)
        F["pca_horizontality"] = np.where(nv >= 4, np.abs(np.cos(theta)), np.nan)
        F["pca_elongation"] = np.where(nv >= 4, lam1 / (lam2 + 1e-9), np.nan)
    return pd.DataFrame(F)


Xall = feats()
gt = df["gt"].values
is_l, is_n, is_t = gt == 2, gt == 0, gt == 1
trainable = is_l | is_n
print(f"{len(df)} frame | {df['group'].nunique()} kelompok | lying {is_l.sum()} normal {is_n.sum()} trans {is_t.sum()} | model {a.model} | {a.group_by} K={a.k} alpha={a.alpha}")
print("fitur:", list(Xall.columns))


def make_model():
    if a.model == "lr":
        return make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                             LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced"))
    return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200, class_weight="balanced",
                                          random_state=a.seed)


def fit_score(tr_idx, te_idx):
    m = make_model()
    tr = tr_idx[trainable[tr_idx]]
    m.fit(Xall.iloc[tr], (gt[tr] == 2).astype(int))
    return m.predict_proba(Xall.iloc[te_idx])[:, 1]


def choose_thr(scores, mask, alpha):
    """Ambang: recall tertinggi dengan FPR normal <= alpha."""
    l, n = mask & is_l, mask & is_n
    cand = np.unique(np.quantile(scores[n], np.linspace(0.5, 1.0, 400)))
    best, best_rec = cand[-1], -1
    for t in cand:
        fpr = (scores[n] >= t).mean()
        if fpr <= alpha:
            rec = (scores[l] >= t).mean()
            if rec > best_rec:
                best, best_rec = t, rec
    return best


def folds_of(groups, k, seed):
    rng = np.random.default_rng(seed)
    has_l = pd.Series(is_l).groupby(groups).any()
    out = {}
    for flag in (True, False):
        v = sorted(has_l[has_l == flag].index)
        rng.shuffle(v)
        for i, g in enumerate(v):
            out[g] = i % k
    return pd.Series(groups).map(out).values


groups = df["group"].values
fold = folds_of(groups, a.k, a.seed)
oof = np.full(len(df), np.nan)
thr_oof = np.zeros(len(df), bool)
rows = []
for f in range(a.k):
    te = np.where(fold == f)[0]
    tr = np.where(fold != f)[0]
    # validasi silang bagian dalam (per kelompok) untuk skor latih yang jujur -> pilih ambang
    inner = folds_of(groups[tr], 3, a.seed + 10 + f)
    inner_scores = np.full(len(tr), np.nan)
    for g in range(3):
        itr, ite = tr[inner != g], np.where(inner == g)[0]
        inner_scores[ite] = fit_score(itr, tr[ite])
    mask_tr = np.zeros(len(df), bool); mask_tr[tr] = True
    sc_full = np.full(len(df), np.nan); sc_full[tr] = inner_scores
    thr = choose_thr(sc_full, mask_tr, a.alpha)
    s_te = fit_score(tr, te)
    oof[te] = s_te
    thr_oof[te] = s_te >= thr
    l_te, n_te = is_l[te], is_n[te]
    rows.append(dict(fold=f, thr=round(float(thr), 3), rec_heldout=float((s_te[l_te] >= thr).mean()) if l_te.any() else np.nan,
                     fpr_heldout=float((s_te[n_te] >= thr).mean()) if n_te.any() else np.nan,
                     n_lying_heldout=int(l_te.sum()), n_videos_heldout=int(pd.Series(groups[te]).nunique())))
folds = pd.DataFrame(rows)

vid = {v: np.where(groups == v)[0] for v in np.unique(groups)}
vl = sorted(vid)


def summ(p, mask):
    l, n, t = mask & is_l, mask & is_n, mask & is_t
    tp, fp = int((p & l).sum()), int((p & n).sum())
    auc = np.nan
    if l.any() and n.any():
        auc = roc_auc_score(np.r_[np.ones(l.sum()), np.zeros(n.sum())], np.r_[oof[l], oof[n]])
    return dict(recall=tp / max(1, l.sum()), precision=tp / max(1, tp + fp), fpr_normal=fp / max(1, n.sum()),
                trans_as_lying=float(p[t].mean()) if t.any() else np.nan, auc=auc, n_lying=int(l.sum()))


def boot(p, key):
    r = np.random.default_rng(a.seed + 99)
    vals = []
    for _ in range(a.boot):
        idx = np.concatenate([vid[vl[i]] for i in r.choice(len(vl), len(vl))])
        l, n = is_l[idx], is_n[idx]
        tp, fp = (p[idx] & l).sum(), (p[idx] & n).sum()
        v = {"recall": tp / l.sum() if l.sum() else np.nan, "precision": tp / (tp + fp) if tp + fp else np.nan,
             "fpr_normal": fp / n.sum() if n.sum() else np.nan}[key]
        if not np.isnan(v):
            vals.append(v)
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


masks = {"SEMUA": np.ones(len(df), bool)}
if a.group_by == "video":
    masks["urfall"] = (df["source"] == "urfall").values
    masks["mcf"] = (df["source"] == "mcf").values
for c in sorted(df[df["source"] == "mcf"]["camera"].unique()):
    masks["mcf_" + c] = ((df["source"] == "mcf") & (df["camera"] == c)).values

print("\n=== HASIL OUT-OF-FOLD (model dan ambang dipilih tanpa melihat video yang diuji) ===")
print(f"{'kelompok':10s} {'lying':>6s} {'recall':>8s} {'precision':>10s} {'FPR normal':>11s} {'trans->lying':>13s} {'AUC':>6s}")
res = {}
for name, m in masks.items():
    s = summ(thr_oof, m); res[name] = s
    print(f"{name:10s} {s['n_lying']:6d} {s['recall']:8.3f} {s['precision']:10.3f} {s['fpr_normal']:11.3f} {s['trans_as_lying']:13.3f} {s['auc']:6.3f}")
ci = {k: boot(thr_oof, k) for k in ("recall", "precision", "fpr_normal")}
print("CI95 per video (SEMUA): recall [%.2f,%.2f] | precision [%.2f,%.2f] | FPR [%.2f,%.2f]" % (*ci["recall"], *ci["precision"], *ci["fpr_normal"]))
print("\n=== PER LIPATAN ===")
print(folds.round(3).to_string(index=False))

# kejadian: >= k frame lying berurutan terbaca lying (per video x kamera); alarm palsu pada urutan tanpa lying
fr = df["img"].str.extract(r"_f(\d+)\.jpg")[0].astype(int).values
seq = pd.DataFrame(dict(video=df["video"].values, cam=df["camera"].values, fr=fr, gt=gt, p=thr_oof, src=df["source"].values))


def run_len(x):
    b = c = 0
    for v in x:
        c = c + 1 if v else 0
        b = max(b, c)
    return b


ev = []
for (v, c), g in seq.sort_values("fr").groupby(["video", "cam"]):
    l, n = g[g["gt"] == 2], g[g["gt"] == 0]
    ev.append(dict(has_l=len(l) > 0, run_l=run_len(l["p"].values) if len(l) else 0, run_n=run_len(n["p"].values) if len(n) else 0, src=g["src"].iloc[0]))
ev = pd.DataFrame(ev); evl, evn = ev[ev["has_l"]], ev[~ev["has_l"]]
print(f"\n=== TINGKAT KEJADIAN (urutan video x kamera; berisi lying {len(evl)}, tanpa lying {len(evn)}) ===")
event = {}
for k in (1, 2, 3, 5):
    event[k] = dict(detected=float((evl["run_l"] >= k).mean()), false_alarm_noLying=float((evn["run_n"] >= k).mean()),
                    false_alarm_withLying=float((evl["run_n"] >= k).mean()))
    print(f"  >= {k} frame berurutan: kejadian terdeteksi {event[k]['detected']:.0%} | alarm palsu pada urutan tanpa lying {event[k]['false_alarm_noLying']:.0%}")
tag = f"{a.features.stem}_{a.model}_{a.group_by}_k{a.k}"
(OUT / f"pose_classifier_cv_{tag}.json").write_text(json.dumps(dict(oof=res, ci=ci, folds=folds.to_dict(orient="records"), event=event), indent=1, default=float))
pd.DataFrame(dict(img=df["img"], video=df["video"], gt=gt, fold=fold, score=oof, pred_lying=thr_oof)).to_csv(OUT / f"pose_classifier_cv_{tag}_oof.csv", index=False)
print("tersimpan:", OUT / f"pose_classifier_cv_{tag}.json")

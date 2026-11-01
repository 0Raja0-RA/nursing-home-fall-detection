"""Pecah kehilangan frame lying UR Fall: dedup pHash vs detektor COCO (yolo11n)."""
import re, random, json, collections
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO

NEW = Path(r"C:\Project_2026\Falling Detection\ml\data\processed_final")
OUT = Path(__file__).resolve().parents[2] / "outputs" / "bbox_on_new_data"
NAMES = {0: "normal", 1: "transitional", 2: "lying"}
THR = 6          # default --phash-threshold di prepare_urfall.py (dipakai untuk normal DAN lying)
random.seed(0)


def phash(g):
    r = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA)
    return (r[:, 1:] > r[:, :-1]).flatten()


frames = []   # (seq, frame_no, cls, path)
for sp in ("train", "val", "test"):
    for l in (NEW / "labels" / sp).glob("urfall_*.txt"):
        m = re.match(r"urfall_((?:fall|adl)-\d+)_f(\d+)", l.stem)
        cls = int(l.read_text().split()[0])
        frames.append((m.group(1), int(m.group(2)), cls, NEW / "images" / sp / (l.stem + ".jpg")))
frames.sort()
print("frame UR Fall data Laila:", collections.Counter(NAMES[c] for _, _, c, _ in frames))

# --- 1) simulasi dedup (aturan prepare_urfall.py: banding dengan frame TERAKHIR yang disimpan)
surv = collections.Counter(); tot = collections.Counter()
dists_lying = []
survivors = []
byseq = collections.defaultdict(list)
for f in frames:
    byseq[f[0]].append(f)
for seq, fl in byseq.items():
    last = None; prev_lying_hash = None
    for (_, fn, c, p) in fl:
        h = phash(cv2.imread(str(p), cv2.IMREAD_GRAYSCALE))
        tot[c] += 1
        if c == 2:
            if prev_lying_hash is not None:
                dists_lying.append(int((h != prev_lying_hash).sum()))
            prev_lying_hash = h
        keep = True
        if last is not None and c != 1 and int((h != last).sum()) <= THR:
            keep = False
        if keep:
            surv[c] += 1; last = h
            survivors.append((seq, fn, c, p))
print("\n[1] Simulasi dedup pHash (ambang %d) pada frame stride-5:" % THR)
for c in (0, 1, 2):
    print(f"   {NAMES[c]:12s} {tot[c]:5d} -> {surv[c]:5d}  (hilang {1 - surv[c]/tot[c]:.0%})")
d = np.array(dists_lying)
print(f"   jarak hamming antar frame lying berurutan: median={np.median(d):.0f}, <=6: {(d<=6).mean():.0%} (n={len(d)})")

# --- 2) detektor COCO yolo11n pada frame berlabel
det = YOLO(r"C:\Project_2026\Falling Detection\yolo11n.pt")


def detect_rate(paths):
    miss = 0; confs = []
    for i in range(0, len(paths), 32):
        for r in det([str(p) for p in paths[i:i+32]], conf=0.25, classes=[0], verbose=False):
            if len(r.boxes) == 0:
                miss += 1
            else:
                confs.append(float(r.boxes.conf.max()))
    return miss, confs


print("\n[2] Detektor yolo11n (conf 0.25, kelas person) - frame tanpa orang terdeteksi:")
res = {}
for c in (2, 0, 1):
    ps = [p for (_, _, cc, p) in frames if cc == c]
    if c != 2:
        ps = random.sample(ps, min(300, len(ps)))
    miss, confs = detect_rate(ps)
    res[c] = (len(ps), miss)
    print(f"   {NAMES[c]:12s} n={len(ps):4d}  tanpa deteksi={miss:4d} ({miss/len(ps):.0%})  conf median={np.median(confs):.2f}")

# --- 3) gabungan: lying yang lolos dedup DAN terdeteksi
lying_surv = [p for (_, _, c, p) in survivors if c == 2]
miss_s, _ = detect_rate(lying_surv)
print(f"\n[3] Lying lolos dedup: {len(lying_surv)}; dari itu terdeteksi detektor: {len(lying_surv) - miss_s}")
print("    (dataset lama kita hanya punya 12 lying)")

# --- 4) kehilangan detektor menurut sequence (di frame lying)
perseq = collections.defaultdict(lambda: [0, 0])
ps = [(s, p) for (s, _, c, p) in frames if c == 2]
for i in range(0, len(ps), 32):
    ch = ps[i:i+32]
    for (s, _), r in zip(ch, det([str(p) for _, p in ch], conf=0.25, classes=[0], verbose=False)):
        perseq[s][0] += 1; perseq[s][1] += int(len(r.boxes) == 0)
print("\n[4] Frame lying per sequence (n, tanpa deteksi):", {k: tuple(v) for k, v in sorted(perseq.items())})
json.dump({"surv": {NAMES[c]: [tot[c], surv[c]] for c in tot}, "det": {NAMES[c]: res[c] for c in res},
           "lying_after_dedup": len(lying_surv), "lying_after_dedup_and_det": len(lying_surv) - miss_s},
          open(OUT / "lying_loss_result.json", "w"), indent=1)

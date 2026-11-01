import re, random
from pathlib import Path
import cv2, numpy as np, pandas as pd

ROOT = Path(r"C:\Project_2026\Falling Detection")
NEW = ROOT / "ml" / "data" / "processed_final"
SP = Path(__file__).resolve().parents[2] / "outputs" / "pose_failure_sheets"
random.seed(3)


def tile(path, text, color=(0, 255, 255)):
    im = cv2.imread(str(path))
    im = cv2.resize(im, (360, 240))
    cv2.rectangle(im, (0, 0), (360, 26), (0, 0, 0), -1)
    cv2.putText(im, text, (6, 19), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1)
    return im


def sheet(tiles, cols, out):
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]
    cv2.imwrite(str(out), np.vstack(rows))


f9 = pd.read_csv(Path(__file__).resolve().parents[2] / "experiments" / "exp009_pose_tuning" / "exp009_laila_features.csv")
t = f9[(f9["split"] == "test") & (f9["gt"] == 2)].copy()
t["cam"] = t.img.str.extract(r"mcf_s\d+_(c\d+)_")[0]
miss = t[(t.detected == 0)]
print("lying test MCF tidak terdeteksi per kamera:", miss[miss.source == "mcf"].cam.value_counts().sort_index().to_dict())
tiles = []
for cam, g in miss[miss.source == "mcf"].groupby("cam"):
    for _, r in g.sample(min(3, len(g)), random_state=1).iterrows():
        tiles.append(tile(NEW / "images" / "test" / r.img, f"MISS {r.img[4:20]}", (0, 0, 255)))
sheet(tiles, 4, SP / "C_lying_missed.jpg")
print("tile missed:", len(tiles))

# kontras: lying yang TERDETEKSI per kamera dengan sudut
hit = t[(t.detected == 1) & (t.source == "mcf")]
tiles = []
for cam, g in hit.groupby("cam"):
    for _, r in g.sample(min(2, len(g)), random_state=1).iterrows():
        tiles.append(tile(NEW / "images" / "test" / r.img, f"HIT ang={r.angle:.0f} {r.img[8:20]}", (0, 255, 0)))
sheet(tiles, 4, SP / "C_lying_hit.jpg")
print("tile hit:", len(tiles))

# s23: frame ADL ber-sudut rendah (pose bilang rebah, label bilang normal/trans)
f10 = pd.read_csv(Path(__file__).resolve().parents[3] / "docs" / "internal" / "data" / "exp010_new_features.csv")
s23 = f10[(f10.split == "test") & f10.seq.str.startswith(("mcf_s23", "mcf_s24")) & (f10.kpt_ok == 1) & (f10.angle < 25)]
print("s23/s24 frame sudut<25:", len(s23), s23.groupby("seq").size().to_dict())
tiles = []
for _, r in s23.sample(min(12, len(s23)), random_state=2).iterrows():
    tiles.append(tile(NEW / "images" / "test" / r.img, f"{r.img[4:20]} gt={r["gt"]} ang={r.angle:.0f}", (0, 200, 255)))
sheet(tiles, 4, SP / "C_s23_lowangle.jpg")
# juga UR Fall adl-35 yang ditandai rebah di EXP-010
u = f10[(f10.split == "test") & (f10.seq == "urfall_adl-35") & (f10.kpt_ok == 1) & (f10.angle < 25)]
tiles = [tile(NEW / "images" / "test" / r.img, f"{r.img[7:22]} gt={r["gt"]} ang={r.angle:.0f}", (0, 200, 255)) for _, r in u.head(8).iterrows()]
if tiles:
    sheet(tiles, 4, SP / "C_adl35_lowangle.jpg")
print("adl-35 sudut<25:", len(u), u["gt"].value_counts().to_dict())

"""Membaca label YOLO dan mengambil sampel frame dari dataset."""

import collections
import re
from pathlib import Path

import numpy as np

CLASS_NAMES = {0: "normal", 1: "transitional", 2: "lying_on_ground"}


def get_ground_truth(label_file: Path) -> int | None:
    """Kelas pada baris pertama file label YOLO."""
    if not label_file.exists():
        return None
    lines = [ln.split() for ln in label_file.read_text().splitlines() if ln.strip()]
    return int(lines[0][0]) if lines else None


def read_box(label_path: Path, w: int, h: int):
    """Kelas dan bbox (xyxy piksel) baris pertama label YOLO."""
    lines = [ln.split() for ln in label_path.read_text().splitlines() if ln.strip()]
    if not lines:
        return None, None
    cls, xc, yc, bw, bh = int(lines[0][0]), *map(float, lines[0][1:5])
    return cls, np.array([(xc - bw / 2) * w, (yc - bh / 2) * h, (xc + bw / 2) * w, (yc + bh / 2) * h])


def camera_of(name: str) -> str:
    m = re.match(r"mcf_s\d+_(c\d+)", name)
    return m.group(1) if m else "urfall"


def sample_frames(img_dir: Path, lbl_dir: Path, per_class: int) -> tuple[list[Path], int]:
    """Semua frame lying + maksimal per_class frame normal/transitional. -> (frame, jumlah lying)"""
    by_class = collections.defaultdict(list)
    for f in sorted(img_dir.glob("*.jpg")):
        cls = get_ground_truth(lbl_dir / f"{f.stem}.txt")
        if cls is not None:
            by_class[cls].append(f)
    samples = list(by_class[2])
    for cls in (0, 1):
        files = by_class[cls]
        step = max(1, len(files) // per_class)
        samples += files[::step][:per_class]
    return samples, len(by_class[2])

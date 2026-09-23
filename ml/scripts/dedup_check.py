"""
dedup_check.py
==============
Cek dan hapus frame duplikat dari dataset yang sudah diekstrak.

Menggunakan perceptual hashing (pHash) untuk membandingkan
kemiripan antar gambar. Frame yang terlalu mirip (di bawah
threshold hamming distance) akan ditandai sebagai duplikat.

Usage:
    python dedup_check.py --dir ml/data/extracted_frames/ \
                          --threshold 10 \
                          --dry-run
"""

import argparse
import os
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np


def compute_phash(image_path: str, hash_size: int = 8) -> np.ndarray:
    """Hitung perceptual hash (pHash) dari gambar.

    Args:
        image_path: Path ke file gambar.
        hash_size: Ukuran hash (default 8 -> 64-bit hash).

    Returns:
        Array boolean yang merepresentasikan hash.
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Tidak dapat membaca: {image_path}")

    resized = cv2.resize(img, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def hamming_distance(hash1: np.ndarray, hash2: np.ndarray) -> int:
    """Hitung hamming distance antara dua hash."""
    return int(np.sum(hash1 != hash2))


def find_duplicates(
    directory: str, threshold: int = 10
) -> List[Tuple[str, str, int]]:
    """Cari pasangan gambar duplikat dalam direktori.

    Args:
        directory: Path ke direktori berisi gambar.
        threshold: Maksimal hamming distance untuk dianggap duplikat.

    Returns:
        List of tuples (file1, file2, distance).
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    files = sorted(
        f
        for f in Path(directory).iterdir()
        if f.suffix.lower() in image_extensions
    )

    print(f"Menghitung hash untuk {len(files)} gambar...")
    hashes = {}
    for f in files:
        try:
            hashes[str(f)] = compute_phash(str(f))
        except FileNotFoundError:
            continue

    duplicates: List[Tuple[str, str, int]] = []
    paths = list(hashes.keys())

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            dist = hamming_distance(hashes[paths[i]], hashes[paths[j]])
            if dist <= threshold:
                duplicates.append((paths[i], paths[j], dist))

    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(description="Cek duplikat frame.")
    parser.add_argument("--dir", required=True, help="Direktori gambar")
    parser.add_argument(
        "--threshold", type=int, default=10, help="Threshold hamming distance"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tampilkan duplikat tanpa menghapus",
    )
    args = parser.parse_args()

    duplicates = find_duplicates(args.dir, args.threshold)

    if not duplicates:
        print("Tidak ditemukan duplikat.")
        return

    print(f"\nDitemukan {len(duplicates)} pasang duplikat:")
    for f1, f2, dist in duplicates:
        print(f"  [{dist}] {f1} <-> {f2}")

    if not args.dry_run:
        for _, f2, _ in duplicates:
            os.remove(f2)
            print(f"  Dihapus: {f2}")


if __name__ == "__main__":
    main()

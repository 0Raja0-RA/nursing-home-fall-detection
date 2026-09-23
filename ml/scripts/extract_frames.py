"""
extract_frames.py
=================
Ekstrak frame dari video raw (mp4/avi) menjadi gambar individual.

Digunakan untuk mempersiapkan dataset sebelum proses labeling.
Frame diekstrak dengan interval tertentu (misal setiap N frame)
agar tidak terlalu banyak frame yang redundan.

Usage:
    python extract_frames.py --input ml/data/raw/video.mp4 \
                             --output ml/data/extracted_frames/ \
                             --interval 10
"""

import argparse
import os
from pathlib import Path

import cv2


def extract_frames(
    video_path: str,
    output_dir: str,
    interval: int = 10,
) -> int:
    """Ekstrak frame dari video setiap *interval* frame.

    Args:
        video_path: Path ke file video sumber.
        output_dir: Direktori output untuk menyimpan frame.
        interval: Ambil 1 frame setiap *interval* frame.

    Returns:
        Jumlah frame yang berhasil diekstrak.
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise FileNotFoundError(f"Tidak dapat membuka video: {video_path}")

    frame_count = 0
    saved_count = 0
    video_name = Path(video_path).stem

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            filename = f"{video_name}_frame_{frame_count:06d}.jpg"
            filepath = os.path.join(output_dir, filename)
            cv2.imwrite(filepath, frame)
            saved_count += 1

        frame_count += 1

    cap.release()
    print(f"Selesai: {saved_count} frame diekstrak dari {frame_count} total frame.")
    return saved_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ekstrak frame dari video.")
    parser.add_argument("--input", required=True, help="Path ke file video")
    parser.add_argument("--output", required=True, help="Direktori output")
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Interval frame (default: 10)",
    )
    args = parser.parse_args()
    extract_frames(args.input, args.output, args.interval)


if __name__ == "__main__":
    main()

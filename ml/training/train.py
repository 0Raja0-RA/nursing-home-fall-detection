"""
train.py
========
Script untuk training model YOLO11 pada dataset fall detection.

Membaca konfigurasi dari config.yaml dan menjalankan training
menggunakan library ultralytics.

Usage:
    cd ml/training
    python train.py
    python train.py --config config.yaml --resume
"""

import argparse
from pathlib import Path

import yaml
from ultralytics import YOLO


def load_config(config_path: str) -> dict:
    """Load training configuration dari file YAML."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def train(config_path: str = "config.yaml", resume: bool = False) -> None:
    """Jalankan training YOLO11.

    Args:
        config_path: Path ke file konfigurasi YAML.
        resume: Lanjutkan training dari checkpoint terakhir.
    """
    config = load_config(config_path)

    # Load base model atau checkpoint
    model_name = config.pop("model", "yolo11s.pt")
    data_path = config.pop("data")

    print(f"{'Melanjutkan' if resume else 'Memulai'} training...")
    print(f"  Base model : {model_name}")
    print(f"  Dataset    : {data_path}")

    model = YOLO(model_name)

    results = model.train(
        data=data_path,
        resume=resume,
        **config,
    )

    print("\nTraining selesai!")
    print(f"Best model tersimpan di: {results.save_dir}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Train YOLO11 fall detection.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path ke config YAML (default: config.yaml)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Lanjutkan training dari checkpoint terakhir",
    )
    args = parser.parse_args()
    train(args.config, args.resume)


if __name__ == "__main__":
    main()

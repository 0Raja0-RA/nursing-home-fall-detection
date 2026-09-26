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


def load_config(config_path: str) -> tuple[dict, Path]:
    """Load training configuration dari file YAML."""
    p = Path(config_path)
    if not p.exists():
        alt = Path(__file__).parent / config_path
        if alt.exists():
            p = alt
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f), p.resolve()


def train(config_path: str = "config.yaml", resume: bool = False):
    """Jalankan training YOLO11.

    Args:
        config_path: Path ke file konfigurasi YAML.
        resume: Lanjutkan training dari checkpoint terakhir.
    """
    config, cfg_path = load_config(config_path)

    # Load base model atau checkpoint
    model_name = config.pop("model", "yolo11n.pt")
    raw_data_path = config.pop("data")

    # Resolve data path relatif terhadap config file
    data_path = Path(raw_data_path)
    if not data_path.is_absolute():
        data_path = (cfg_path.parent / data_path).resolve()

    # Resolve project path agar konsisten
    if "project" in config:
        proj_path = Path(config["project"])
        if not proj_path.is_absolute():
            config["project"] = str((cfg_path.parent / proj_path).resolve())

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

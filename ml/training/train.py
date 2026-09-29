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

    import torch
    import ultralytics

    gpu_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if gpu_available else "CPU"
    vram_info = f"{torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB" if gpu_available else "N/A"

    print("=" * 65)
    print("🔥 YOLO11 TRAINING PIPELINE - FALL DETECTION")
    print("=" * 65)
    print(f"• Ultralytics Version: {ultralytics.__version__}")
    print(f"• PyTorch Version    : {torch.__version__} (CUDA: {torch.version.cuda if gpu_available else 'Disabled'})")
    print(f"• Device / Hardware  : {device_name} (VRAM: {vram_info})")
    print(f"• Base Model         : {model_name}")
    print(f"• Dataset Config     : {data_path}")
    print(f"• Epochs             : {config.get('epochs', 50)}")
    print(f"• Batch Size         : {config.get('batch', 16)}")
    print(f"• Image Size         : {config.get('imgsz', 640)}")
    print("=" * 65)
    print("⚡ Memulai training (progress bar live ditampilkan per-batch)...")
    print("=" * 65)

    model = YOLO(model_name)

    # Ultralytics secara bawaan menggunakan progress bar TQDM interaktif
    results = model.train(
        data=str(data_path),
        resume=resume,
        verbose=True,
        **config,
    )

    print("\n" + "=" * 65)
    print("🎉 TRAINING SELESAI!")
    print("=" * 65)
    print(f"• Best weights tersimpan di: {Path(results.save_dir) / 'weights' / 'best.pt'}")
    print(f"• Last checkpoint tersimpan: {Path(results.save_dir) / 'weights' / 'last.pt'}")
    print(f"• Grafik & Kurva Evaluasi  : {results.save_dir}")

    # Otomatis evaluasi pada test set jika tersedia
    try:
        print("\n📊 Menjalankan Evaluasi Akhir pada Test Set...")
        test_metrics = model.val(data=str(data_path), split="test", verbose=False)
        print("-" * 65)
        print(f"• Test mAP50       : {test_metrics.box.map50 * 100:.2f}%")
        print(f"• Test mAP50-95    : {test_metrics.box.map * 100:.2f}%")
        print(f"• Test Precision   : {test_metrics.box.mp * 100:.2f}%")
        print(f"• Test Recall      : {test_metrics.box.mr * 100:.2f}%")
        print("-" * 65)
    except Exception as e:
        print(f"[NOTE] Evaluasi test set opsional dilewati: {e}")

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

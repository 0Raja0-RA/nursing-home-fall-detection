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


def train(config_path: str = "config.yaml", resume: bool = False, run_id: str = "", notes: str = ""):
    """Jalankan training YOLO11.

    Args:
        config_path: Path ke file konfigurasi YAML.
        resume: Lanjutkan training dari checkpoint terakhir.
        run_id: ID eksperimen untuk logging otomatis ke experiments.csv.
        notes: Catatan ringkas tentang perubahan eksperimen.
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
    test_metrics = None
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

    # Catat ke experiments.csv jika run_id diberikan
    if run_id:
        try:
            import datetime
            csv_path = cfg_path.parent / "experiments.csv"
            date_str = datetime.date.today().isoformat()
            
            # Ekstrak data epoch run dari results secara aman
            epochs_set = config.get("epochs", 50)
            epochs_run = epochs_set
            if hasattr(results, "epoch") and results.epoch is not None:
                epochs_run = results.epoch + 1
            else:
                csv_results = Path(results.save_dir) / "results.csv"
                if csv_results.exists():
                    try:
                        with open(csv_results, "r", encoding="utf-8") as f_res:
                            epochs_run = max(1, len(f_res.readlines()) - 1)
                    except Exception:
                        pass
            
            val_map50 = getattr(results, "results_dict", {}).get("metrics/mAP50(B)", 0.0) * 100
            t_map50 = (test_metrics.box.map50 * 100) if test_metrics and hasattr(test_metrics, "box") else 0.0
            t_map = (test_metrics.box.map * 100) if test_metrics and hasattr(test_metrics, "box") else 0.0
            t_mp = (test_metrics.box.mp * 100) if test_metrics and hasattr(test_metrics, "box") else 0.0
            t_mr = (test_metrics.box.mr * 100) if test_metrics and hasattr(test_metrics, "box") else 0.0
            
            speed_info = getattr(results, "speed", {}) if hasattr(results, "speed") else {}
            inf_ms = speed_info.get("inference", 0.0)
            fps = round(1000.0 / inf_ms, 1) if inf_ms > 0 else 0.0

            log_line = (
                f"{run_id},{date_str},{model_name},{epochs_set},{epochs_run},"
                f"{config.get('batch', 16)},{config.get('imgsz', 640)},"
                f"{config.get('optimizer', 'auto')},{config.get('lr0', 0.01)},"
                f"{config.get('patience', 15)},{val_map50:.2f},{t_map50:.2f},"
                f"{t_map:.2f},{t_mp:.2f},{t_mr:.2f},{inf_ms:.1f},{fps:.1f},"
                f"COMPLETED,\"{notes}\"\n"
            )
            with open(csv_path, "a", encoding="utf-8") as f_csv:
                f_csv.write(log_line)
            print(f"📝 Hasil run berhasil dicatat ke: {csv_path.name}")
        except Exception as e_log:
            print(f"[WARN] Gagal mencatat otomatis ke CSV: {e_log}")

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
    parser.add_argument(
        "--run-id",
        type=str,
        default="",
        help="Identifier eksperimen (misal: EXP-002) untuk pencatatan otomatis ke spreadsheet.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Catatan singkat eksperimen untuk log CSV.",
    )
    args = parser.parse_args()
    train(args.config, args.resume, args.run_id, args.notes)


if __name__ == "__main__":
    main()

# Folder `ml/`

Data, training, evaluasi, dan catatan eksperimen deteksi jatuh. Semua perintah dijalankan dari akar repo dengan `.venv` aktif.

| Folder | Isi |
|---|---|
| `common/` | Fungsi bersama: label, inferensi pose, gambar skeleton |
| `data_pipeline/` | Preprocessing dataset, lihat [README-nya](data_pipeline/README.md) |
| `training/` | `train.py`, `config.yaml`, `kaggle_train.py` |
| `evaluation/` | Evaluasi model dan visualisasi hasil |
| `demo/` | Demo kamera langsung |
| `notebooks/` | Preprocessing, EDA, training, dan [ringkasan hasil](notebooks/results_summary.ipynb) |
| `experiments/` | [Indeks](experiments/EXPERIMENTS.md) dan satu folder per eksperimen |
| `archive/` | Skrip dan notebook yang tidak aktif |
| `data/` | Dataset; gambar dan label tidak masuk git |
| `models/` | Hasil training; backend memuat `models/fall_detection/weights/best.pt` |
| `outputs/` | Output mentah, tidak masuk git, boleh dihapus |

## Perintah utama

```powershell
python ml/demo/demo_pose_fall.py --source 0
python ml/training/train.py --config ml/training/config.yaml
python -m ml.evaluation.pose_sweep --split val
python -m ml.evaluation.pose_visualize configs --split val
python ml/evaluation/eval_lying.py --help
```

Skrip yang memakai `ml/common` dijalankan dengan `python -m`.

## Aturan

1. **Cek dulu `experiments/EXPERIMENTS.md`** sebelum membuat eksperimen baru, supaya tidak mengulang.
2. **Satu eksperimen, satu folder** `experiments/expNNNN_nama/`: `README.md` (pertanyaan, perintah, hasil, keputusan), satu CSV ringkasan, maksimal 3 gambar pilihan.
3. **Output mentah masuk `outputs/`**, tidak pernah ke git.
4. **Sebisa mungkin tambah opsi pada skrip yang ada**, bukan membuat skrip baru.
5. **Lima output training yang disimpan per eksperimen:** `results.csv`, `args.yaml`, `confusion_matrix.png`, `BoxPR_curve.png`, dan `summary.json` (metrik per kelas di val dan test, dataset, versi library, GPU, durasi, lokasi `best.pt`).

## Nomor eksperimen

Nomor terakhir yang terpakai adalah `exp0016`. Eksperimen berikutnya memakai `exp0017`.

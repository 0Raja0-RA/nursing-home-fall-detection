# Pipeline data

Membuat dataset training final dari UR Fall dan MCF. Penjelasan lengkap dan alasan tiap langkah ada di [preprocessing_pipeline.ipynb](../notebooks/preprocessing_pipeline.ipynb), analisis isi data di [eda_dataset.ipynb](../notebooks/eda_dataset.ipynb).

| Tahap | Skrip | Keluaran |
|---|---|---|
| 1 | `prepare_dataset.py` | `data/processed_urfall/` (bbox otomatis `yolo11n`) |
| 2 | `prepare_mcf.py` | `data/processed_mcf/` (bbox otomatis `yolo11m`) |
| 3 | `merge_datasets.py` | `data/processed_v2/` (perantara, hanya lokal) |
| 4 | `audit_dataset.py` | `data/processed_v2/frames_meta.csv` |
| 5 | `make_training_set.py` | `data/processed_final/` |

Alat bantu: `mcf_check.py`, `extract_mcf_tables.py`, `preview_dataset.py`, dan `box_audit.py` (audit manual bbox otomatis). Perintah lengkap ada di [README utama](../../README.md).

Pipeline awal berbasis `prepare_urfall.py` sudah tidak dipakai, dokumennya ada di [archive/DATA_PREPROCESSING_awal.md](../archive/DATA_PREPROCESSING_awal.md).

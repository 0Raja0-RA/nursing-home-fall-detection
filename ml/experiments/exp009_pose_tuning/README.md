# EXP-009 pada dataset baru

**Pertanyaan:** bagaimana grid search threshold EXP-009 pada `processed_final`?

**Perintah:** `python ml/archive/scripts/tune_pose_fall.py --data-dir ml/data/processed_final --out ml/experiments/exp009_pose_tuning/exp009_laila_results.json --features-csv ml/experiments/exp009_pose_tuning/exp009_laila_features.csv`

**Hasil (test):** threshold terbaik fall 40, trans 60, AR 1.25. Akurasi 53.5%, macro F1 40.4%, lying recall 25.0%, precision 15.7%.

**Keputusan:** threshold saja tidak cukup untuk kamera MCF.

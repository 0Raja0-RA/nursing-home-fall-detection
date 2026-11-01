# EXP-0015: Kualitas keypoint per konfigurasi

**Pertanyaan:** konfigurasi pose mana yang paling sering menemukan orang berbaring dan membaca bahu serta pinggul?

**Perintah:** `python -m ml.evaluation.pose_sweep --split val --configs ...`, gambar dari `python -m ml.evaluation.pose_visualize configs --split val`. Run asli memakai skrip `pose_keypoint_sweep.py`, yang kini digabung ke `pose_sweep.py`.

**Hasil (val, 128 frame lying, keypoint inti terbaca):** `yolo11n` 640 64.8%, `yolo11n` 640 + rotasi 81.2%, `yolo11m` 640 77.3%, `yolo11m` 1280 83.6%, `yolo11m` 640 + rotasi 90.6%. `results.csv` memuat rincian per kamera.

**Temuan lain:** deteksi conf tertinggi kadang berupa benda, misalnya kursi berjaket di `c5` (`grid_lying_baseline_gagal.jpg`). Pipeline perlu memilih orang dengan lebih cerdas.

**Keterbatasan:** metrik ini proxy terhadap bbox label dan belum dikonfirmasi di test.

**Keputusan:** rotasi dan model `m` layak dilanjutkan. Perbandingan dengan fine-tune di `models/pose/exp0013` dan `exp0014` belum dilakukan.

**File mentah:** `ml/outputs/viz/`, `ml/outputs/pose_sweep_val.csv`

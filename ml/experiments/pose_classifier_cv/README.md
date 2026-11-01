# Klasifier keypoint vs aturan sudut

**Pertanyaan:** apakah klasifier di atas fitur keypoint mengungguli aturan sudut, termasuk pada skenario dan kamera yang belum pernah dilihat?

**Perintah:** `python ml/archive/scripts/pose_extract_features.py`, lalu `pose_classifier_cv.py` dan `pose_grouped_cv.py`, semuanya di `ml/archive/scripts/`.

**Hasil (validasi silang per video, `yolo11n` 640):** HGB recall 64.9%, precision 76.0%, FPR normal 6.0%. Aturan sudut recall 41.9%, precision 66.1%, FPR normal 6.3%. Pada kamera yang belum dilihat, HGB recall 49.9% dan aturan sudut 33.0%. Rincian ada di `results.csv`.

**Keputusan:** klasifier keypoint lebih baik daripada aturan sudut. Hasil ini per frame dan belum dievaluasi per kejadian.

**File mentah:** `ml/outputs/pose_classifier_cv/`

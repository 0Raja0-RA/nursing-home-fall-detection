# Model bbox lama pada dataset baru

**Pertanyaan:** bagaimana model `fall_detection` (dilatih di UR Fall) bekerja pada `processed_final`?

**Perintah:** `python ml/evaluation/eval_bbox.py`, `python ml/evaluation/eval_lying.py`, `python ml/archive/scripts/lying_loss_decomposition.py`

**Hasil (test, 3.401 gambar, conf 0.25):**
- Akurasi 45.8%, macro F1 38.8%. UR Fall akurasi 77.1%, MCF 40.0%.
- Dari 264 frame lying, 90 benar sebagai lying dan 114 tidak terdeteksi.
- Lying vs bukan-lying: recall 36.0%, precision 18.3%, AP 0.236.
- Pada pipeline awal, 209 frame lying UR Fall tersisa 13 setelah dedup pHash, dan 11 setelah dedup serta deteksi `yolo11n`.

**Keputusan:** model ini tidak bisa dipakai pada kamera MCF tanpa dilatih ulang. Angka lying recall 100% di EXP-006 tidak mewakili dataset baru.

**File mentah:** `ml/outputs/bbox_on_new_data/`

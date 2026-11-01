# Pose: resolusi dan ukuran model

**Pertanyaan:** seberapa banyak frame lying terbaca jika resolusi dan ukuran model dinaikkan? Tanpa training.

**Perintah:** `python ml/archive/scripts/pose_resolution_sweep.py`

**Hasil (264 frame lying test, conf 0.25):** orang terdeteksi naik dari 114 frame (`yolo11n` 640) ke 135 (`yolo11m` 640) dan 221 (`yolo11m` 1280). Sudut di bawah 40 derajat: 58, 91, dan 119 frame.

**Keputusan:** ukuran model dan resolusi berpengaruh besar, tapi `yolo11m` 1280 terlalu lambat untuk dijadikan default tanpa uji alarm palsu.

**File mentah:** `ml/outputs/pose_resolution/`

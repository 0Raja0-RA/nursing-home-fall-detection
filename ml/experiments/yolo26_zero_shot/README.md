# YOLO26-pose tanpa training

**Pertanyaan:** apakah YOLO26-pose lebih baik dari YOLO11-pose pada frame lying, tanpa training?

**Perintah:** `python ml/archive/scripts/yolo26_zero_shot.py --mode pose`

**Hasil (264 frame lying test, conf 0.25, orang terdeteksi):** `yolo11n` 640 113 frame, `yolo26n` 640 74, `yolo26s` 640 120, `yolo26m` 640 92. Pada 1280, `yolo11n` 177, `yolo26n` 94, `yolo26s` 133, `yolo26m` 144.

**Keputusan:** generasi model tidak lebih berpengaruh daripada ukuran dan resolusi, jadi YOLO26 tidak diprioritaskan.

**File mentah:** `ml/outputs/yolo26_zero_shot/`

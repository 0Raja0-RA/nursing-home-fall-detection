# Pose: ambang confidence pada seluruh test

**Pertanyaan:** bagaimana recall dan alarm palsu berubah jika conf diturunkan?

**Perintah:** `python ml/archive/scripts/pose_conf_sweep_fulltest.py --weights yolo11m-pose.pt --imgsz 1280`

**Hasil (`yolo11m` 1280, 3.401 gambar):**

| Conf | Lying terdeteksi | Aturan 20/1.15: recall / precision | Aturan 40/1.25: recall / precision |
|---|---|---|---|
| 0.25 | 83.0% | 48.1% / 36.6% | 56.1% / 22.5% |
| 0.10 | 92.0% | 50.4% / 35.7% | 61.0% / 22.9% |
| 0.05 | 97.3% | 50.4% / 35.2% | 61.7% / 22.9% |

**Keputusan:** deteksi hampir penuh tetap belum cukup, karena recall tertahan oleh aturan sudut. Masalah ini bukan hanya soal menemukan orang.

**File mentah:** `ml/outputs/pose_conf_sweep/`

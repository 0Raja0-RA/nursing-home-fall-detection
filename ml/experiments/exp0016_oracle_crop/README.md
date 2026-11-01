# EXP-0016: Oracle crop vs gambar penuh

**Pertanyaan:** apakah pose lebih baik jika dijalankan pada potongan orang, dengan bbox label sebagai pengganti detektor sempurna?

**Perintah:** `python -m ml.evaluation.pose_sweep --split val --out ml/outputs/oracle_crop`. Run asli memakai `pose_oracle_crop.py`, yang kini digabung ke `pose_sweep.py`.

**Hasil (val, GPU, keypoint inti terbaca):**

| Konfigurasi | Lying | Transisi | Normal | Waktu |
|---|---|---|---|---|
| Penuh, `m` 640 + rotasi | 90.6% | 94.7% | 86.0% | 98 ms |
| Penuh, `m` 640 | 77.3% | 90.7% | 84.7% | 33 ms |
| Crop, `m` 320 | 83.6% | 93.3% | 92.0% | 22 ms + detektor |
| Crop, `m` 640 | 75.8% | 86.7% | 78.7% | 36 ms + detektor |
| Crop, `m` 640 + rotasi | 80.5% | 85.3% | 75.3% | 104 ms + detektor |

**Keterbatasan:** crop memakai bbox label, jadi ini batas atas. Beberapa bbox `c3` tampak terpotong. Grid di folder ini membandingkan dengan crop `m` 640, bukan crop terbaik `m` 320.

**Keputusan:** belum final, pembahasan lanjutan menunggu diskusi dengan Laila.

**File mentah:** `ml/outputs/oracle_crop/`

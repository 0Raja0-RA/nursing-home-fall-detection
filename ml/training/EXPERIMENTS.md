# 🔬 Log Eksperimen & Hyperparameter Tuning YOLO11
## Proyek Deteksi Jatuh Panti Jompo (Nursing Home Fall Detection)

Dokumen ini mencatat seluruh eksperimen pemodelan Machine Learning secara sistematis, transparan, dan berbasis hipotesis ilmiah (*Data-Centric & Model-Centric AI*).

---

## 📊 Tabel Ringkasan Eksperimen (Leaderboard)

| Run ID | Model | Epochs (Run/Set) | Batch | ImgSz | Optimizer (lr0) | Test mAP50 | Test Recall | Test Precision | Latency (ms) | Status | Keputusan |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`EXP-001`** | **`yolo11n.pt`** | **32 / 50** | **16** | **640** | **SGD (0.01)** | **70.40%** | **87.43%** | **49.97%** | **6.1 ms (~164 FPS)** | ✅ Done | **👑 Champion Model Saat Ini** |
| `EXP-002` | `yolo11s.pt` | 50 / 50 | 16 | 640 | AdamW (auto) | 49.72% | 77.36% | 46.92% | 6.3 ms (~158 FPS) | ✅ Done | Overfit pada data latih (Kapasitas model terlalu besar untuk 924 gambar) |
| `EXP-003` | `yolo11n.pt` | TBD | 16 | 640 | AdamW (0.001) | - | - | - | - | ⏳ Next | Fine-tuning Optimizer & Regularization pada model Nano |
| `EXP-004` | Best Model | TBD | 16 | 640 | Best + Cosine LR | - | - | - | - | ⏳ Pending | Learning Rate Schedule Exploration |

---

## 🎯 Target Metrik Sistem Panti Jompo

| Metrik | Target Minimum | Target Ideal | Alasan Klinis / Operasional |
| :--- | :---: | :---: | :--- |
| **Recall (Lying on ground)** | $\ge 85\%$ | $\ge 92\%$ | **Prioritas #1:** Nyawa lansia. Jangan sampai ada lansia jatuh yang tidak terdeteksi sistem. |
| **Precision** | $\ge 65\%$ | $\ge 80\%$ | Mencegah kelelahan perawat (*alarm fatigue*) akibat alarm palsu (bantal/selimut). |
| **mAP50** | $\ge 75\%$ | $\ge 85\%$ | Standar akurasi benchmark computer vision secara menyeluruh. |
| **Inference Latency** | $\le 30\text{ ms}$ | $\le 10\text{ ms}$ | Real-time CCTV surveillance tanpa lag di perangkat lokal / mini PC. |

---

## 📝 Detail Catatan per Eksperimen

### 🔹 EXP-001: Baseline Model (YOLO11 Nano)
* **Tanggal:** 26 September 2026
* **Hardware:** NVIDIA GeForce RTX 2050 (4 GB VRAM)
* **Konfigurasi:**
  * Base Model: `yolo11n.pt` (2.58M parameters)
  * Epochs: 50 (Early stopped pada Epoch 32 karena patience 15)
  * Batch: 16 | ImgSz: 640 | Optimizer: Auto (SGD, lr0: 0.01)
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik (Test Set):**
  * **mAP50:** `70.40%`
  * **mAP50-95:** `49.82%`
  * **Recall:** `87.43%`
  * **Precision:** `49.97%`
  * **Inference Speed:** `6.1 ms` (~164 FPS)
* **Analisis & Temuan:**
  * ✅ Recall sangat memuaskan (87.4%), artinya detektor sangat sensitif menangkap tubuh manusia.
  * ⚠️ Precision masih rendah (~50%). Model nano masih kesulitan membedakan orang duduk santai / membungkuk dengan orang terkapar di lantai.
  * ⚠️ Terdapat lonjakan loss (*loss spike*) pada epoch 13 di grafik validasi.
* **Hipotesis untuk Eksperimen Berikutnya (EXP-002):**
  * Model `yolo11s.pt` (Small - 9.4M parameters) memiliki kapasitas representasi fitur yang jauh lebih kaya. Meningkatkan kapasitas model diprediksi akan mendongkrak Precision tanpa mengorbankan Recall.

---

### 🔹 EXP-002: Architecture Scaling (YOLO11 Small)
* **Tanggal:** 29 September 2026
* **Hardware:** NVIDIA GeForce RTX 2050 (4 GB VRAM)
* **Konfigurasi:**
  * Base Model: `yolo11s.pt` (9.4M parameters — 3.5x lebih besar dari nano)
  * Epochs: 50 (Selesai 50 epoch penuh)
  * Batch: 16 | ImgSz: 640 | Optimizer: Auto (AdamW)
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik (Test Set):**
  * **mAP50:** `49.72%` *(turun -20.68% dibanding EXP-001)*
  * **mAP50-95:** `42.37%`
  * **Recall:** `77.36%` *(turun -10.07%)*
  * **Precision:** `46.92%`
  * **Inference Speed:** `6.3 ms` (~158 FPS)
* **Analisis & Temuan (Insight Penting):**
  * 📉 **Overfitting Akibat Model Terlalu Besar untuk Data Sedikit:**  
    Dataset train kita memiliki 924 gambar (setelah deduplikasi). Model `yolo11s` memiliki 9.4 juta parameter. Karena kapasitas memorisasinya terlalu tinggi, model menghafal pola visual spesifik pada video train (`train_loss` turun sangat rendah ke 0.22), namun saat diuji pada sequence video baru di Test Set (`fall-26` s/d `fall-30`), generalisasinya menurun drastis.
  * 📈 **Sisi Positif:** Pada kelas `normal`, mAP naik menjadi **0.860** (dibanding 0.741 pada baseline).
  * 💡 **Kesimpulan Desain:** Untuk dataset $\approx 1.000$ gambar di panti jompo, **arsitektur `yolo11n` (Nano) terbukti jauh lebih ideal dan tahan terhadap overfitting**.
* **Hipotesis untuk Eksperimen Berikutnya (EXP-003):**
  * Kembali ke arsitektur `yolo11n.pt` sebagai fondasi terbaik, lalu kita fokus pada **Optimizer & Regularisasi**: gunakan `optimizer: AdamW`, turunkan learning rate awal ke `lr0: 0.001`, dan aktifkan `cos_lr: True` untuk menghaluskan konvergensi.

---

### 🔹 EXP-003: Optimizer Tuning on Nano (AdamW + Cosine LR) — *Next*
* **Tujuan:** Memperbaiki Precision baseline nano dengan optimizer `AdamW` yang lebih stabil dan learning rate schedule yang halus.
* **Hipotesis:** AdamW dengan learning rate 0.001 dan cosine annealing akan menekan false positive tanpa menyebabkan model overfit.
* **Perubahan Parameter:** `model: "yolo11n.pt"`, `optimizer: "AdamW"`, `lr0: 0.001`, `cos_lr: True`, `name: "exp003_nano_adamw"`.

---

## 🛠️ Standar Prosedur Alur Kerja & Git Commit

Setiap kali melakukan 1 eksperimen:
1. **Set Parameter:** Ubah `ml/training/config.yaml`.
2. **Jalankan Training:** `python ml/training/train.py`.
3. **Catat Hasil:** Update baris di `ml/training/experiments.csv` dan `ml/training/EXPERIMENTS.md`.
4. **Git Commit:**
   ```powershell
   git add ml/training/config.yaml ml/training/experiments.csv ml/training/EXPERIMENTS.md
   git commit -m "exp(ml): EXP-00X [deskripsi singkat] (mAP50: XX.X%, Recall: XX.X%)"
   git push origin ml-modeling
   ```

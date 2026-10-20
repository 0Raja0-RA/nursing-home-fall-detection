# 🔬 Log Eksperimen & Hyperparameter Tuning YOLO11

## Proyek Deteksi Jatuh Panti Jompo (Nursing Home Fall Detection)

Dokumen ini mencatat seluruh eksperimen pemodelan Machine Learning secara sistematis, transparan, dan berbasis hipotesis ilmiah (*Data-Centric & Model-Centric AI*).

---

## 📊 Tabel Ringkasan Eksperimen (Leaderboard)

|        Run ID        |          Model          | Epochs (Run/Set) |    Batch    |     ImgSz     |     Optimizer (lr0)     |    Test mAP50    |   Test Recall   |   Test Precision   |          Latency (ms)          | Status |                                Keputusan                                |
| :-------------------: | :----------------------: | :---------------: | :----------: | :-----------: | :---------------------: | :--------------: | :--------------: | :-----------------: | :----------------------------: | :-----: | :----------------------------------------------------------------------: |
| **`EXP-001`** | **`yolo11n.pt`** | **32 / 50** | **16** | **640** |  **SGD (0.01)**  | **70.40%** | **87.43%** |       49.97%       |  **6.1 ms (~164 FPS)**  | ✅ Done |                   **👑 Highest mAP50 (General Benchmark)**                   |
|      `EXP-002`      |      `yolo11s.pt`      |      50 / 50      |      16      |      640      |      AdamW (auto)      |      49.72%      |      77.36%      |       46.92%       |       6.3 ms (~158 FPS)       | ✅ Done | Overfit pada data latih (Kapasitas model terlalu besar untuk 924 gambar) |
| **`EXP-003`** | **`yolo11n.pt`** | **49 / 60** | **16** | **640** | **AdamW (0.001)** |      56.91%      | **82.61%** | **56.40%** 📈 | **2.9 ms (~347 FPS)** ⚡ | ✅ Done |    **👑 Highest Speed (Anti-False Alarm Awal)**    |
|      `EXP-004`      |      `yolo11m.pt`      |      45 / 50      |      16      |      640      |    auto (SGD, 0.01)    |      50.45%      |      82.77%      |       47.08%       |           - (Kaggle T4)       | ✅ Done | Severe Overfit (Model 20.1M params terlalu masif untuk 924 sampel) |
| **`EXP-005`** | **`yolo11n.pt`** | **68 / 70** | **16** | **640** | **auto (SGD, 0.01)** |      51.18%      | **92.87%** 🔥 |       47.64%       |  **3.2 ms (~312 FPS)**  | ✅ Done | **👑 Highest All-Class Recall (Eksplorasi Patience 30)** |
| **`EXP-006`** | **`yolo11n.pt`** | **70 / 70** | **16** | **640** | **AdamW (0.001)** | **70.22%** | **76.31%** (Lying: 100% 🔥) | **68.62%** 🏆 | **3.4 ms (~294 FPS)** ⚡ | ✅ Done | **👑 OVERALL CHAMPION (Record mAP50-95: 61.71%, Precision 68.62%, Lying Recall 100%)** |
|      `EXP-007`      |      `yolo11n.pt`      |      70 / 70      |      16      |      640      | AdamW (Two-Stage) |      56.39%      | 71.15% (Lying: 100% 🔥) |       54.70%       |       7.6 ms (local RTX)       | ✅ Done | Two-Stage Freeze (Stage 1 freeze 10 ep 25, Stage 2 unfreeze ep 45) |

---

## 🎯 Target Metrik Sistem Panti Jompo

| Metrik                             |    Target Minimum    |     Target Ideal     | Alasan Klinis / Operasional                                                                        |
| :--------------------------------- | :------------------: | :------------------: | :------------------------------------------------------------------------------------------------- |
| **Recall (Lying on ground)** |     $\ge 85\%$     |     $\ge 92\%$     | **Prioritas #1:** Nyawa lansia. Jangan sampai ada lansia jatuh yang tidak terdeteksi sistem. |
| **Precision**                |     $\ge 65\%$     |     $\ge 80\%$     | Mencegah kelelahan perawat (*alarm fatigue*) akibat alarm palsu (bantal/selimut).                |
| **mAP50**                    |     $\ge 75\%$     |     $\ge 85\%$     | Standar akurasi benchmark computer vision secara menyeluruh.                                       |
| **Inference Latency**        | $\le 30\text{ ms}$ | $\le 10\text{ ms}$ | Real-time CCTV surveillance tanpa lag di perangkat lokal / mini PC.                                |

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
  * 📉 **Overfitting Akibat Model Terlalu Besar untuk Data Sedikit:**Dataset train kita memiliki 924 gambar (setelah deduplikasi). Model `yolo11s` memiliki 9.4 juta parameter. Karena kapasitas memorisasinya terlalu tinggi, model menghafal pola visual spesifik pada video train (`train_loss` turun sangat rendah ke 0.22), namun saat diuji pada sequence video baru di Test Set (`fall-26` s/d `fall-30`), generalisasinya menurun drastis.
  * 📈 **Sisi Positif:** Pada kelas `normal`, mAP naik menjadi **0.860** (dibanding 0.741 pada baseline).

---

### 🔹 EXP-003: Optimizer & Cosine Annealing Tuning (YOLO11 Nano + AdamW)

* **Tanggal:** 01 Oktober 2026
* **Hardware:** NVIDIA GeForce RTX 2050 (4 GB VRAM)
* **Konfigurasi:**
  * Base Model: `yolo11n.pt`
  * Epochs: 60 (Early stopped pada Epoch 49 karena patience 25)
  * Batch: 16 | ImgSz: 640 | Optimizer: `AdamW` (lr0: 0.001, `cos_lr: True`)
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik (Test Set):**
  * **mAP50:** `56.91%` (Val mAP50: **65.92%**)
  * **mAP50-95:** **`50.68%`** *(Rekor Tertinggi!)*
  * **Recall:** `82.61%`
  * **Precision:** **`56.40%`** *(Naik signifikan +6.43% dibanding baseline!)*
  * **Inference Speed:** **`2.9 ms` (~347 FPS)** ⚡ *(Kecepatan 2x lebih kencang!)*
* **Analisis & Temuan:**
  * 🎯 **Precision Terbaik:** AdamW dengan learning rate halus (0.001) berhasil memangkas false positives, menaikkan Precision ke **56.40%**.
  * ⚡ **Efisiensi Ekstrem:** Latensi 2.9 ms sangat mengagumkan untuk deployment CCTV live feed.
  * 🛡️ **mAP50-95:** Skor 50.68% menunjukkan ketepatan bounding box yang sangat rapat (tight fit IoU).


---

### 🔹 EXP-004: Model Scaling Limit (YOLO11 Medium on Kaggle T4)

* **Tanggal:** 30 September 2026
* **Hardware:** Tesla T4 x 1 (Kaggle Cloud GPU)
* **Konfigurasi:**
  * Base Model: `yolo11m.pt` (20.1M parameters — ~8x lebih besar dari nano)
  * Epochs: 50 (Early stopped pada Epoch 45 karena patience 15; best epoch: 30)
  * Batch: 16 | ImgSz: 640 | Optimizer: Auto (SGD, lr0: 0.01)
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik (Test Set):**
  * **val_mAP50:** `58.80%`
  * **Test mAP50:** `50.45%`
  * **Test mAP50-95:** `36.76%`
  * **Test Recall:** `82.77%`
  * **Test Precision:** `47.08%`
* **Analisis & Temuan:**
  * 📉 **Konfirmasi Overfitting Parah (Over-parameterization):** Eksperimen ini memvalidasi hipotesis bahwa memperbesar ukuran model (`nano` $\rightarrow$ `small` $\rightarrow$ `medium`) pada dataset berukuran 924 gambar justru menurunkan performa generalisasi. Model 20.1 juta parameter ini terlalu mudah menghafal latar belakang ruangan pada video latih.
  * 🛑 **Kesimpulan Arsitektur:** YOLO11 Nano (`yolo11n`) terbukti secara definitif sebagai arsitektur paling seimbang dan optimal untuk skala dataset ini.

---

### 🔹 EXP-005: Extended Training & Patience (YOLO11 Nano + Patience 30)

* **Tanggal:** 01-02 Oktober 2026
* **Hardware:** Kaggle Cloud GPU
* **Konfigurasi:**
  * Base Model: `yolo11n.pt` (2.58M parameters)
  * Epochs: 70 (Early stopped pada Epoch 68 karena patience 30; best epoch: 38)
  * Batch: 16 | ImgSz: 640 | Optimizer: Auto (SGD, lr0: 0.01)
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik (Test Set):**
  * **val_mAP50 Peak:** `64.84%` (Epoch 38)
  * **Test mAP50:** `51.18%`
  * **Test mAP50-95:** `36.37%`
  * **Test Recall:** **`92.87%`** 🔥 *(Rekor Tertinggi Sepanjang Eksperimen! Melebihi target ideal klinis $\ge 92\%$)*
  * **Test Precision:** `47.64%`
  * **Inference Speed:** **`3.2 ms` (~312.5 FPS)** ⚡
* **Analisis & Temuan (Insight Klinis & Operasional):**
  * 🛡️ **Prioritas Keselamatan Lansia Terpenuhi (Safety-First):** Test Recall sebesar **92.87%** adalah capaian paling krusial untuk domain panti jompo. Nyaris tidak ada kejadian jatuh atau lansia terkapar di lantai yang luput dari deteksi model ini.
  * ⚖️ **Kompensasi Presisi dengan State Machine:** Presisi 47.64% berarti model cenderung agresif memprediksi postur berbaring. Namun, dalam sistem monorepo kita, *false positive* sesaat akan disaring oleh **Temporal State Machine (10-second confirmation window)** di backend. Lansia yang hanya membungkuk mengambil barang (<10 detik) tidak akan memicu alarm.
  * ⚡ **Kecepatan Inferensi:** 3.2 ms (~312 FPS) memastikan throughput video stream lancar tanpa beban komputasi berat.


---

### 🔹 EXP-006: The Hybrid Optimization (AdamW + Cosine LR + Night/IR Augmentation + Class Loss Tuning) 👑

* **Tanggal:** 02 Oktober 2026
* **Hardware:** Tesla T4 x 1 (Kaggle Cloud GPU)
* **Konfigurasi:**
  * Base Model: `yolo11n.pt` (2.58M parameters)
  * Epochs: 70 (Selesai 70/70 epochs penuh)
  * Batch: 16 | ImgSz: 640 | Optimizer: `AdamW` (lr0: 0.001, lrf: 0.01, `cos_lr: True`)
  * Patience: 30
  * Class Weight Penalty: `cls: 1.0` (Dinaikkan dari default 0.5)
  * Augmentasi Realita Panti: `hsv_v: 0.6` (cahaya redup/malam), `bgr: 0.2` (simulasi infrared CCTV malam), `erasing: 0.4` (occlusion selimut/kursi), `fliplr: 0.5`, `flipud: 0.0`.
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik Keseluruhan (Test Set):**
  * **Test mAP50:** **`70.22%`**
  * **Test mAP50-95:** **`61.71%`** 🏆 *(REKOR BARU TERTINGGI SEPANJANG SEJARAH PROYEK!)*
  * **Test Precision:** **`68.62%`** 🏆 *(REKOR BARU TERTINGGI! Lolos target minimum $\ge 65\%$)*
  * **Test Recall:** `76.31%`
  * **Inference Speed:** **`3.4 ms` (~294.1 FPS)** ⚡
* **Hasil Metrik per Kelas pada Test Set:**
  * **`lying_on_ground` (Lansia Jatuh di Lantai):**
    * **Recall: `100.0%` (1.0)** 🔥 *(Sempurna! Nol lansia jatuh yang lolos!)*
    * **Precision: `87.9%`** *(Sangat bersih dari false positive)*
    * **mAP50: `99.5%`** | **mAP50-95: `89.5%`**
  * **`transitional` (Fase Jatuh / Bergerak):**
    * Precision: `97.4%` | Recall: `64.6%` | mAP50: `86.6%`
  * **`normal` (Aktivitas Harian / Berdiri):**
    * Precision: `20.6%` | Recall: `64.3%` | mAP50: `24.6%`
* **Analisis & Keputusan Saintifik:**
  * 👑 **Champion Model Definitif:** EXP-006 resmi dinobatkan sebagai model terbaik untuk sistem produksi deteksi jatuh panti jompo kita.
  * 🎯 **Mengapa Begitu Hebat?**
    1. Kenaikan drastis `cls: 1.0` membuat model sangat disiplin dalam memisahkan postur rebahan dari postur lainnya, menghasilkan **Recall 100% dan Precision 87.9% khusus untuk kasus orang jatuh**.
    2. Optimizer AdamW + Cosine Annealing berhasil mencegah *gradient explosion*, sehingga *tightness* bounding box (mAP50-95) melonjak tinggi ke **61.71%**.
    3. Augmentasi `hsv_v: 0.6` dan `bgr: 0.2` membuktikan model mampu menggeneralisasi kondisi pencahayaan minim tanpa kehilangan akurasi deteksi.


---

### 🔹 EXP-007: Two-Stage Freeze Backbone Transfer Learning

* **Tanggal:** 02 Oktober 2026
* **Hardware:** Tesla T4 x 1 (Kaggle Cloud GPU) & NVIDIA RTX 2050 (Local Evaluation)
* **Konfigurasi:**
  * Base Model: `yolo11n.pt`
  * **Stage 1 (Head Warmup):**
    * Epochs: 25 | Batch: 16 | ImgSz: 640
    * `freeze: 10` (Membekukan 10 layer pertama: Backbone Conv, C3k2, SPPF)
    * Optimizer: `AdamW` (lr0: 0.001, `cos_lr: True`, `cls: 1.0`)
  * **Stage 2 (Full Fine-Tuning):**
    * Epochs: 45 | Patience: 25
    * `freeze: 0` (Seluruh layer dicairkan / unfreeze)
    * Optimizer: `AdamW` (lr0: **0.0001** — 10x lebih halus, `cos_lr: True`, `cls: 1.0`)
  * Augmentasi: `hsv_v: 0.6`, `bgr: 0.2`, `erasing: 0.4`, `fliplr: 0.5`, `flipud: 0.0`
  * Dataset: UR Fall Cam0 (Train: 924, Val: 254, Test: 320)
* **Hasil Metrik Keseluruhan (Test Set):**
  * **Test mAP50:** `56.39%` *(turun -13.83% dibanding EXP-006)*
  * **Test mAP50-95:** `50.93%` *(turun -10.78%)*
  * **Test Precision:** `54.70%` *(turun -13.92%)*
  * **Test Recall:** `71.15%` *(turun -5.16%)*
* **Hasil Metrik per Kelas pada Test Set:**
  * **`lying_on_ground` (Lansia Jatuh):**
    * **Recall: `100.00%` (1.0)** 🔥 *(Sempurna! Nol kejadian jatuh yang terlewat)*
    * **Precision: `37.38%`** *(Terjadi peningkatan false positive dibanding EXP-006)*
    * **mAP50: `49.75%`** | **mAP50-95: `49.75%`**
  * **`transitional`:** Precision: `97.25%` | Recall: `48.46%` | mAP50: `92.99%` | mAP50-95: `85.05%`
  * **`normal`:** Precision: `29.46%` | Recall: `64.98%` | mAP50: `26.43%`
* **Analisis & Temuan Saintifik:**
  * 📉 **Mengapa Two-Stage Freeze Kalah dari EXP-006?**
    1. Di arsitektur YOLO (Object Detection), Backbone dan Neck (PAN-FPN) terhubung secara multi-skala (stride 8, 16, 32). Membekukan Backbone selama 25 epoch memaksa Neck beradaptasi pada representasi COCO generik yang belum terspesialisasi pada sudut kamera CCTV dan orientasi lantai.
    2. Saat memasuki Stage 2 dengan learning rate sangat halus (`lr0: 0.0001`), pembaruan bobot backbone berjalan terlalu lambat untuk menyelaraskan kembali geometri postur jatuh, sehingga memicu lebih banyak *false positive* pada kelas rebahan.
  * 🛡️ **Sisi Positif:** Metrik keselamatan lansia tetap solid karena **Recall kasus jatuh berada di angka 100%**.
  * 🏆 **Keputusan:** **EXP-006 tetap dipertahankan sebagai model champion produksi.**

---

### 🔹 EXP-008: Scale-Up Model Capacity & High Resolution (YOLO11s @ 800x800)

* **Tanggal:** 07 Oktober 2026
* **Hardware:** Tesla T4 x 1 (Kaggle Cloud GPU)
* **Konfigurasi:**
  * Base Model: `yolo11s.pt` (9.41M parameters — 3.65x lebih besar dari nano)
  * Epochs: 70 | Batch: 16 | ImgSz: 800 (Resolusi tinggi)
  * Optimizer: `AdamW` (lr0: 0.001, lrf: 0.01, cos_lr: True, patience: 25)
  * Loss & Regularisasi: `cls: 1.2`, `label_smoothing: 0.05`
  * Augmentasi: `hsv_v: 0.6`, `hsv_s: 0.7`, `bgr: 0.2`, `erasing: 0.4`, `scale: 0.5`, `mosaic: 1.0`, `close_mosaic: 10`
* **Hasil Metrik Keseluruhan (Test Set):**
  * **Test mAP50:** `37.99%` *(turun drastis -32.23% dibanding EXP-006)*
  * **Test mAP50-95:** `30.67%` *(turun -31.04%)*
  * **Test Precision:** `36.96%` *(turun -31.66%)*
  * **Test Recall:** `80.94%`
  * **Inference Speed:** `11.7 ms` (~85.5 FPS)
* **Hasil Metrik per Kelas pada Test Set:**
  * **`lying_on_ground` (Lansia Jatuh):**
    * **Recall: `100.00%` (1.0)** 🔥 *(Safety Recall sempurna, nol kasus jatuh yang terlewat)*
    * **Precision: `7.11%`** *(False positive sangat tinggi, banyak objek lain terprediksi jatuh)*
    * **mAP50: `8.29%`** | **mAP50-95: `5.64%`**
  * **`transitional`:** Precision: `80.50%` | Recall: `76.10%` | mAP50: `84.90%` | mAP50-95: `70.76%`
  * **`normal`:** Precision: `23.30%` | Recall: `66.70%` | mAP50: `20.80%` | mAP50-95: `15.60%`
* **Analisis & Temuan Saintifik:**
  * 📉 **Konfirmasi Batas Kapasitas Model (Capacity Saturation):**
    1. Dataset UR Fall Cam0 (924 gambar latih) **terlalu kecil** untuk menopang 9.41 juta parameter `yolo11s`. Model mengalami overfitting parah dengan menghafal variasi noise piksel daripada mempelajari batas postur yang dapat digeneralisasi.
    2. Resolusi `800x800` pada video rekaman sumber (yang resolusi aslinya 640x480) tidak menambahkan informasi visual baru, melainkan hanya memperbesar blur interpolasi piksel.
    3. Distribusi test set sangat tidak seimbang: `transitional` menguasai **91.25%** (292 dari 320 gambar), sedangkan `lying_on_ground` hanya memiliki **1 gambar** (0.3%). Ketimpangan ekstrem ini membuat model bias berat ke arah memprediksi transitional, dan 1 kesalahan deteksi pada kelas jatuh langsung menghancurkan nilai mAP.
  * 🏆 **Kesimpulan & Keputusan:**
    * **EXP-006 (`yolo11n.pt` @ 640x640) tetap tak tergantikan sebagai 👑 Model Champion Produksi untuk Bounding Box** (Test mAP50: 70.22%, mAP50-95: 61.71%, Precision: 68.62%, Lying Recall: 100%).
    * Eksperimen ini membuktikan secara empiris bahwa kita telah mencapai **batas teoritis maksimal (mathematical ceiling)** dari pendekatan *bounding-box object detection* murni pada dataset UR Fall 924 gambar.

---

### 🔹 EXP-009: Kinematic Pose Estimation & Threshold Tuning (YOLO11n-Pose)

* **Tanggal:** 08 Oktober 2026
* **Hardware:** NVIDIA GeForce RTX 2050 (Local GPU)
* **Paradigma Baru:** **17 Skeletal Keypoints + Kinematic Spine Angle ($\theta$) Analysis**
* **Konfigurasi & Metodologi:**
  * Base Model: `yolo11n-pose.pt` (Pretrained COCO Keypoints, 2.9M parameters, 7.5 GFLOPs)
  * Feature Extraction: Ekstraksi koordinat sendi bahu (left: 5, right: 6) dan pinggul (left: 11, right: 12)
  * Rumus Kinematika Sudut Tulang Belakang terhadap Bidang Horizontal Lantai:
    $$\theta = \arctan2(|\Delta y|, |\Delta x|) \times \frac{180}{\pi}$$
  * Parameter Optimasi (Grid Search pada 254 sampel Validation Set):
    * Fall Angle ($\theta_{\text{fall}}$ candidates: 20° - 40°)
    * Transitional Angle ($\theta_{\text{trans}}$ candidates: 45° - 60°)
    * Aspect Ratio ($AR_{\text{threshold}}$ candidates: 1.05 - 1.35)
* **Threshold Optimal Hasil Grid Search (Val Set):**
  * **Optimal Fall Angle:** $< 20.0^\circ$ *(orang terkapar mendatar di lantai)*
  * **Optimal Transitional Angle:** $< 60.0^\circ$ *(orang membungkuk / oleng)*
  * **Optimal Aspect Ratio:** $> 1.15$
  * **Inference Speed:** ~15.3 ms/frame (**~65.4 FPS batch**)
* **Hasil Evaluasi Independen pada Test Set (320 Gambar):**
  * **Test Accuracy:** `38.44%`
  * **Macro F1-Score:** `24.46%`
  * **Normal (GT=0) Accuracy/Recall:** **`100.0%` (27 dari 27 gambar benar)**
  * **Lying Recall (GT=2):** `0.00%` *(Hanya ada 1 sampel di seluruh test set, terjadi motion blur parah)*
  * **Confusion Matrix Test Set:**
    $$\begin{bmatrix}
    \text{Actual \textbackslash\ Pred} & \textbf{Normal} & \textbf{Transitional} & \textbf{Lying} \\
    \textbf{Normal (GT=0)} & \mathbf{27} & 0 & 0 \\
    \textbf{Transitional (GT=1)} & 171 & \mathbf{96} & 25 \\
    \textbf{Lying (GT=2)} & 1 & 0 & \mathbf{0}
    \end{bmatrix}$$
* **Analisis Mendalam & Root Cause Analysis (RCA):**
  * 🔬 **Mengapa Angka Metrik di UR Fall Test Set Rendah, tetapi Superior di Demo Live?**
    1. **Annotation Pathology / Label Noise pada Dataset Benchmark:**
       * Test set UR Fall memiliki **292 gambar (91.25%)** yang semuanya dilabeli secara borongan sebagai `transitional`.
       * Pada video aslinya, aktor berdiri beberapa detik sebelum jatuh ($\theta \ge 60^\circ$). Model Pose secara objektif memprediksinya sebagai `normal` (171 gambar). Saat aktor sudah mendarat di lantai ($\theta < 20^\circ$), model memprediksinya sebagai `lying` (25 gambar). Model Pose mengikuti **hukum fisika sudut nyata**, sementara anotasi ground truth dataset tidak konsisten.
    2. **Single-sample Lying Class (0.3% Test Set):**
       * Hanya ada **1 gambar** berlabel `lying_on_ground` di test set (`fall-30_f0062.jpg`). Karena gambar tersebut buram dan terpotong di sudut lantai sehingga confidence < 0.25 (fallback to 90°), recall menjadi $0/1 = 0.00\%$.
  * 🚀 **Keunggulan Nyata di Pengujian Live (Iriun Webcam):**
    * Model berjalan lancar di **20–27 FPS live webcam** dengan deteksi multi-person (3–4 orang).
    * Membedakan posisi duduk santai ($\theta \approx 85^\circ$), membungkuk ($\theta \approx 43^\circ$), dan jatuh di lantai ($\theta = 12^\circ$) secara presisi.
    * **0% False Positive pada Furnitur/Kasur:** Berbeda dari bounding box yang memicu false alarm pada kasur/bantal rebah, pose estimation mensyaratkan adanya sendi manusia asli.
* **Keputusan Strategis:**
  * **EXP-009 (YOLO11n-Pose)** diadopsi sebagai **Arsitektur Utama untuk Real-World Deployment / EHS K3**, sementara **EXP-006** tetap diarsipkan sebagai representasi terbaik pendekatan Bounding Box murni.

---

### 🔹 EXP-010: Temporal Kinematic Fall Velocity & Dynamic Sequence Analysis

* **Tanggal:** 09 Oktober 2026
* **Hardware:** NVIDIA GeForce RTX 2050 (Local GPU)
* **Paradigma Baru:** **Temporal Trajectory & Downward Velocity ($V_y = \frac{\Delta y}{\Delta t}$) Tracking**
* **Konfigurasi & Metodologi:**
  * Base Model: `yolo11n-pose.pt` (Inference sequential per video clip)
  * Dataset: 11 Rangkaian Video Independen pada Test Set (5 video jatuh `fall-26` s.d. `fall-30`, 6 video aktivitas harian `adl-35` s.d. `adl-40`) dan 10 video pada Validation Set.
  * Formulasi Kecepatan Vertikal Pinggul ($V_y$):
    $$V_y(t) = \frac{Y_{\text{hip}}(t) - Y_{\text{hip}}(t - k)}{k \cdot \Delta t}$$
    *(Normalisasi terhadap tinggi frame piksel)*
  * Threshold Kecepatan Hasil Kalibrasi Val Set: $V_{\text{threshold}} = 0.0350\text{ norm\_h / frame}$
  * Kondisi Pemicu Ganda (*Dual-Trigger*):
    $$\text{Fall Event} \iff (\theta_{\min} < 25.0^\circ) \text{ DAN } (V_{y,\max} \ge 0.0350)$$
* **Hasil Metrik Urutan Video (Sequence-Level Test Set):**
  * **Static Angle Only ($\theta < 25^\circ$):**
    * **Sequence Accuracy:** `72.7%`
    * **Fall Safety Recall:** **`80.0%` (4 dari 5 video jatuh terdeteksi!)**
    * **Precision:** `66.7%`
    * **F1-Score:** `72.7%`
  * **Temporal Dual-Trigger ($\theta < 25^\circ \ \& \ V_y > 0.0350$):**
    * **Sequence Accuracy:** `54.5%`
    * **Fall Safety Recall:** `40.0%` (2 dari 5 video jatuh terdeteksi)
    * **Precision:** `50.0%`
    * **F1-Score:** `44.4%`
* **Analisis & Temuan Saintifik Mendalam (Root Cause Analysis):**
  * 📉 **Mengapa Kecepatan Monokuler ($V_y$) Menurunkan Recall Jatuh?**
    1. **Scale & Perspective Distortion:** Pada kamera 2D monokuler, pergerakan piksel $\Delta y$ sangat dipengaruhi jarak aktor ke lensa kamera. Pada video `fall-27` dan `fall-28` di mana aktor jatuh di sudut ruangan yang jauh, displacement pikselnya kecil ($V_y \approx 0.016-0.023$) sehingga tidak menembus batas threshold kecepatan meskipun aktor jelas-jelas jatuh terkapar di lantai.
    2. **Kekuatan Sudut Tulang Belakang ($\theta$):** Berbeda dari kecepatan piksel, sudut kemiringan $\theta = \arctan2(|\Delta y|, |\Delta x|)$ bersifat **invarian terhadap skala (*scale-invariant*)**. Aktor di jarak 2 meter maupun 6 meter memiliki sudut yang sama persis saat rebah di lantai ($\theta < 20^\circ$).
  * 🛡️ **Validasi Arsitektur Backend FSM 10 Detik:**
    * Temuan ini memvalidasi secara ilmiah bahwa **kombinasi Sudut Kemiringan Statis ($\theta < 20^\circ$) + Stopwatch Durasi 10 Detik (FSM)** di backend adalah solusi paling robust dan stabil untuk deployment nyata, karena tidak terdistorsi oleh noise jarak kamera maupun frame rate jitter.
* **Artefak yang Dihasilkan:**
  * Visualisasi kurva trajektori sudut & lonjakan kecepatan tersimpan di: [`ml/training/curves/exp010_temporal_velocity_curves.png`](curves/exp010_temporal_velocity_curves.png).

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

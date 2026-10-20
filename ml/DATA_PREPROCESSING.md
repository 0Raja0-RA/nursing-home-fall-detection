# 🧹 Konsep & Pipeline Preprocessing Dataset UR Fall

Dokumen ini mendokumentasikan secara lengkap arsitektur dan metodologi pipeline preprocessing dataset **UR Fall Detection (Cam0 RGB)** yang diimplementasikan di [`ml/scripts/prepare_urfall.py`](scripts/prepare_urfall.py).

Pipeline ini dirancang untuk mengatasi 3 tantangan utama dataset video medis:
1. **Ketimpangan Kelas Ekstrem (*Severe Class Imbalance*)** (frame berdiri jauh lebih banyak dibanding frame jatuh).
2. **Frame Redundan (*Temporal Redundancy*)** (ribuan frame statis saat aktor tidak bergerak).
3. **Kebocoran Data (*Data Leakage*)** jika frame diacak secara acak (*random shuffle*).

---

## 1. Sumber Data Mentah (Raw Source)

Dataset berasal dari benchmark publik **UR Fall Detection Dataset**:
* **Input Video/Gambar:** Kamera Cam0 (Frontal RGB 640x480).
  * 30 Rekaman Kasus Jatuh (`fall-01` s.d. `fall-30`)
  * 40 Rekaman Aktivitas Harian / ADL (`adl-01` s.d. `adl-40`)
* **Input Anotasi Asli:** Dua file CSV resmi:
  * `urfall-cam0-falls.csv`
  * `urfall-cam0-adls.csv`

---

## 2. Pemetaan Label Kelas (Class Mapping)

Anotasi asli UR Fall menggunakan format frame level `[-1, 0, 1]`, yang dipetakan ke standar kelas YOLO `[0, 1, 2]`:

| Nilai Asli UR Fall | Kategori Postur Klinis | Kelas YOLO ID | Nama Kelas YOLO | Penjelasan |
| :---: | :--- | :---: | :--- | :--- |
| **`-1`** | *Person is not lying* | **`0`** | **`normal`** | Berdiri, berjalan, atau duduk normal. |
| **`0`** | *Temporary pose* | **`1`** | **`transitional`** | Fase kritis saat tubuh mulai oleng, tergelincir, atau membungkuk. |
| **`1`** | *Person is lying on ground* | **`2`** | **`lying_on_ground`** | Pasien sudah terkapar/terbaring di atas lantai. |

---

## 3. Smart Adaptive Deduplication (pHash 64-bit)

Video 30 FPS menghasilkan ribuan frame yang hampir identik. Jika semua dimasukkan, model akan mengalami *overfitting* pada pose statis. Kami menerapkan **Deduplikasi Adaptif berbasis Perceptual Hashing (pHash 64-bit)** dengan aturan berbeda untuk tiap kelas:

$$\text{Hamming Distance} = \sum |h_1 \neq h_2|$$

```
                                  [ Frame Masuk ]
                                         │
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
             Kelas 'normal'     Kelas 'lying_on_ground'  Kelas 'transitional'
             (Banyak frame)         (Frame rebahan)          (Fase jatuh)
                    │                    │                    │
                    ▼                    ▼                    ▼
             Dedup Agresif        Dedup Moderat        TIDAK DI-DEDUP!
           (Hamming Dist ≤ 10)  (Hamming Dist ≤ 6)     (100% disimpan)
                    │                    │                    │
                    ▼                    ▼                    ▼
               Buang frame          Buang frame         Semua frame
                 kembar               kembar             dipertahankan
```

* **Kelas `normal` (Dedup Agresif):** Membuang frame berjalan/berdiri yang redundan agar tidak mendominasi dataset.
* **Kelas `lying_on_ground` (Dedup Moderat):** Membuang frame terkapar yang terlalu lama/identik, tetapi tetap menyisakan sampel yang cukup.
* **Kelas `transitional` (Tanpa Dedup - Zero Deduplication):** Karena kejadian jatuh berlangsung sangat cepat (hanya 0.3 s.d. 0.8 detik), setiap milidetik frame pada fase transisi ini **sangat langka dan berharga**.

---

## 4. Auto-Annotation Bounding Box (YOLO11 Pre-trained)

Anotasi asli UR Fall hanya memberikan label kelas per-frame tanpa kotak koordinat (*no bounding box*).
Untuk membuat format deteksi YOLO:
1. Setiap frame yang lolos tahap deduplikasi diproses oleh model dasar pre-trained `yolo11n.pt`.
2. Deteksi kelas `person` dengan confidence tertinggi diekstrak koordinatnya:
   $$\text{BBox} = [x_{\text{center}}, y_{\text{center}}, \text{width}, \text{height}] \quad (\text{dinormalisasi } 0.0 - 1.0)$$
3. Kelas label diisi sesuai hasil lookup CSV asli UR Fall.
4. Anotasi disimpan ke file teks format YOLO: `<label_id> <x_center> <y_center> <width> <height>`.

---

## 5. Group Splitting Berbasis Sequence (Anti Data-Leakage)

> **Prinsip Utama:** Jangan pernah membagi frame secara acak (*random train_test_split*) pada data video! Frame ke-10 dan frame ke-11 dari orang yang sama memiliki kemiripan 99%. Membaginya ke train dan test akan menyebabkan *data leakage* dan akurasi palsu (*data memorization*).

Kami membagi data berdasarkan **Nomor Urut Video (Sequence-Based Group Split)**:

### A. Rekaman Jatuh (30 Video Fall):
* **Train Set (70%):** `fall-01` s.d. `fall-21` (21 video)
* **Val Set (13.3%):** `fall-22` s.d. `fall-25` (4 video)
* **Test Set (16.7%):** `fall-26` s.d. `fall-30` (5 video)

### B. Rekaman Aktivitas Normal (40 Video ADL):
* **Train Set (70%):** `adl-01` s.d. `adl-28` (28 video)
* **Val Set (15%):** `adl-29` s.d. `adl-34` (6 video)
* **Test Set (15%):** `adl-35` s.d. `adl-40` (6 video)

---

## 6. Struktur Output Dataset Akhir

Hasil akhir preprocessing tersimpan di:
* Folder aktif: `ml/data/processed/`
* Arsip terkompresi: `ml/data/urfall_yolo_dataset.zip` (109 MB)

```
ml/data/processed/
├── data.yaml            # Konfigurasi path & 3 kelas YOLO
├── images/
│   ├── train/          # 924 gambar (21 fall + 28 adl)
│   ├── val/            # 254 gambar (4 fall + 6 adl)
│   └── test/           # 320 gambar (5 fall + 6 adl)
└── labels/
    ├── train/          # 924 file .txt anotasi YOLO
    ├── val/            # 254 file .txt anotasi YOLO
    └── test/           # 320 file .txt anotasi YOLO
```

---

## 7. Cara Menjalankan Ulang Preprocessing

Jika sewaktu-waktu ingin mengekstrak ulang dari file ZIP asli:

```powershell
python ml/scripts/prepare_urfall.py --downloads-dir "path/to/downloads" --zip-output
```

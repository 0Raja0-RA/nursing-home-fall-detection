# Architecture Overview

Dokumentasi arsitektur sistem Fall Detection untuk panti jompo.

## System Overview

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐
│  IP Camera  │     │                    BACKEND (FastAPI)                  │
│  / Webcam   │────▶│                                                      │
│  (RTSP)     │     │  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
└─────────────┘     │  │  Camera    │  │  Inference   │  │   State     │  │
                    │  │  Service   │──│  Service     │──│   Machine   │  │
                    │  │ (capture)  │  │ (YOLO11 .pt) │  │  (per cam)  │  │
                    │  └────────────┘  └──────────────┘  └──────┬──────┘  │
                    │                                           │         │
                    │                    ┌──────────────────────┤         │
                    │                    ▼                      ▼         │
                    │  ┌─────────────────────┐  ┌────────────────────┐   │
                    │  │  Notification       │  │   WebSocket        │   │
                    │  │  Service (Telegram) │  │   Manager          │   │
                    │  └─────────────────────┘  └────────┬───────────┘   │
                    │                                    │               │
                    │  ┌─────────────────────┐           │               │
                    │  │  SQLite Database    │           │               │
                    │  │  (alert history)    │           │               │
                    │  └─────────────────────┘           │               │
                    │                                    │               │
                    │  ┌─────────────────────┐           │               │
                    │  │  REST API           │           │               │
                    │  │  /api/alerts        │           │               │
                    │  │  /api/cameras       │           │               │
                    │  │  /api/settings      │           │               │
                    │  └─────────┬───────────┘           │               │
                    └────────────┼────────────────────────┼───────────────┘
                                 │                        │
                    ┌────────────┼────────────────────────┼───────────────┐
                    │            ▼          FRONTEND      ▼               │
                    │  ┌─────────────────┐  ┌────────────────────┐       │
                    │  │  API Client     │  │  WebSocket Client  │       │
                    │  │  (axios)        │  │  (auto-reconnect)  │       │
                    │  └────────┬────────┘  └────────┬───────────┘       │
                    │           │                     │                   │
                    │  ┌────────┴─────────────────────┴───────────┐      │
                    │  │              React Dashboard              │      │
                    │  │  ┌───────────┐ ┌──────────┐ ┌─────────┐ │      │
                    │  │  │ Dashboard │ │  Alert   │ │Settings │ │      │
                    │  │  │ (live)    │ │ History  │ │(thresh) │ │      │
                    │  │  └───────────┘ └──────────┘ └─────────┘ │      │
                    │  └──────────────────────────────────────────┘      │
                    └───────────────────────────────────────────────────┘
```

## Development Phase

```mermaid
graph LR
    A[Collect Video] --> B[Extract Frames]
    B --> C[Label Dataset]
    C --> D[Train YOLO11]
    D --> E[Export best.pt]
    E --> F[Integrate with Backend]
```

1. **Data Collection**: Download UR Fall Detection Dataset.
2. **Frame Extraction**: `ml/scripts/extract_frames.py` → frame individual.
3. **Dedup**: `ml/scripts/dedup_check.py` → hapus frame redundan.
4. **Label Conversion**: Convert UR Fall labels (-1/0/1) ke YOLO format (0/1/2).
5. **Training**: `ml/training/train.py` dengan config di `config.yaml`.
6. **Export**: Model `best.pt` tersimpan di `ml/models/`.

## Real-Time Deployment Phase

```mermaid
graph TD
    CAM[Camera/RTSP] --> CS[Camera Service]
    CS -->|frame| IS[Inference Service]
    IS -->|posture + confidence| SM[State Machine]
    SM -->|CONFIRMED_FALL| NS[Notification Service]
    SM -->|status_update| WS[WebSocket Manager]
    NS -->|alert| TG[Telegram Bot]
    WS -->|real-time| FE[Frontend Dashboard]
    SM -->|alert record| DB[(SQLite)]
```

## State Machine Diagram

```mermaid
stateDiagram-v2
    [*] --> MONITORING
    MONITORING --> POSSIBLE_FALL : lying_on_ground detected
    POSSIBLE_FALL --> CONFIRMED_FALL : duration >= threshold
    POSSIBLE_FALL --> MONITORING : posture = normal / transitional
    CONFIRMED_FALL --> MONITORING : acknowledged / reset
```

## Tech Stack

| Layer     | Technology             |
|-----------|------------------------|
| ML        | YOLO11 (ultralytics)   |
| Backend   | FastAPI + uvicorn      |
| Database  | SQLite (aiosqlite)     |
| Frontend  | React + Vite           |
| Notif     | Telegram Bot API       |
| Deploy    | Docker Compose         |

## Filosofi alarm dan tabel status

Acuan bersama tim untuk semua layar dan pesan yang berkaitan dengan alarm. Alasannya
berasal dari riset referensi UI/UX proyek ini (audit 41 temuan, rencana Tahap 1 dan 2).

### Prinsip

1. **Alarm berarti kemungkinan, bukan kepastian.** Model membaca postur berbaring,
   bukan kejadian jatuh. Kata yang dipakai: "Kemungkinan jatuh" dan "terbaca
   berbaring N detik", tidak pernah "Terdeteksi jatuh" atau "tidak bergerak".
2. **Tidak ada rasa aman palsu.** Kamera yang tidak menemukan orang tidak disebut
   Normal, dan kamera yang buta selalu terlihat sebagai Terputus, di layar dan di grup.
3. **Satu warna, satu arti.** Merah hanya untuk alarm yang belum direspons. Amber untuk
   hitungan berbaring dan untuk alarm yang sudah ada yang menuju lokasi. Biru untuk
   latihan dan info. Abu-abu untuk hal teknis dan keterangan. Hijau hanya untuk logo,
   tombol utama, dan tanda selesai. Setiap status juga punya ikon dan kata, tidak
   mengandalkan warna saja.
4. **Penanganan dua langkah, terlihat semua orang.** "Saya ke sana" mencatat nama,
   menghentikan bunyi di semua dashboard, dan menyunting pesan Telegram. "Tandai
   Ditangani" dilakukan setelah penghuni ditolong.
5. **Penanganan dan putusan dipisah.** Putusan (jatuh sungguhan, alarm palsu dengan
   alasan, belum yakin) menjawab seberapa sering alarmnya salah. Alarm tanpa putusan
   tetap di antrean Perlu tindakan.
6. **Tidak ada yang menutup alarm diam-diam.** Tidak ada penutupan otomatis, penutupan
   massal, atau bisu tanpa jejak. Bisu hanya 5 menit dan hanya untuk alarm yang sedang
   tampil; alarm baru tetap berbunyi. Menjeda deteksi juga tidak pernah otomatis: Mode
   perawatan dimulai manusia per kamera, paling lama 2 jam, berhitung mundur, tercatat,
   dan dikabarkan ke grup. Alarm yang sudah terbuka tidak ikut tertutup.
7. **Privasi lebih dulu.** Foto di Telegram bawaannya diburamkan dan semua pesan
   dilindungi dari penerusan. Foto lengkap dan klip kejadian hanya bisa dibuka setelah
   masuk, klip tidak pernah dikirim ke Telegram, dan klip dihapus otomatis setelah masa
   simpannya (bawaan 7 hari). Tidak ada pengenalan wajah.
8. **Latihan tidak boleh tertukar dengan kejadian nyata.** Latihan berwarna biru, bernada
   lain, tidak dinilai, tidak ikut dihitung, dan secara bawaan tidak dikirim ke Telegram.

### Status kamera (tile di Pemantauan)

| Status | Bentuk | Arti | Yang perlu dilakukan |
|---|---|---|---|
| Terpantau | lingkaran, abu-abu | model melihat orang dan posturnya bukan berbaring | tidak ada |
| AI tidak menemukan orang | mata tercoret, abu-abu | ruang kosong, atau model gagal membaca orangnya | lihat videonya bila seharusnya ada orang; jam orang terakhir terlihat ditampilkan |
| Berbaring 00:02 dari 00:03 | belah ketupat, amber | hitungan berjalan, alarm belum berbunyi | pantau |
| Kemungkinan jatuh | segitiga, merah | ambang terlewati, alarm berbunyi; tile naik ke depan | tangani lewat banner |
| Latihan | labu kimia, biru | Mode latihan berjalan | ikuti alur seperti alarm sungguhan |
| Mode perawatan 09:32 | jam, biru bergaris | deteksi dan video dijeda manual, dengan hitung mundur; jatuh di ruang ini tidak terdeteksi | lanjutkan pemantauan setelah perawatan selesai, atau biarkan habis sendiri |
| Terputus | kamera tercoret, garis putus-putus | kamera tidak mengirim gambar; jatuh di ruang ini tidak terdeteksi | periksa daya, jaringan, dan alamat di Daftar Kamera |

### Status insiden (banner dan Riwayat Insiden)

| Status | Warna banner | Bunyi | Siapa yang mengubah |
|---|---|---|---|
| Belum direspons | merah | berulang tiap 4 detik | muncul saat ambang terlewati |
| Belum ada yang merespons · 2 mnt | merah, lama ditulis tebal | berulang | tidak ada klaim setelah N menit (Pengaturan, bawaan 2); grup Telegram menerima pengingat sebagai balasan ke pesan alarm, tiap N menit, paling banyak 3 kali |
| Menuju lokasi | amber, dengan nama penangan | berhenti di semua dashboard | "Saya ke sana" di dashboard atau Telegram |
| Ditangani | banner hilang | tidak | "Tandai Ditangani", atau tombol putusan di Telegram |
| Putusan: jatuh sungguhan, alarm palsu (alasan wajib), belum yakin | | | saat menutup, atau belakangan di Riwayat Insiden |
| Belum dinilai | | | ditutup tanpa putusan; tetap di antrean Perlu tindakan |

Banyak alarm sekaligus tampil sebagai satu banner berisi "1 dari 3" dan daftar alarm lain,
bukan tumpukan banner. Urutannya: alarm sungguhan yang belum direspons, lalu yang sudah ada
yang ke sana, lalu latihan; di tiap kelompok yang terlama lebih dulu. Alarm yang baru diklaim
tetap tampil di layar penekannya, supaya Tandai Ditangani ada di tempat yang sama.

Bukti di laci detail Riwayat Insiden: foto saat alarm, dan klip dari sekitar 5 detik
sebelum orangnya terbaca berbaring sampai 5 detik sesudah alarm. Pipeline menitipkan
4 gambar per detik (lebar 640 px) dari 30 detik terakhir di memori, dan klip dipotong
dari situ saat alarm. Bila kamera tidak mengirim gambar, laci menulis bahwa klipnya
tidak ada, bukan menampilkan ruang kosong.

### Aturan angka

Waktu respons dihitung juga untuk alarm palsu, karena perawat tidak tahu statusnya
sebelum memeriksa. Latihan keluar dari semua angka. Persentase selalu disertai jumlah
absolut, misalnya "3 dari 12". Recall tidak bisa dihitung dari putusan, karena jatuh
yang terlewat tidak pernah muncul di daftar.

Riwayat Insiden menampilkan empat kartu untuk rentang yang dipilih: perlu tindakan, median
waktu respons, alarm palsu dari yang dinilai, dan Telegram gagal. Pratinjau ambang di
Pengaturan menilai ulang episode berbaring 30 hari terakhir: bila ambang dinaikkan, ia
menyebut alarm yang hilang beserta putusannya, termasuk jatuh sungguhan; bila diturunkan, ia
menyebut alarm tambahan yang belum pernah dinilai.

Tab Ringkasan shift di Riwayat Insiden menyiapkan serah terima: angka alarm shift itu, alarm
yang masih perlu ditindaklanjuti shift berikutnya, catatan perawat, ruang yang tidak terpantau
karena Mode perawatan atau kamera terputus, dan tanda sudah dibaca. Bawaannya shift sebelumnya.

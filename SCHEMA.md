# SCHEMA.md

Skema database FallDetect, ditulis dari kode di `backend/app/db/models.py` dan `backend/app/db/database.py`. Kalau kode dan dokumen ini berbeda, yang benar adalah kode. Perbaiki dokumen ini dalam perubahan yang sama.

## Mesin dan lokasi

- **SQLite**, satu berkas `backend/fall_detection.db`. Lokasinya diatur `DATABASE_URL` di `backend/app/core/config.py`, dengan bawaan `sqlite+aiosqlite:///./fall_detection.db`. Berkas ini tidak ikut Git.
- Diakses lewat **SQLAlchemy async + aiosqlite**, supaya kerja database tidak memblokir video dan WebSocket.
- Satu backend memegang satu database. Saat pameran, hanya satu laptop yang menjalankan backend, jadi semua dashboard membaca data yang sama.

## Tabel

```mermaid
erDiagram
    cameras {
        string id PK "cam-01, cam-02, ..."
        string name
        string source "0 | http(s) | rtsp | path file"
        int rotate "0, 90, 180, 270"
        bool enabled
        string privasi "utuh | buram | kerangka"
        int denah_baris
        int denah_kolom
        datetime created_at
    }
    akses_video {
        int id PK
        string camera_id
        int alert_id "alarm yang menjadi alasan"
        string oleh
        datetime mulai
        datetime sampai
    }
    app_settings {
        string key PK
        string value
        datetime updated_at
    }
    alerts {
        int id PK
        string camera_id "rujukan longgar, bukan FK"
        string camera_name "disalin saat kejadian"
        string severity
        string message
        float fall_duration
        bool simulated
        bool acknowledged
        datetime acknowledged_at
        string acknowledged_by "nama disalin"
        string claimed_by
        datetime claimed_at
        string verdict "jatuh | palsu | belum_yakin"
        string verdict_reason
        string verdict_by
        datetime verdict_at
        string caregiver_note
        float threshold_sec
        string detection_mode
        bool notified
        string telegram_status
        int telegram_message_id
        bool telegram_foto
        string klip_status "merekam | tersimpan | kosong | gagal | dihapus"
        float klip_detik
        int eskalasi_ke "pengingat Telegram yang terkirim"
        datetime eskalasi_terakhir
        bool terlewat "jatuh yang dicatat manual"
        datetime created_at
    }
    alert_snapshots {
        int alert_id PK "= alerts.id"
        blob jpeg
        datetime created_at
    }
    users {
        int id PK
        string username UK "huruf kecil"
        string display_name
        string password_hash "scrypt"
        string role "pengelola | perawat"
        bool active
        datetime created_at
    }
    sessions {
        string token_hash PK
        int user_id "rujukan ke users.id"
        datetime created_at
        datetime expires_at
    }
    episode_berbaring {
        int id PK
        string camera_id "rujukan longgar, bukan FK"
        datetime mulai
        datetime selesai
        float durasi_maks
        bool alarm
        bool latihan
        bool dipotong "direset oleh Tandai Ditangani"
    }
    serah_terima {
        datetime shift_mulai PK "awal shift, UTC"
        string dibaca_oleh
        datetime dibaca_pada
    }
    jeda_kamera {
        int id PK
        string camera_id "rujukan longgar, bukan FK"
        string camera_name "disalin saat jeda"
        datetime mulai
        datetime sampai "bergeser bila diperpanjang"
        string oleh
        datetime selesai "diisi bila dihentikan lebih awal"
        string diakhiri_oleh
    }
    cameras ||..o{ alerts : "camera_id (tanpa FK)"
    alerts ||..o| alert_snapshots : "satu foto per alert"
    users ||..o{ sessions : "user_id"
    cameras ||..o{ jeda_kamera : "camera_id (tanpa FK)"
    cameras ||..o{ akses_video : "camera_id (tanpa FK)"
    cameras ||..o{ episode_berbaring : "camera_id (tanpa FK)"
```

Semua garisnya putus-putus, karena database ini tidak memasang foreign key sama sekali (`models.py` tidak memakai `ForeignKey`). Hubungan antartabel dijaga oleh kode.

### `cameras`

Daftar kamera. Disimpan di database supaya alamat kamera HP bisa diganti dari dashboard tanpa menyunting kode atau me-restart server.

- `id` dibentuk `cam-NN`. Nomornya tidak pernah dipakai ulang, walaupun kameranya sudah dihapus (lihat `camera_last_number`).
- `source` hanya berlaku di laptop yang menjalankan backend. Contohnya, `0` adalah webcam laptop itu.
- `denah_baris` dan `denah_kolom` meletakkan ruang di denah unit pada layar dinding (mulai 1); kosong berarti belum diletakkan.
- `privasi` menentukan yang ditayangkan, disimpan sebagai foto dan klip, dan dikirim ke Telegram: `utuh`, `buram`, atau `kerangka` (kerangka dan kotak deteksi di latar gelap). Model selalu membaca gambar asli. Kamera baru bawaannya `buram`; kamera yang sudah ada sebelum kolom ini tetap `utuh`.

### `app_settings`

Pengaturan dari dashboard yang harus bertahan setelah restart. Bentuknya pasangan kunci-nilai, supaya menambah pengaturan baru tidak butuh `ALTER TABLE`.

| Kunci | Isi | Ditulis oleh |
|---|---|---|
| `detection_mode` | Model aktif (`bbox` atau `pose`) | `api/settings.py` |
| `fall_duration_threshold` | Ambang detik sebelum alarm | `api/settings.py` |
| `camera_last_number` | Nomor kamera tertinggi yang pernah dipakai | `db/repository.py` |
| `telegram_photo_mode` | Cara foto dikirim ke Telegram (`buram` bawaan, `utuh`, ...) | `db/repository.py` |
| `telegram_send_drills` | `1` bila latihan ikut dikirim ke Telegram | `db/repository.py` |
| `telegram_camera_offline` | `1` bila kamera terputus atau dijeda dikabarkan ke Telegram (bawaan `1`) | `db/repository.py` |
| `pola_shift` | `3` (shift 07, 14, 21) atau `2` (07, 19), untuk ringkasan shift (bawaan `3`) | `api/settings.py` |
| `eskalasi_menit` | Menit tanpa "Saya ke sana" sebelum alarm dieskalasi (bawaan `2`) | `api/settings.py` |

Rahasia seperti token bot dan ID chat Telegram tidak disimpan di sini. Keduanya tetap di `backend/.env`.

### `alerts`

Riwayat insiden. Satu baris untuk satu alarm yang dikonfirmasi state machine, atau untuk satu
jatuh yang tidak memicu alarm dan dicatat manual (`terlewat`).

- **Kejadian:** `camera_id`, `camera_name`, `message`, `severity`, `fall_duration`, `created_at`. Nilai `simulated` = latihan, bukan kejadian sungguhan.
- **Penanganan:** `claimed_by`/`claimed_at` diisi saat ada yang menekan "Saya ke sana". `acknowledged`, `acknowledged_by`, dan `acknowledged_at` diisi saat alarm ditandai ditangani. `caregiver_note` berisi catatan perawat.
- **Putusan:** `verdict` bernilai `jatuh`, `palsu`, atau `belum_yakin`, dan NULL berarti belum dinilai. Untuk alarm palsu, `verdict_reason` berisi kode alasannya. Putusan sengaja dipisah dari penanganan, karena alarm bisa sudah ditangani tetapi belum dinilai.
- **Keadaan sistem saat kejadian:** `threshold_sec` dan `detection_mode`. Tanpa keduanya, angka alarm palsu tidak bisa ditafsirkan.
- **Telegram:** `telegram_status` bernilai `mengirim`, `terkirim`, `gagal`, `mati`, atau `dilewati`. `telegram_message_id` dipakai untuk menyunting pesan yang sama, dan `telegram_foto` menandai pesan berupa foto. Pada alert lama, `telegram_status` NULL dan yang berlaku adalah `notified`.
- **Eskalasi:** `eskalasi_ke` menghitung pengingat Telegram yang sudah terkirim karena alarm belum direspons, dan `eskalasi_terakhir` jam pengingat terakhir. Pengingat dikirim setiap `eskalasi_menit` menit, paling banyak tiga kali, hanya untuk alarm yang pesan Telegram-nya terkirim (`services/eskalasi.py`).
- **Jatuh terlewat:** `terlewat = true` berarti jatuh ini tidak memicu alarm dan dicatat manual dari Riwayat Insiden. `created_at` berisi perkiraan waktu kejadian, `verdict` langsung `jatuh`, dan pencatatnya mengisi `acknowledged_by` dan `verdict_by`. Baris ini tidak dihitung sebagai alarm, tetapi menjadi penyebut recall (jatuh terdeteksi dari semua jatuh yang diketahui) selama putusannya tetap `jatuh`; bila belakangan diubah, misalnya ternyata bukan jatuh, ia keluar dari hitungan.
- **Klip:** `klip_status` bernilai `merekam` (menunggu detik-detik sesudah alarm), `tersimpan`, `kosong` (kamera tidak mengirim gambar di sekitar kejadian), `gagal`, atau `dihapus` (lewat masa simpan). NULL berarti tidak direkam: alert lama, atau perekaman dimatikan. `klip_detik` adalah panjang klipnya. Berkas klipnya sendiri tidak ada di database, tetapi di folder `KLIP_DIR` (bawaan `backend/klip/`, diabaikan git), satu ZIP berisi JPEG per alert, dan dihapus otomatis setelah `KLIP_MASA_SIMPAN_HARI` hari.
- Nama ruang (`camera_name`) dan nama orang (`*_by`) **disalin, bukan dirujuk**. Riwayat harus tetap menyebut tempat dan orangnya walaupun kameranya dihapus atau akunnya dinonaktifkan. Pada alert lama, `camera_name` bisa NULL, dan `camera_id` dipakai sebagai cadangan.

### `alert_snapshots`

Foto kejadian, satu per alert, dengan `alert_id` sama dengan `alerts.id`. Dipisah dari `alerts` supaya daftar riwayat tidak ikut memuat gambar. Foto hanya bisa dibuka lewat API yang wajib login.

### `users`

Akun per orang, karena tombol "Saya ke sana" harus menyebut siapa yang menuju lokasi.

- `role`: `pengelola` atau `perawat`. Yang khusus pengelola saat ini hanya pengelolaan akun (`/api/users`). Kamera dan pengaturan masih bisa diubah oleh akun mana pun yang login. Sistem harus selalu punya minimal satu pengelola aktif.
- `password_hash` disimpan dalam format `scrypt$n$r$p$garam$turunan`, dengan garam acak per akun (`core/keamanan.py`).
- Akun tidak dihapus, hanya dinonaktifkan (`active = false`), supaya nama di riwayat tetap bermakna.
- Akun tim berupa satu akun demo, dibuat atau disamakan setiap backend menyala dari `DEMO_USERNAME` dan `DEMO_PASSWORD` di `backend/.env`, dengan peran `pengelola` (`siapkan_akun_demo` di `api/auth.py`). Tidak ada akun atau kata sandi yang ditulis di kode, dan tidak ada formulir pembuat akun pertama.

### `sessions`

Sesi masuk. Yang disimpan hanya hash token, sedangkan tokennya sendiri ada di cookie HttpOnly. Sesi berlaku 30 hari (`UMUR_SESI` di `api/auth.py`), dan sesi kedaluwarsa dibersihkan saat ada yang masuk.

### `episode_berbaring`

Satu baris untuk setiap masa seseorang terbaca berbaring sampai hitungan dimulai: kapan, berapa lama paling jauh (`durasi_maks`), dan apakah sampai berbunyi (`alarm`). Dipakai pratinjau ambang di Pengaturan, karena kejadian yang berhenti sebelum ambang tidak pernah menjadi alarm. `dipotong` berarti hitungannya direset oleh Tandai Ditangani, jadi lama sebenarnya tidak diketahui. Dicatat pipeline (`services/episode.py`); pasangannya di `alerts` dicari lewat kamera dan waktu, bukan kunci.

### `serah_terima`

Tanda bahwa ringkasan satu shift sudah dibaca shift berikutnya, dengan awal shift (UTC) sebagai kunci. Hanya pembaca pertama yang dicatat. Isi ringkasannya sendiri tidak disimpan, tetapi dihitung dari `alerts` dan `jeda_kamera` setiap kali dibuka (`services/shift.py`).

### `akses_video`

Satu baris setiap kali video asli kamera berprivasi dibuka sementara (15 detik) saat ada alarm: siapa, kamera mana, alarm mana yang menjadi alasannya, dan sampai kapan.

### `jeda_kamera`

Riwayat Mode perawatan: jeda deteksi jatuh dan video di satu kamera, misalnya saat penghuni dimandikan. Jatuh di ruang itu tidak terdeteksi selama jeda, jadi setiap jeda dicatat: siapa (`oleh`), mulai kapan, dan sampai kapan. Memperpanjang jeda menggeser `sampai` di baris yang sama. Bila dihentikan lebih awal, `selesai` dan `diakhiri_oleh` diisi; jeda yang berjalan sampai habis membiarkan `selesai` kosong. Jeda yang belum habis dimuat lagi saat backend menyala (`services/mode_perawatan.py`).

## Batasan dan akses

- Semua API, video, dan WebSocket wajib login (`wajib_login`, dipasang di `backend/app/main.py`). Kecualinya `/api/auth` (status, masuk, pengunjung, keluar) dan health check. Hanya `/api/users` yang khusus `pengelola` (`wajib_pengelola` di `api/auth.py`). Pembatasan ini dijaga di backend, bukan di database: SQLite tidak punya row-level security.
- `users.username` unik dan disimpan dalam huruf kecil.
- Pengunjung pameran (dari QR di stand) tidak punya baris di tabel mana pun. Cookie lihat-sajanya ditandatangani HMAC dengan `VISITOR_TOKEN` dan berlaku 12 jam; token baru dari launcher membatalkan cookie lama. Pengunjung boleh semua GET kecuali `/api/users`, dan metode lain ditolak 403 (`tolak_perubahan_pengunjung` di `api/auth.py`).
- Nilai seperti `role`, `verdict`, dan `telegram_status` disimpan sebagai teks bebas di database. Validasinya ada di skema Pydantic (`backend/app/models/schemas.py`).

## Cara skema diperbarui

Proyek ini tidak memakai alat migrasi seperti Alembic.

1. Saat backend menyala, `init_db()` di `database.py` menjalankan `create_all`, yang membuat tabel yang belum ada.
2. `create_all` tidak menambah kolom ke tabel yang sudah ada. Karena itu, setiap kolom baru juga didaftarkan di `_KOLOM_SUSULAN`, dan `_tambal_kolom` menambahkannya dengan `ALTER TABLE` ke database lama tanpa menghapus riwayat.
3. Untuk perubahan yang lebih berat, seperti mengganti nama atau tipe kolom, pakai Alembic. Mekanisme di atas tidak cukup untuk itu.

Menambah kolom berarti mengubah tiga tempat dalam satu commit: `models.py`, `_KOLOM_SUSULAN`, dan dokumen ini.

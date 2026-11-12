# API Documentation

Dokumentasi endpoint REST API dan WebSocket untuk backend FallDetect. Dokumentasi
interaktif yang selalu sesuai kode ada di `http://localhost:8000/docs` saat backend berjalan.

Base URL: `http://localhost:8000`

---

## Login dan sesi

Semua endpoint wajib login, kecuali `GET /`, `GET /api/auth/status`,
`POST /api/auth/login`, `POST /api/auth/pengunjung`, dan `POST /api/auth/logout`. Tanpa
sesi yang sah, jawabannya `401`. Ini juga berlaku untuk video MJPEG dan WebSocket.

Sesi disimpan di cookie `falldetect_sesi` (HttpOnly, SameSite=Lax, 30 hari). Cookie
dipakai, bukan header `Authorization`, karena video dimuat lewat `<img>` dan siaran
langsung lewat WebSocket, dan keduanya tidak bisa membawa header. Akibatnya dashboard
dan backend harus dibuka lewat **host yang sama**: dashboard di `localhost` dengan
backend di `127.0.0.1` akan selalu dianggap belum masuk.

**Akun tim:** satu akun demo, dibuat atau disamakan setiap backend menyala dari
`DEMO_USERNAME` dan `DEMO_PASSWORD` di `backend/.env`, berperan `pengelola`. Tidak ada
akun di kode dan tidak ada formulir pembuat akun pertama, karena lewat tunnel pameran
siapa pun bisa membuka alamatnya.

**Pengunjung pameran:** QR di stand berisi `https://<alamat-tunnel>/lihat#t=<VISITOR_TOKEN>`.
Token ada di fragmen (`#`), jadi tidak pernah sampai ke log server. Halaman `/lihat`
menukarnya lewat `POST /api/auth/pengunjung` dengan cookie `falldetect_pengunjung`
(HMAC dengan `VISITOR_TOKEN`, 12 jam). Pengunjung boleh semua `GET` kecuali `/api/users`;
metode lain dijawab `403` "Pengunjung hanya bisa melihat." Launcher pameran membuat
token baru setiap dijalankan, sehingga cookie pengunjung lama ikut tidak berlaku.
`VISITOR_TOKEN` kosong berarti akses pengunjung mati.

Mencoba API dari halaman `/docs`: jalankan `POST /api/auth/login` di halaman itu,
lalu endpoint lain di halaman yang sama ikut memakai sesinya.

### Auth

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/auth/status` | `{"ada_akun": true, "pengunjung_aktif": true}` |
| POST | `/api/auth/login` | `{"username", "password"}`. Salah: `401`; akun nonaktif: `403`; 5 kali gagal dalam 5 menit: `429` selama 1 menit |
| POST | `/api/auth/pengunjung` | `{"token"}` dari QR. Salah: `403`; akses mati: `404`; tebakan beruntun: `429` |
| POST | `/api/auth/logout` | Keluar dari perangkat ini, sebagai tim maupun pengunjung |
| GET | `/api/auth/me` | Akun yang sedang masuk, atau `{"role": "pengunjung"}` |
| PUT | `/api/auth/password` | `{"password_lama", "password_baru"}`. Perangkat lain ikut dikeluarkan. Untuk akun demo, `backend/.env` kembali berlaku saat backend menyala lagi |

### Akun (khusus pengelola, belum dipakai dashboard)

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/users/` | Daftar akun |
| POST | `/api/users/` | `{"display_name", "username", "password", "role"}`; `role` = `pengelola` atau `perawat` |
| PATCH | `/api/users/{id}` | Ubah `display_name`, `role`, `active`, atau atur ulang `password`. Menonaktifkan atau mengganti sandi mengeluarkan akun itu dari semua perangkat. Pengelola aktif terakhir tidak bisa dinonaktifkan atau diturunkan |

`username`: 3 sampai 32 karakter, huruf kecil, angka, titik, garis bawah, atau tanda
hubung. Kata sandi minimal 8 karakter, disimpan sebagai hash scrypt.

---

## Health Check

### `GET /`

```json
{ "status": "ok", "service": "fall-detection-backend" }
```

---

## Alerts (insiden)

Penanganan dan putusan adalah dua hal terpisah. Penanganan menjawab "sudah ada yang
menolong?", putusan menjawab "apakah ini benar jatuh?". Alarm yang ditutup tanpa putusan
tetap di antrean Perlu tindakan sampai dinilai.

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/alerts/` | Daftar alert, terbaru dulu. Filter di bawah |
| GET | `/api/alerts/ringkasan` | Jumlah per kelompok, untuk tab dan lencana menu |
| GET | `/api/alerts/metrik` | Kartu angka Riwayat Insiden, `sejak` opsional: `total`, `jatuh`, `palsu`, `belum_yakin`, `belum_dinilai`, `belum_ditangani`, `median_respons_detik` (sampai klaim, atau penutupan bila tidak diklaim; alarm palsu ikut), `jumlah_respons`, `telegram_gagal`. Latihan tidak dihitung |
| GET | `/api/alerts/ekspor` | Unduh CSV, filter sama dengan daftar tanpa `skip`/`limit`, urut dari yang terlama. Akun tim saja, pengunjung `403`. Kolomnya di bawah |
| GET | `/api/alerts/count` | Hitung total alert, filter `acknowledged` opsional |
| GET | `/api/alerts/{id}` | Detail satu alert |
| GET | `/api/alerts/{id}/snapshot` | Foto kejadian (JPEG, tanpa diburamkan, `Cache-Control: no-store`). `404` bila tidak tersimpan |
| GET | `/api/alerts/{id}/klip` | Klip sebelum dan sesudah kejadian: `{detik_tergeletak, dihapus_pada, frame: [{t, jpeg}]}`, dengan `t` detik relatif terhadap alarm dan `jpeg` base64 (`Cache-Control: no-store`). `404` beserta sebabnya bila tidak ada; keadaannya ada di `klip_status` alert |
| PUT | `/api/alerts/{id}/claim` | "Saya ke sana". Klaim oleh orang lain ditolak `409` beserta nama dan jamnya |
| PUT | `/api/alerts/{id}/ack` | "Tandai Ditangani". Body opsional `{"verdict", "reason", "note"}` |
| PUT | `/api/alerts/{id}/verdict` | Isi atau ubah putusan belakangan. `409` bila belum ditangani |
| PUT | `/api/alerts/{id}/note` | Tambah atau ubah catatan perawat; teks kosong menghapusnya |
| POST | `/api/alerts/{id}/telegram` | Kirim ulang pesan Telegram yang gagal (`202`); hasilnya terlihat di `telegram_status` |

Filter `GET /api/alerts/`:

| Parameter | Nilai |
|---|---|
| `status` | `terbuka` (belum ditangani), `perlu_tindakan` (belum ditangani atau belum dinilai), `selesai`, `semua` |
| `camera_id` | mis. `cam-02` |
| `verdict` | `jatuh`, `palsu`, `belum_yakin`, `belum_dinilai` |
| `simulated` | `true` hanya latihan, `false` tanpa latihan |
| `sejak`, `sampai` | waktu ISO; tanpa zona dibaca UTC |
| `skip`, `limit` | pagination, `limit` 1 sampai 200 |

CSV `GET /api/alerts/ekspor` berawalan BOM UTF-8 supaya terbaca Excel. Waktu ditulis dalam
zona waktu komputer backend. `detik_sampai_respons` dihitung sampai klaim, atau sampai
penutupan bila tidak ada yang mengklaim. Sel yang diawali `=`, `+`, `-`, atau `@` diberi
tanda kutip tunggal supaya tidak dijalankan sebagai rumus. Kolom: `id`, `waktu_alarm`,
`ruang`, `kamera_id`, `latihan`, `mode_deteksi`, `ambang_detik`, `lama_tergeletak_detik`,
`diklaim_oleh`, `waktu_klaim`, `ditangani_oleh`, `waktu_ditangani`, `detik_sampai_respons`,
`detik_sampai_ditangani`, `putusan`, `alasan_palsu`, `dinilai_oleh`, `waktu_dinilai`,
`telegram`, `catatan`. Dipakai untuk [uji mini](uji-mini.md).
| `acknowledged` | `true` / `false` (lama, tetap didukung) |

Putusan (`verdict`): `jatuh`, `palsu`, `belum_yakin`, atau `null` (belum dinilai).
Bila `palsu`, `reason` wajib salah satu dari `berbaring_sengaja`, `duduk_membungkuk`,
`bukan_orang`, `orang_lain`, `lainnya`; selain itu `reason` diabaikan.

Contoh alert:

```json
{
  "id": 12,
  "camera_id": "cam-02",
  "camera_name": "Kamar 102",
  "severity": "critical",
  "message": "Terdeteksi jatuh pada Kamar 102 selama 5.2 detik.",
  "fall_duration": 5.2,
  "simulated": false,
  "created_at": "2026-11-12T08:19:04",
  "claimed_by": "Siti Aminah",
  "claimed_at": "2026-11-12T08:19:40",
  "acknowledged": true,
  "acknowledged_by": "Siti Aminah",
  "acknowledged_at": "2026-11-12T08:22:10",
  "verdict": "palsu",
  "verdict_reason": "bukan_orang",
  "verdict_by": "Siti Aminah",
  "verdict_at": "2026-11-12T08:22:10",
  "caregiver_note": "Bayangan tirai terbaca sebagai orang.",
  "threshold_sec": 3.0,
  "detection_mode": "pose",
  "notified": true,
  "telegram_status": "terkirim",
  "klip_status": "tersimpan",
  "klip_detik": 12.7,
  "eskalasi_ke": null,
  "eskalasi_terakhir": null
}
```

`camera_name` disalin saat kejadian (kosong pada alert lama; pakai `camera_id`).
Nama penangan lewat Telegram berakhiran `(Telegram)`. `telegram_status`: `mengirim`,
`terkirim`, `gagal`, `mati` (Telegram belum diatur), `dilewati` (latihan tidak dikirim),
atau kosong pada alert lama (lihat `notified`). `klip_status`: `merekam`, `tersimpan`,
`kosong`, `gagal`, `dihapus`, atau kosong bila tidak direkam. `eskalasi_ke`: berapa pengingat
Telegram yang sudah terkirim karena belum ada yang merespons (paling banyak 3), dengan jam
pengingat terakhir di `eskalasi_terakhir`. Waktu disimpan UTC tanpa zona.

---

## Cameras

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/cameras/` | Kamera terdaftar beserta status runtime-nya |
| POST | `/api/cameras/` | Daftarkan kamera baru; sumbernya diperiksa dulu |
| GET | `/api/cameras/{id}` | Satu kamera |
| PATCH | `/api/cameras/{id}` | Ubah `name`, `source`, `rotate`, `enabled`; kamera dinyalakan ulang bila perlu |
| DELETE | `/api/cameras/{id}` | Matikan dan hapus kamera. Nomornya tidak dipakai lagi |
| GET | `/api/cameras/{id}/stream` | Video MJPEG dengan kotak deteksi |
| GET | `/api/cameras/{id}/snapshot` | Satu gambar terakhir (JPEG), untuk gambar mini |
| GET | `/api/cameras/devices` | Kamera yang terpasang di komputer ini (webcam, Iriun) |
| POST | `/api/cameras/scan` | Pindai subnet lokal untuk mencari kamera IP |
| POST | `/api/cameras/{id}/simulate-fall` | Mode latihan: paksa observasi pemicu beberapa detik. `409` selama Mode perawatan |
| POST | `/api/cameras/{id}/jeda` | Mode perawatan. Body `{"menit": 1-120}`: mulai jeda, atau perpanjang jeda yang berjalan (sisa paling lama 120 menit). `409` bila kamera mati |
| DELETE | `/api/cameras/{id}/jeda` | Hentikan Mode perawatan lebih awal. Aman dipanggil bila tidak sedang dijeda |

Kata sandi di `source` disamarkan dalam jawaban (`rtsp://admin:***@10.0.0.5/s`).
Mengirim balik alamat tersamar itu lewat PATCH dianggap "tidak diubah".
`last_frame_at` adalah jam frame terakhir yang benar-benar diterima, jadi kamera yang
terputus menunjukkan sejak kapan ia buta.

---

## Settings

| Method | Endpoint | Keterangan |
|---|---|---|
| GET | `/api/settings/` | Konfigurasi aktif, pilihan model, pengaturan Telegram, daftar putusan dan alasan |
| PUT | `/api/settings/threshold` | `{"fall_duration_threshold": 3}` (lebih dari 0, paling besar 60) |
| PUT | `/api/settings/mode` | `{"detection_mode": "pose"}` atau `bbox`; mereset hitungan semua kamera |
| PUT | `/api/settings/telegram` | `{"photo_mode", "send_drills", "camera_offline"}`, semuanya opsional |
| GET | `/api/settings/pratinjau-ambang` | `?ambang=5&hari=30`: episode berbaring sungguhan dinilai ulang dengan ambang lain. `berbunyi`, `hilang` (alarm yang tidak lagi berbunyi, per putusan), `belum_tentu` (alarm yang ditutup sebelum ambang itu), `tambahan` (episode yang dulu tidak berbunyi, belum pernah dinilai) |
| PUT | `/api/settings/eskalasi` | `{"eskalasi_menit": 1-30}`: menit tanpa "Saya ke sana" sebelum banner menulis lamanya dan grup Telegram menerima pengingat. Bawaan 2; ikut dikembalikan `GET /api/settings/` |
| POST | `/api/settings/test-telegram` | Kirim pesan uji ke grup |

`photo_mode`: `buram` (bawaan), `utuh` (tertutup sampai diketuk), atau `tanpa`.
`send_drills` (bawaan `false`): latihan ikut dikirim ke Telegram. `camera_offline`
(bawaan `true`): kabari grup saat kamera terputus lebih dari 30 detik dan saat pulih.
Token bot dan ID grup hanya bisa diatur di `backend/.env`.

---

## WebSocket

### `WS /ws`

Wajib login: cookie sesi ikut terkirim saat jabat tangan. Tanpa sesi yang sah,
koneksi ditolak sebelum diterima.

| Event | Isi `data` | Kapan |
|---|---|---|
| `status_update` | status satu kamera (`camera_id`, `is_active`, `current_posture`, `fall_state`, `fall_duration`, `confidence`, `fps`, `last_frame_at`, `simulated`, `dijeda_sampai`, `dijeda_oleh`) | setiap frame diproses; selama Mode perawatan tiap setengah detik |
| `alert` | alert baru, bentuk sama dengan `GET /api/alerts/{id}` | jatuh terkonfirmasi atau latihan |
| `alert_update` | alert lengkap | ada yang menekan "Saya ke sana" atau mengubah putusan, dari dashboard atau Telegram |
| `alert_ack` | alert lengkap | alert ditandai ditangani; banner hilang di semua dashboard |
| `heartbeat` | `{"status": "pong"}` | jawaban untuk pesan `"ping"` dari klien |

Alert lama tidak dikirim ulang lewat WebSocket. Dashboard mengambil alarm yang belum
ditangani dalam 24 jam terakhir lewat `GET /api/alerts/?status=terbuka` setiap kali
tersambung, jadi banner tidak hilang saat halaman dimuat ulang.

---

## Tombol Telegram

Pesan alarm membawa tombol `Saya ke sana` dan `Alarm palsu`; setelah ada yang menuju
lokasi, tombolnya menjadi `Jatuh sungguhan`, `Alarm palsu`, dan `Belum yakin`.
`Alarm palsu` menampilkan pilihan alasan dulu. Backend menerima tekanan tombol lewat
long polling `getUpdates`, karena laptop tidak punya alamat publik untuk webhook,
dan hanya melayani tombol dari grup di `TELEGRAM_CHAT_ID`. Satu token bot hanya bisa
dilayani satu backend; backend kedua menerima `409` dari Telegram dan menunggu.

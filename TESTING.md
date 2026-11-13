# Panduan Pengujian Manual

Cara menjalankan sistem dari nol dan memastikan deteksi jatuh benar-benar bekerja.
Ditulis untuk anggota tim yang baru pertama kali menjalankan repo ini.

Dokumen ini melengkapi [README.md](README.md). Kalau keduanya berbeda, ikuti yang di sini —
dokumen ini ditulis setelah sistemnya benar-benar dijalankan dan diuji.

---

## Ringkasan 30 detik

```
run-backend.bat     ← klik dua kali, tunggu sampai muncul "Application startup complete"
run-frontend.bat    ← klik dua kali di jendela terpisah
```

Lalu buka di browser:

| Yang mau dilihat | Alamat |
|---|---|
| Dashboard | <http://localhost:5173> |
| **Video + bounding box** | <http://localhost:8000/api/cameras/cam-01/stream>, setelah masuk di dashboard |
| Dokumentasi API | <http://localhost:8000/docs> |

Masuk dengan **akun demo** dari `DEMO_USERNAME` dan `DEMO_PASSWORD` di `backend/.env`
(salin dari `backend/.env.example`). Backend membuat akun itu setiap kali menyala; kalau
keduanya kosong, halaman Login memberi tahu dan tidak ada yang bisa masuk. API, video, dan
WebSocket hanya bisa dibuka setelah masuk, dari browser yang sama. Pakai `localhost` untuk keduanya: sesi disimpan di cookie, dan cookie `localhost`
tidak terkirim ke `127.0.0.1`.

`cam-01` adalah kamera pertama pada database baru. Nomor kamera yang dihapus tidak dipakai lagi, jadi kalau kamera pernah dihapus, lihat nomornya di `GET /api/cameras/`.

---

## 1. Persiapan (sekali saja)

### Yang harus terpasang

| Kebutuhan | Versi | Catatan |
|---|---|---|
| Python | **3.12** | 3.13 dan 3.14 belum didukung `ultralytics`. Cek dengan `py -0p` |
| Node.js | 18+ | diuji dengan v24 |
| File model `best.pt` | — | minta ke anggota ML (model juara EXP-006) |

### Buat virtual environment

Venv ada di **root repo**, bukan di dalam `backend/`:

```powershell
cd nursing-home-fall-detection
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### Siapkan file model

File bobot `.pt` **tidak ikut di repo** (lihat `.gitignore`), jadi harus diminta ke anggota ML.
Model yang dipakai adalah juara **EXP-006** (`exp006_hybrid_adamw`).

Taruh file itu tepat di:

```
ml/models/fall_detection/weights/best.pt
```

Itu lokasi bawaan yang sudah dipakai `run-backend.bat` dan `backend/app/core/config.py`,
jadi tidak perlu mengubah pengaturan apa pun.

> **Pastikan dulu file model-nya benar** sebelum menjalankan backend. Bobot COCO bawaan YOLO
> (`yolo11n.pt`) berukuran mirip dan mudah tertukar, tapi isinya 80 kelas (`person`, `car`, dan
> seterusnya). Kalau yang tertukar itu dipakai, pemetaan kelas jadi kacau: `person` terbaca
> `normal` dan `car` terbaca `lying_on_ground`.
>
> ```powershell
> .venv\Scripts\python.exe -c "from ultralytics import YOLO; print(YOLO('ml/models/fall_detection/weights/best.pt').names)"
> ```
>
> Harus muncul tepat `{0: 'normal', 1: 'transitional', 2: 'lying_on_ground'}`.
> Kalau yang muncul 80 kelas, file-nya salah.

---

## 2. Atur sumber kamera

Ada dua jalur, dan untuk pemakaian sehari-hari **jalur dashboard yang dipakai**:

| Jalur | Kapan dipakai |
|---|---|
| **Dashboard → Daftar Kamera** | Mengganti alamat kamera, menambah kamera, memutar gambar. Tidak perlu me-restart server. |
| `run-backend.bat` | Hanya menentukan kamera **bawaan** saat database masih kosong. |

Daftar kamera disimpan di database (`backend/fall_detection.db`), jadi tetap ada setelah
server dimatikan. `CAMERA_SOURCE` di `run-backend.bat` hanya terpakai sekali, yaitu saat
tabel kameranya masih kosong.

### Mengelola kamera dari dashboard

Buka **Daftar Kamera** di sidebar.

- **Tambah** — isi nama ruang dan alamat kamera, tekan **Tambah kamera**. Untuk alamat
  `rtsp://` atau `http://` muncul kolom nama pengguna dan kata sandi kamera; sandinya
  tidak pernah ditampilkan lagi. Backend mencoba menghubungi sumbernya lebih dulu
  (maksimal 3 detik). Kalau tidak terjangkau, kamera **tidak jadi ditambahkan** dan
  alasannya ditampilkan, jadi salah ketik alamat langsung ketahuan.
- **Cari kamera** — memindai jaringan lokal untuk mencari perangkat yang menyiarkan kamera
  (port 8080, 4747, 8081, 554), sekaligus kamera yang terpasang di laptop. Satu subnet /24
  selesai dalam 1–3 detik, dan hasilnya tinggal diklik untuk mengisi kolom alamat.
- **Atur** — panel per kamera: rotasi (0/90/180/270, searah jarum jam) tepat di bawah
  pratinjau, ganti nama, ganti alamat, matikan atau nyalakan. Rotasi yang salah membuat
  orang berdiri terbaca berbaring dan memicu alarm palsu, jadi cek pratinjaunya.
- **Hapus** — ikon tempat sampah, dengan konfirmasi. Kamera langsung dimatikan. Nomornya
  tidak dipakai lagi, supaya riwayat alert lama tetap menunjuk kamera yang benar.

Tiap kamera menampilkan statusnya beserta alasan: **Terhubung** dengan fps dan jam
gambar terakhir, atau **Terputus sejak** jam tertentu. Kamera yang terdaftar otomatis
muncul di halaman **Pemantauan**, lengkap dengan stream dan bounding box-nya.

**Batas 4 kamera.** Inference berjalan di CPU, jadi setiap kamera menambah beban secara
linear. Batasnya bisa dinaikkan lewat `MAX_CAMERAS`, tapi ukur dulu FPS-nya. Catatan
tambahan: browser hanya mengizinkan sekitar 6 koneksi serentak ke satu host, dan setiap
stream yang terbuka memakai satu koneksi.

### Kamera bawaan lewat run-backend.bat

Blok **PENGATURAN** di bagian atas `run-backend.bat` hanya menentukan kamera pertama,
dan hanya saat database masih kosong.

```bat
set "CAMERA_SOURCE=http://10.252.129.120:8080/video"
set "CAMERA_ROTATE=90"
set "MODEL_PATH=%~dp0ml\models\fall_detection\weights\best.pt"
set "CONFIDENCE_THRESHOLD=0.25"
```

### Pilihan sumber kamera

Nilai yang sama berlaku baik di form **Daftar Kamera** maupun di `run-backend.bat`.

| Sumber | Nilai sumber | Rotasi |
|---|---|---|
| Webcam laptop | `0` | `0` |
| Kamera HP (Android) | `http://IP-HP:8080/video` | biasanya `90` |
| File video (uji ulang) | `D:\...\fall-01-cam0.mp4` | `0` |

### Menghubungkan kamera HP

HP bertindak sebagai **server kamera**, dan backend di laptop menariknya sebagai klien.
Keduanya harus berada di WiFi yang sama.

1. Pasang aplikasi **IP Webcam** (Android), lalu tekan **Start server**.
2. Catat alamat yang muncul di layar HP, misalnya `http://10.252.129.120:8080` — atau
   lewati langkah ini dan tekan **Cari kamera** di halaman Daftar Kamera.
3. Isi kolom alamat dengan alamat itu **ditambah `/video`**.

> **Supaya alamatnya berhenti berubah-ubah.** Alamat IP HP berganti setiap kali pindah
> WiFi (kos, kampus, rumah). Kalau laptop disambungkan ke **hotspot HP** — bukan
> sebaliknya — HP selalu menjadi gateway dan alamatnya sama di mana pun; di Android
> umumnya `192.168.43.1`. Cara ini sekaligus menghindari pemblokiran antar-perangkat
> di WiFi kampus. Cukup periksa sekali, simpan di dashboard, lalu tidak perlu diubah lagi.
4. Di pengaturan IP Webcam, turunkan resolusi ke **640×480**. Resolusi 1080p membuat
   inference di CPU melambat drastis.

Uji alamatnya sebelum menjalankan backend:

```powershell
.venv\Scripts\python.exe tools\check_camera.py "http://10.252.129.120:8080/video"
```

Hasil yang diharapkan: `Kamera OK (640x480).` Kalau gagal, pesannya menjelaskan penyebabnya —
alamat tidak terjangkau, nama host salah, file tidak ada, atau kamera sedang dipakai aplikasi lain.

Alat yang sama bisa dipakai untuk semua jenis sumber:

```powershell
.venv\Scripts\python.exe tools\check_camera.py "0"
.venv\Scripts\python.exe tools\check_camera.py "D:\...\fall-01-cam0.mp4"
```

`run-backend.bat` menjalankan pengecekan ini otomatis sebelum menyalakan server.

---

## 3. Jalankan

Klik dua kali `run-backend.bat`, atau dari terminal:

```powershell
.\run-backend.bat
```

Script akan mengecek venv, file model, dan koneksi kamera sebelum menyalakan server.
Tiga baris berikut menandakan semuanya siap:

```
Kamera OK.
📷 Camera cam-01 started (source=...)
✅ Model loaded: ...\ml\models\fall_detection\weights\best.pt
INFO:     Application startup complete.
```

Lalu jalankan `run-frontend.bat` di jendela terpisah.

Hentikan keduanya dengan **Ctrl+C**.

---

## 4. Memastikan sistem benar-benar bekerja

### a. Video bergerak, bukan gambar beku

Masuk ke dashboard, lalu buka <http://localhost:8000/api/cameras/cam-01/stream> di
browser yang sama. Gambar harus **bergerak**. Di halaman **Daftar Kamera**, jam
"gambar terakhir" tiap kamera juga harus terus maju.

Kalau diam total, jalankan ini untuk memastikan. Skrip ini meminta nama pengguna dan
kata sandi (tidak disimpan), lalu menghitung berapa frame yang benar-benar berbeda dalam
10 detik:

```powershell
.venv\Scripts\python.exe -c @'
import getpass, hashlib, time, httpx
with httpx.Client(base_url="http://localhost:8000", timeout=15) as c:
    c.post("/api/auth/login", json={"username": input("Nama pengguna: "), "password": getpass.getpass("Kata sandi: ")}).raise_for_status()
    data, akhir = b"", time.time() + 10
    with c.stream("GET", "/api/cameras/cam-01/stream") as r:
        for potong in r.iter_bytes():
            data += potong
            if time.time() > akhir:
                break
f = data.split(b"--frame")[1:]
print("frame:", len(f), "| unik:", len({hashlib.md5(x).hexdigest() for x in f}))
'@
```

Sehat kalau jumlah **unik** jauh lebih dari 1. Kalau unik = 1, koneksi kamera putus.

### b. Bounding box muncul

Kotak digambar oleh backend di dalam stream, jadi bentuknya langsung terlihat di video. Kotak
dan kerangkanya bertepi hitam supaya tetap terlihat di latar terang. Labelnya berupa kata, tanpa
angka keyakinan; nama kelas model dan keyakinannya ada di halaman Uji Kamera dan sakelar
**Tampilkan detail AI** di Pemantauan.

| Warna kotak | Label | Arti |
|---|---|---|
| Hijau | `tegak` | kelas `normal`, keyakinan di atas ambang |
| Oranye | `transisi` | kelas `transitional` |
| Merah | `berbaring` | kelas `lying_on_ground` |
| **Abu-abu** | kata yang sama + `(ragu)` | model mendeteksi, tapi keyakinan **di bawah** `CONFIDENCE_THRESHOLD` |

Kotak abu-abu itu disengaja. Tanpa itu, layar terlihat kosong dan kita tidak bisa membedakan
"model tidak melihat apa pun" dari "model melihat tapi kurang yakin".

### c. Status mengalir

Buka <http://localhost:8000/docs>, jalankan `POST /api/auth/login`, lalu
`GET /api/cameras/` di halaman yang sama. Nilai `fps`, `confidence`, `current_posture`,
dan `last_frame_at` harus **berubah** tiap kali dipanggil. Kalau angkanya persis sama
terus, kamera sedang membeku. Di dashboard, nyalakan **Tampilkan detail AI** di
Pemantauan untuk melihat keluaran model yang sama.

### d. State machine berpindah

Berbaring di depan kamera dan perhatikan `fall_state`:

```
monitoring  →  possible_fall  →  confirmed_fall
```

Dengan pengaturan bawaan, `possible_fall` muncul setelah 0,5 detik dan `confirmed_fall`
setelah 3 detik. Untuk produksi, nilai aslinya 2 detik dan 10 detik.

### e. Alert tersimpan dan ditangani

Banner merah muncul di semua halaman dashboard dan bunyi berulang tiap 4 detik.

1. Tekan **Saya ke sana**: banner berubah amber dengan nama Anda, dan bunyi berhenti di
   semua dashboard yang terbuka.
2. Tekan **Tandai Ditangani**, jawab **Apakah ini benar jatuh?** (alarm palsu wajib
   beralasan), isi catatan bila perlu, lalu simpan.
3. Buka **Riwayat Insiden**. Insiden tadi tercatat lengkap dengan penangan, waktu
   respons, putusan, status Telegram, dan foto kejadian di laci **Detail**.

Memuat ulang halaman tidak menghilangkan alarm yang belum ditangani.

Notifikasi browser: buka **Pengaturan → Suara dan notifikasi**, tekan **Izinkan notifikasi**,
lalu **Tes notifikasi**. Sesudah itu, picu alarm (mis. **Mode latihan**) lalu pindah ke aplikasi
lain: notifikasi muncul dengan nama ruang, dan hilang sendiri setelah ada yang menekan
**Saya ke sana**. Notifikasi hanya tersedia lewat `https://` (mis. tunnel pameran) atau
`localhost`, tidak lewat alamat IP biasa di jaringan lokal. Fitur ini untuk komputer jaga: Chrome
Android dan Safari iOS tidak menampilkan notifikasi dari halaman web biasa, dan perawat di HP
dikabari lewat Telegram.

Untuk mengatur posisi kamera, buka **Daftar Kamera → Uji** pada kamera itu. Halaman Uji Kamera
menampilkan semua deteksi, waktu inferensi, dan laju tangkap serta analisis. Nyalakan **Mode uji**
selama mencoba dengan tubuh sungguhan: alarm dari kamera itu dicatat sebagai latihan selama
10 menit, lalu ikuti skrip uji di bawahnya.

Tombol **Unduh CSV** di Riwayat Insiden mengunduh semua insiden sesuai tab dan filter,
lengkap dengan waktu respons dalam detik. Untuk menguji alur alarm dengan perawat atau
mahasiswa keperawatan, ikuti [docs/uji-mini.md](docs/uji-mini.md).

---

## 5. Notifikasi Telegram

### Menyiapkan bot (sekali saja)

1. Buat bot lewat [@BotFather](https://t.me/BotFather) dengan `/newbot`, lalu salin tokennya.
2. Salin templat `.env`, lalu isi tokennya:

   ```powershell
   copy backend\.env.example backend\.env
   ```

   Nama variabelnya harus **persis** seperti ini:

   ```
   TELEGRAM_BOT_TOKEN=<token dari BotFather>
   ```

3. Buat grup untuk perawat, masukkan botnya, lalu kirim `/start@NamaBot_bot` **di dalam grup
   itu**. Bot Telegram tidak bisa mengirim pesan ke pihak yang belum menyapanya, dan di grup
   bot hanya melihat pesan yang menyebut namanya — `/start` saja tidak cukup.
4. Ambil `chat_id`-nya **segera setelah** mengirim pesan tadi:

   ```powershell
   .venv\Scripts\python.exe tools\get_chat_id.py
   ```

   Lalu simpan yang grup (nilainya negatif):

   ```powershell
   .venv\Scripts\python.exe tools\get_chat_id.py --simpan -1001234567890
   ```

5. Jalankan ulang backend supaya `.env` yang baru terbaca.

> **Urutannya penting.** Antrean update Telegram kedaluwarsa setelah 24 jam. Kirim pesan
> dulu, baru jalankan skripnya — bukan sebaliknya. Kalau daftarnya kosong, jalankan
> `tools\get_chat_id.py --diagnosa`: ia menyebutkan bot pemilik token, status webhook, dan
> jumlah update, sehingga penyebabnya langsung ketahuan.

### Menguji koneksinya

Masuk ke dashboard, buka **Pengaturan → Telegram**, lalu tekan **Kirim pesan uji**.
Yang diharapkan: tulisan "Pesan uji terkirim. Cek grup Telegram-mu." dan satu pesan masuk
ke grup. Kalau statusnya **Belum diatur**, token atau `chat_id`-nya belum terbaca —
periksa nama variabelnya di `backend/.env` dan jalankan ulang backend.

Lewat API: buka <http://localhost:8000/docs>, jalankan `POST /api/auth/login`, lalu
`POST /api/settings/test-telegram` di halaman yang sama.

### Uji sungguhan

Berbaringlah di depan kamera lebih lama dari `FALL_DURATION_THRESHOLD`. Yang seharusnya
terjadi, berurutan:

1. Dashboard menyala **seketika** lewat WebSocket
2. Beberapa detik kemudian, pesan **Kemungkinan jatuh** masuk ke grup Telegram dengan foto
   yang diburamkan, nama ruang, lama terbaca berbaring, jam, dan tombol **Saya ke sana**
   serta **Alarm palsu**
3. Menekan **Saya ke sana** di Telegram mengubah banner di dashboard menjadi amber dengan
   nama Anda berakhiran "(Telegram)", dan pesan di grup ikut disunting
4. Riwayat Insiden menunjukkan Telegram **Terkirim**
5. Sesudah alarm ditutup, pesan di grup diakhiri "Balas pesan ini untuk menambah catatan".
   Balas pesan alarm itu dengan teks: balasan Anda mendapat reaksi 👍, dan laci **Detail**
   insiden itu menampilkan catatan "Nama Anda (Telegram): isi balasan"

Hanya satu backend yang bisa menerima tombol untuk satu token bot. Kalau dua laptop
menjalankan backend dengan token yang sama, tombol dilayani salah satunya saja.

Urutan itu disengaja: Telegram dikirim setelah dashboard diberi tahu, jadi gangguan
jaringan tidak pernah menunda peringatan di layar.

### Kalau Telegram gagal

| Gejala | Penyebab |
|---|---|
| `dikonfigurasi: false` | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` belum terbaca. Nama variabelnya harus persis, dan backend perlu dijalankan ulang setelah `.env` diubah |
| `terkirim: false`, log menyebut koneksi | Tidak ada internet. Ini yang terjadi kalau laptop jadi hotspot tanpa tersambung WiFi lain |
| HTTP 400 dari Telegram | `chat_id` salah, atau bot sudah dikeluarkan dari grup |
| HTTP 403 | Bot diblokir, atau belum pernah disapa di chat tujuan |

Kegagalan Telegram **tidak** membatalkan alert: barisnya tetap tersimpan dan dashboard
tetap menyala, hanya `notified` bernilai `false`. Itu disengaja — notifikasi yang gagal
diam-diam jauh lebih berbahaya daripada yang gagal terang-terangan.

---

## 6. Masalah yang sering terjadi

### Video hanya satu gambar diam

Koneksi kamera putus dan tidak tersambung ulang. Sudah diperbaiki: backend kini menyambung
ulang otomatis, dan frame yang lebih tua dari 3 detik dianggap basi sehingga kamera dilaporkan
OFFLINE. Kalau masih terjadi, periksa aplikasi IP Webcam di HP masih menyala.

### Tidak ada bounding box sama sekali

Pastikan alamat yang dibuka benar. Ini kekeliruan yang paling sering:

| Alamat | Isi |
|---|---|
| `10.252.129.120:**8080**/video` | siaran mentah dari HP, **tanpa** kotak |
| `localhost:**8000**/api/cameras/cam-01/stream` | hasil olahan backend, **dengan** kotak (setelah masuk) |

Singkatnya: port **8080** itu HP, port **8000** itu backend.

### Kotak jarang muncul atau keyakinannya rendah

Model dilatih pada dataset URFD yang hanya berisi satu ruangan, jadi keyakinannya turun di
ruangan lain. Yang bisa dicoba:

1. Mundurkan kamera supaya **seluruh tubuh** masuk frame. Wajah yang memenuhi layar tidak
   dikenali sebagai orang utuh.
2. Turunkan `CONFIDENCE_THRESHOLD` ke `0.1`.

### `Gagal membuka kamera`

- **Webcam laptop:** tutup aplikasi lain yang memakainya, misalnya browser, Zoom, atau aplikasi Kamera.
- **Kamera HP:** periksa IP-nya. Alamat HP bisa berubah setelah tersambung ulang ke WiFi.

### Kamera HP tidak terjangkau padahal IP sudah benar (WiFi kampus)

Banyak WiFi kampus dan hotel memakai **client isolation**: setiap perangkat bisa mengakses
internet, tapi **tidak bisa saling menghubungi**. Di jaringan seperti ini kamera HP mustahil
ditarik backend, berapa pun IP-nya diubah.

Cara memastikan ini penyebabnya:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '10.*' }
ping <IP-HP>
ping <IP-gateway>
```

Tandanya: **gateway terjangkau, klien lain tidak satu pun**.

Hasil pengukuran nyata di `eepiswlan` (8 Oktober 2026), laptop `10.252.144.87`:

| Tujuan | Hasil |
|---|---|
| Gateway `10.252.144.2` | ping 3 ms, port 80 terbuka seketika |
| HP `10.252.151.81` | ping 100% hilang, TCP 8080 timeout |
| Empat tetangga lain di `10.252.144.x` (ada di tabel ARP) | tidak satu pun membalas ping |
| Sapuan port 8080 ke seluruh `10.252.144.0/21` | hanya `10.252.144.1` (perangkat jaringan) |

Perhatikan baris ketiga: tetangga yang **muncul di tabel ARP pun tidak bisa dihubungi**.
Jadi yang diblokir adalah lalu lintas antar-klien, bukan sekadar soal alamat.

> **Oktet ketiga yang berbeda itu normal, bukan penyebab masalah.** Di `eepiswlan` maskernya
> `255.255.248.0` (/21), jadi satu subnet membentang dari `10.252.144.0` sampai
> `10.252.151.255` — 2046 alamat. DHCP membagikan alamat mana saja dari kolam itu, sehingga
> laptop bisa dapat `10.252.144.87` dan HP dapat `10.252.151.81` walau tersambung ke SSID
> yang sama. Keduanya **tetap satu subnet**. Jangan membuang waktu mencoba menyamakan oktet
> ketiganya.

Solusinya, berurutan dari yang paling mudah:

1. **Hotspot HP.** Nyalakan hotspot di HP, lalu sambungkan laptop ke hotspot itu. HP menjadi
   gateway sehingga pasti terjangkau. Jalankan IP Webcam seperti biasa dan pakai alamat baru
   yang muncul. Ini cara paling andal untuk demo.
2. **USB tethering.** Sambungkan HP ke laptop dengan kabel USB lalu nyalakan USB tethering.
   Tidak bergantung WiFi sama sekali.
3. **WiFi pribadi** (router rumah atau MiFi) yang tidak mengaktifkan isolasi.
4. **Tailscale.** Pasang Tailscale di HP dan laptop dengan akun yang sama, lalu pakai alamat
   `100.x.y.z` milik HP. Tetap jalan walaupun jaringannya terisolasi.

Selama belum bisa, pakai sumber `0` (webcam laptop) atau file video supaya pengujian
backend tetap bisa berjalan.

### Alamat bisa dihubungi tapi kamera tetap gagal

Alamat yang ditampilkan aplikasi IP Webcam di layar HP (`http://10.252.151.81:8080`) adalah
**halaman webnya**, bukan aliran videonya. Yang dibutuhkan adalah alamat itu **ditambah
`/video`**. Tanpa itu, pemeriksaan koneksi lolos tapi OpenCV tidak mendapat gambar.

Backend sekarang menangkap kekeliruan ini saat kamera ditambahkan: kalau alamatnya
mengembalikan halaman HTML, kamera ditolak dan pesannya langsung menyebutkan alamat
lengkap yang seharusnya dipakai.

### Gambar dari HP miring 90 derajat

Atur `CAMERA_ROTATE` ke `90`, `180`, atau `270` di `run-backend.bat`.

### FPS sangat rendah (di bawah 2)

Turunkan resolusi di aplikasi IP Webcam menjadi 640×480. Inference berjalan di CPU, dan
gambar 1080p memakan waktu berkali-kali lipat.

### `UnicodeEncodeError` di terminal

Sudah tidak terjadi. Backend memakai `logging` dengan UTF-8, bukan `print()`.

---

## 7. Menjalankan test otomatis

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests\ -q
```

Saat ini **190 test** dan semuanya harus lulus. Tidak ada yang menghubungi Telegram, kamera, atau internet sungguhan: semuanya memakai server tiruan dan database di memori.

---

## 8. Yang belum berfungsi

Supaya tidak ada yang mengira ini bug baru:

| Bagian | Status |
|---|---|
| Peran perawat | Hanya pengelolaan akun yang dibatasi. Perawat masih bisa mengubah kamera dan pengaturan |
| Tombol Buka dashboard di Telegram | Hanya muncul kalau `DASHBOARD_URL` diisi dengan alamat yang bisa dibuka dari HP |
| Alarm lama di banner | Hanya alarm 24 jam terakhir yang muncul lagi setelah dimuat ulang; yang lebih tua ada di antrean Riwayat Insiden |

Akurasi prediksi postur juga masih rendah di luar dataset URFD. Itu keterbatasan dataset,
bukan kesalahan backend.

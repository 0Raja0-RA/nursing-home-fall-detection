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
| **Video + bounding box** | <http://127.0.0.1:8000/api/cameras/cam-01/stream> |
| Dokumentasi API | <http://127.0.0.1:8000/docs> |
| Dashboard | <http://localhost:5173> |

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
| **Dashboard → Kelola Kamera** | Mengganti alamat kamera, menambah kamera, memutar gambar. Tidak perlu me-restart server. |
| `run-backend.bat` | Hanya menentukan kamera **bawaan** saat database masih kosong. |

Daftar kamera disimpan di database (`backend/fall_detection.db`), jadi tetap ada setelah
server dimatikan. `CAMERA_SOURCE` di `run-backend.bat` hanya terpakai sekali, yaitu saat
tabel kameranya masih kosong.

### Mengelola kamera dari dashboard

Buka **Kelola Kamera** di sidebar.

- **Tambah** — isi nama dan sumber, tekan **Tambah Kamera**. Backend mencoba menghubungi
  sumbernya lebih dulu (maksimal 3 detik). Kalau tidak terjangkau, kamera **tidak jadi
  ditambahkan** dan alasannya ditampilkan, jadi salah ketik alamat langsung ketahuan.
- **Pindai** — tombol di sebelah Tambah Kamera memindai jaringan lokal untuk mencari
  perangkat yang menyiarkan kamera (port 8080, 4747, 8081, 554). Satu subnet /24 selesai
  dalam 1–3 detik, dan hasilnya tinggal diklik untuk mengisi kolom alamat. Ini
  menghilangkan keharusan membaca alamat IP dari layar HP setiap kali berpindah WiFi.
- **Rotasi** — dropdown di tiap baris (0/90/180/270, searah jarum jam). Nilainya **per
  kamera**, jadi kamera HP bisa 90° sementara webcam laptop tetap 0°.
- **Hapus** — ikon tempat sampah. Kamera langsung dimatikan.

Kamera yang terdaftar otomatis muncul di halaman **Simulasi Live**, lengkap dengan stream
dan bounding box-nya.

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

Nilai yang sama berlaku baik di form **Kelola Kamera** maupun di `run-backend.bat`.

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
   lewati langkah ini dan tekan **Pindai** di halaman Kelola Kamera.
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

Buka <http://127.0.0.1:8000/api/cameras/cam-01/stream>. Gambar harus **bergerak**.

Kalau diam total, jalankan ini untuk memastikan — perintah ini menghitung berapa frame
yang benar-benar berbeda dalam 10 detik:

```powershell
curl.exe -s -m 10 http://127.0.0.1:8000/api/cameras/cam-01/stream -o s.bin
.venv\Scripts\python.exe -c "import hashlib; d=open('s.bin','rb').read(); f=d.split(b'--frame')[1:]; h=[hashlib.md5(x).hexdigest() for x in f]; print('frame:', len(f), '| unik:', len(set(h)))"
```

Sehat kalau jumlah **unik** jauh lebih dari 1. Kalau unik = 1, koneksi kamera putus.

### b. Bounding box muncul

Kotak digambar oleh backend di dalam stream, jadi bentuknya langsung terlihat di video.

| Warna kotak | Arti |
|---|---|
| Hijau | `normal`, keyakinan di atas ambang |
| Oranye | `transitional` |
| Merah | `lying_on_ground` |
| **Abu-abu + `(ragu)`** | model mendeteksi, tapi keyakinan **di bawah** `CONFIDENCE_THRESHOLD` |

Kotak abu-abu itu disengaja. Tanpa itu, layar terlihat kosong dan kita tidak bisa membedakan
"model tidak melihat apa pun" dari "model melihat tapi kurang yakin".

### c. Status mengalir

```powershell
curl.exe -s http://127.0.0.1:8000/api/cameras/
```

Nilai `fps`, `confidence`, dan `current_posture` harus **berubah** tiap kali dipanggil.
Kalau angkanya persis sama terus, kamera sedang membeku.

### d. State machine berpindah

Berbaring di depan kamera dan perhatikan `fall_state`:

```
monitoring  →  possible_fall  →  confirmed_fall
```

Dengan pengaturan bawaan, `possible_fall` muncul setelah 0,5 detik dan `confirmed_fall`
setelah 3 detik. Untuk produksi, nilai aslinya 2 detik dan 10 detik.

### e. Alert tersimpan

```powershell
curl.exe -s http://127.0.0.1:8000/api/alerts/
```

---

## 5. Masalah yang sering terjadi

### Video hanya satu gambar diam

Koneksi kamera putus dan tidak tersambung ulang. Sudah diperbaiki: backend kini menyambung
ulang otomatis, dan frame yang lebih tua dari 3 detik dianggap basi sehingga kamera dilaporkan
OFFLINE. Kalau masih terjadi, periksa aplikasi IP Webcam di HP masih menyala.

### Tidak ada bounding box sama sekali

Pastikan alamat yang dibuka benar. Ini kekeliruan yang paling sering:

| Alamat | Isi |
|---|---|
| `10.252.129.120:**8080**/video` | siaran mentah dari HP, **tanpa** kotak |
| `127.0.0.1:**8000**/api/cameras/cam-01/stream` | hasil olahan backend, **dengan** kotak |

Singkatnya: port **8080** itu HP, port **8000** itu backend.

### Kotak jarang muncul atau keyakinannya rendah

Model dilatih pada dataset URFD yang hanya berisi satu ruangan, jadi keyakinannya turun di
ruangan lain. Yang bisa dicoba:

1. Mundurkan kamera supaya **seluruh tubuh** masuk frame. Wajah yang memenuhi layar tidak
   dikenali sebagai orang utuh.
2. Turunkan `CONFIDENCE_THRESHOLD` ke `0.1`.

### `Gagal membuka kamera`

- **Webcam laptop:** tutup aplikasi lain yang memakainya, termasuk tab browser yang membuka
  halaman "Testing Kamera HP" (halaman itu memakai kamera browser).
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

## 6. Menjalankan test otomatis

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests\ -q
```

Saat ini **13 test** dan semuanya harus lulus.

---

## 7. Yang belum berfungsi

Supaya tidak ada yang mengira ini bug baru:

| Bagian | Status |
|---|---|
| Notifikasi Telegram | **Belum tersambung.** `alert_service.py` baru berisi TODO, jadi kolom `notified` di database selalu `0` |
| Halaman "Simulasi Live" | Masih simulasi, belum menampilkan kamera sungguhan |
| Halaman "Kelola Kamera" | Masih data contoh di browser, belum tersambung backend |
| Jumlah kamera | Baru satu (`cam-01`), ditetapkan di `main.py` |
| Riwayat alert di WebSocket | Alert lama tidak dikirim ulang ke klien baru. Ambil lewat `GET /api/alerts/` |

Akurasi prediksi postur juga masih rendah di luar dataset URFD. Itu keterbatasan dataset,
bukan kesalahan backend.

# FallDetect - Frontend Dashboard (Caregiver Interface)

Antarmuka *frontend* berbasis web untuk sistem **Fall Detection** (Deteksi Jatuh Lansia) yang dirancang menggunakan **React, Vite, Tailwind CSS**, dan **Lucide React**. Antarmuka ini dikhususkan bagi perawat/pengawas (*caregiver*) untuk memantau kondisi lansia secara *real-time*, menguji kamera perangkat keras, dan melihat riwayat insiden.

---

## 🚀 Fitur Utama
1. **Landing Page Interaktif**: Halaman sambutan utama yang memperkenalkan sistem pemantauan berbasis AI/YOLO11.
2. **Autentikasi Caregiver**: Halaman login aman dengan akun simulasi untuk hak akses perawat.
3. **Simulasi Live Monitoring CCTV**: Dasbor utama untuk memantau status ruangan, tingkat *confidence* model deteksi postur, serta fitur pemicu simulasi jatuh darurat.
4. **Testing Kamera Perangkat (Live Camera)**: Fitur pengujian kamera secara langsung (*real-time*) menggunakan perangkat HP atau laptop via WebRTC, lengkap dengan tombol putar kamera (depan/belakang) dan simulasi deteksi jatuh interaktif.
5. **Manajemen Kamera & Pengaturan**: Halaman untuk mengelola daftar kamera CCTV dan konfigurasi sistem.
6. **Riwayat Insiden**: Log riwayat kejadian jatuh lengkap dengan catatan waktu dan status penanganan.
7. **Dark / Light Mode**: Dukungan tema gelap dan terang secara dinamis menggunakan *Context API* dan Tailwind CSS.
8. **Responsif & Sidebar Collapsible**: Tata letak yang ramah perangkat seluler dengan menu navigasi geser (*drawer*).

---

## 🛠️ Teknologi yang Digunakan
* **React.js (Vite)** sebagai pustaka antarmuka utama
* **Tailwind CSS** untuk perancangan tata letak dan gaya responsif
* **React Router DOM** untuk pengelolaan navigasi rute halaman
* **Lucide React** untuk ikon antarmuka modern
* **WebRTC API (`getUserMedia`)** untuk streaming kamera perangkat keras secara langsung

---

## 📦 Cara Menjalankan Proyek (Development)

Ikuti langkah-langkah berikut di terminal untuk menjalankan aplikasi di komputer lokal:

1. **Masuk ke folder frontend:**
   ```bash
   cd frontend

2. **Instal dependensi yang diperlukan:**
   ```bash
   npm install

3. **Jalankan server pengembangan lokal (mendukung akses jaringan lokal/HP):**
   ```bash
   npm run dev -- --host
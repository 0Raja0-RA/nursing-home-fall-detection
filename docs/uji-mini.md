# Uji mini FallDetect

Panduan menjalankan uji singkat dengan 3–5 perawat atau mahasiswa keperawatan, untuk
mengukur apakah alur alarm FallDetect benar-benar membantu orang menolong, bukan hanya
seberapa akurat modelnya. Uji ini adalah butir pertama rencana lanjutan di laporan riset
UI/UX. Skenario dan pertanyaan di bawah adalah usulan; sesuaikan dengan ruang dan kamera
yang tersedia.

## Yang diukur

| Ukuran | Cara mengukur | Sumber |
|---|---|---|
| Waktu sampai diakui | Kolom `detik_sampai_respons`: dari alarm sampai `Saya ke sana`, atau sampai `Tandai Ditangani` bila tidak ada yang mengklaim | CSV dari Riwayat Insiden |
| Waktu sampai di lokasi | Stopwatch pengamat, dari alarm muncul sampai peserta masuk ruang uji | Lembar pengamatan |
| Persentase alarm benar | Alarm pada skenario jatuh dibagi semua alarm. Skenario jatuh yang tidak memicu alarm dicatat lewat `Catat jatuh terlewat` | CSV dan daftar skenario |
| Ketepatan putusan peserta | Putusan dan alasan peserta dibandingkan dengan kenyataan skenario | CSV dan daftar skenario |
| Keyakinan pengguna | Skala 1–5 sesudah tiap alarm dan di akhir sesi | Kuesioner |

## Peserta dan peran

- **Peserta:** 3–5 perawat atau mahasiswa keperawatan, bukan anggota tim. Satu peserta per sesi.
- **Fasilitator** (anggota tim): menjelaskan sistem, memberi isyarat ke aktor, menjaga urutan skenario.
- **Aktor** (anggota tim atau relawan): memerankan kejadian di depan kamera.
- **Pengamat:** memegang stopwatch dan lembar pengamatan. Boleh dirangkap fasilitator.

Jangan melibatkan penghuni panti. Aktor dan peserta menyetujui perekaman secara tertulis
sebelum mulai. Di semua catatan, peserta ditulis dengan kode (P1–P5), bukan nama.

## Persiapan

1. Pisahkan **ruang uji** (tempat kamera dan aktor) dari **pos peserta**: beda ruangan atau
   di balik sekat, supaya peserta harus memakai FallDetect dan berjalan ke lokasi.
2. Jalankan backend dan dashboard di laptop (`run-backend.bat` dan `run-frontend.bat`),
   lalu taruh laptop di pos peserta. Masuk dengan akun demo, tekan `Aktifkan suara`, lalu
   `Tes suara` di Pemantauan, dan pastikan bunyinya terdengar dari tempat peserta duduk.
3. Hubungkan Telegram ke grup uji, bukan grup panti sungguhan. Peserta bergabung dari HP-nya
   atau memakai HP yang disiapkan tim.
4. Gelar matras tebal di depan kamera. Aktor tidak perlu jatuh keras: FallDetect menilai
   postur tergeletak dan lamanya, bukan benturan, jadi cukup merebahkan diri ke matras.
5. Catat ambang dan mode deteksi di Pengaturan. Nilai saat kejadian juga tercatat di setiap
   alarm (`ambang_detik`, `mode_deteksi` di CSV).
6. Coba sekali tanpa peserta: jalankan skenario J1 dan pastikan alarm muncul di dashboard
   dan Telegram. Tutup alarm uji coba itu dengan putusan `Belum yakin` dan catatan
   "uji coba", supaya mudah dibuang saat mengolah data.
7. Cetak lembar pengamatan dan kuesioner (templat di bawah).

## Skenario usulan

Urutan diacak per peserta. Satu peserta sekitar 30 menit.

| Kode | Yang diperankan aktor | Kenyataan | Harapan |
|---|---|---|---|
| J1 | Jatuh ke depan, lalu diam di matras 20 detik | Jatuh | Alarm |
| J2 | Bangkit dari kursi, terduduk, lalu rebah miring dan diam 20 detik | Jatuh | Alarm |
| J3 | Terpeleset ke belakang, mencoba bangun tetapi tetap tergeletak 20 detik | Jatuh | Alarm |
| P1 | Berbaring sengaja di matras seperti tidur, 30 detik | Bukan jatuh: berbaring sengaja | Idealnya tanpa alarm |
| P2 | Jongkok atau membungkuk mengambil barang di lantai, 20 detik | Bukan jatuh: duduk atau membungkuk | Tanpa alarm |
| P3 | Rebah, lalu bangun sendiri sebelum ambang tercapai | Bukan jatuh | Tanpa alarm |

Peserta hanya diberi tahu bahwa alarm bisa benar atau palsu, dan bahwa mereka menilainya
sendiri dari kamera. Daftar skenario tidak diperlihatkan.

## Jalannya satu sesi

1. **Penjelasan (5 menit).** Apa yang dilakukan FallDetect, lalu tiga tindakan: `Lihat
   kamera`, `Saya ke sana`, dan `Tandai Ditangani` dengan putusan. Tunjukkan juga tombol
   yang sama di Telegram.
2. **Latihan.** Jalankan `Mode latihan` sekali supaya peserta mengenal tombolnya. Alarm
   latihan tercatat sebagai latihan dan tidak ikut dihitung.
3. **Skenario.** Peserta menunggu di pos sambil mengerjakan tugas lain, misalnya mengisi
   formulir. Untuk tiap skenario:
   - Fasilitator memberi isyarat ke aktor tanpa diketahui peserta, dan mencatat jamnya.
   - Pengamat menyalakan stopwatch saat banner atau bunyi alarm muncul, lalu mencatat
     detik saat peserta masuk ruang uji. Bila tidak ada alarm dalam 60 detik, tulis
     "tidak ada alarm", dan sesudah sesi catat skenario itu di Riwayat Insiden lewat
     `Catat jatuh terlewat`, dengan jam isyaratnya sebagai perkiraan waktu kejadian.
   - Peserta merespons seperti biasa: melihat kamera, mengklaim, berjalan ke ruang uji,
     menolong (cukup menyentuh bahu aktor), lalu menutup alarm dengan putusan dari
     dashboard atau Telegram, mana saja yang ia pilih.
   - Sesudah menutup alarm, peserta menjawab satu pertanyaan keyakinan.
   - Jeda 1–2 menit. Pastikan banner kosong sebelum skenario berikutnya.
4. **Akhir sesi.** Kuesioner akhir dan wawancara singkat (5–10 menit).
5. Catat jam mulai dan selesai sesi, untuk memilah baris CSV per peserta.

## Kuesioner

**Sesudah tiap alarm:** "Seberapa yakin Anda bahwa putusan Anda untuk alarm ini benar?"
1 (tidak yakin) sampai 5 (sangat yakin).

**Akhir sesi**, skala 1 (sangat tidak setuju) sampai 5 (sangat setuju):

1. Saat alarm muncul, saya langsung tahu ruang mana yang bermasalah.
2. Dari kamera, saya bisa menilai apakah orangnya benar jatuh.
3. Saya tahu apa yang harus ditekan setelah menolong.
4. Pesan Telegram cukup untuk bertindak tanpa membuka dashboard.
5. Saya akan mengandalkan sistem ini saat jaga malam.

Pertanyaan terbuka: apa yang paling membingungkan, dan apa yang harus diubah lebih dulu?
Bila ingin skor kegunaan yang bisa dibandingkan dengan sistem lain, tambahkan System
Usability Scale (SUS).

## Lembar pengamatan

| Peserta | Urutan | Skenario | Jam isyarat | Alarm muncul? | Detik sampai tiba | Ditutup lewat | Catatan |
|---|---|---|---|---|---|---|---|
| P1 | 1 | | | | | Dashboard / Telegram | |

## Mengolah hasil

1. Buka Riwayat Insiden, tab `Semua`, rentang `24 jam terakhir`, lalu tekan `Unduh CSV`.
   Latihan tidak ikut kecuali `Tampilkan latihan` dicentang. Waktu di CSV memakai jam
   laptop yang menjalankan backend.
2. Cocokkan tiap baris dengan lembar pengamatan lewat `waktu_alarm` dan jam sesi peserta.
   Buang baris uji coba.
3. Hitung:
   - **Waktu sampai diakui:** median `detik_sampai_respons` pada skenario J, ditambah
     nilai terkecil dan terbesar. Dengan sedikit peserta, rata-rata mudah tertarik satu
     angka ekstrem.
   - **Waktu sampai di lokasi:** median dari lembar pengamatan, dengan cara yang sama.
   - **Alarm benar:** tulis dalam angka mutlak, misalnya "9 dari 12 alarm terjadi pada
     skenario jatuh", ditambah jumlah skenario jatuh yang terlewat (baris CSV dengan
     `terlewat` = `ya`; kartu "Jatuh terdeteksi" menampilkan keduanya). Persentase dari
     jumlah sekecil ini mudah menyesatkan.
   - **Ketepatan putusan:** berapa putusan (`putusan`, `alasan_palsu`) yang sesuai
     kenyataan skenario.
   - **Keyakinan:** median skor tiap pertanyaan.
4. Tulis temuan sebagai daftar masalah: apa yang terjadi, berapa peserta mengalaminya,
   dan usulan perbaikannya.

## Batasan

- Uji ini untuk menemukan masalah besar dalam alur, bukan untuk mengukur akurasi model.
- Aktor bukan lansia, dan gerak jatuh lansia sungguhan bisa berbeda. Jangan menulis hasil
  uji ini sebagai akurasi FallDetect di panti.

## Privasi dan keamanan

- Foto kejadian aktor tersimpan di database. Supaya data uji tidak bercampur dengan data
  demo, backend bisa dijalankan dengan database terpisah: sebelum `run-backend.bat`,
  jalankan `set DATABASE_URL=sqlite+aiosqlite:///./uji_mini.db` di jendela yang sama.
  Database baru dimulai kosong, jadi kamera dan pengaturan perlu diisi ulang.
- Aktor jatuh hanya ke matras dan boleh berhenti kapan saja.
- CSV berisi nama penangan dan catatan. Simpan di folder tim, jangan di repo.

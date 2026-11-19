# Video untuk kamera di Docker

Folder ini dipasang ke container sebagai `/app/video` (baca-saja). Webcam laptop tidak bisa
dibuka dari dalam Docker di Windows, jadi kamera di Docker memakai video dari sini atau kamera HP
lewat jaringan.

1. Taruh video (mp4) di folder ini, misalnya `contoh.mp4`. Video diputar ulang dari awal setiap
   kali habis.
2. Isi `CAMERA_SOURCE=/app/video/contoh.mp4` di `deployment/.env` sebelum start pertama, atau
   tambahkan kamera dengan sumber itu dari halaman Daftar Kamera.

Isi folder ini selain README ini tidak ikut git (lihat `.gitignore`), supaya video berukuran
besar atau yang memuat wajah orang tidak ikut terunggah ke repo publik.

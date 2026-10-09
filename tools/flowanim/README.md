# flowanim — flowchart Excalidraw jadi GIF beranimasi

Menghasilkan `docs/assets/flow-detection.gif` dan `docs/assets/flow-api.gif`
dari dua berkas sumber di `docs/flow/`.

```bash
python tools/flowanim/build.py          # .excalidraw -> HTML beranimasi
node tools/flowanim/capture.mjs flow-detection
node tools/flowanim/capture.mjs flow-api
```

Butuh **puppeteer** (terpasang global: `npm i -g puppeteer`) dan **ffmpeg** di PATH.
Keluaran sementara ada di `build/flowanim/` yang sudah masuk `.gitignore`.

Dua diagram lain -- `flowchart-arsitektur` dan `flowchart-state-machine` -- tidak
dianimasikan. Keduanya diekspor manual sebagai PNG dari excalidraw.com
(`docs/assets/architecture.png` dan `state-machine.png`), jadi tidak lewat
perkakas ini sama sekali.

## Kenapa dibikin begini

**Kenapa menggambar ulang SVG-nya sendiri, bukan ekspor SVG dari excalidraw.com?**
Hasil ekspor excalidraw adalah satu gambar utuh tanpa pegangan per elemen, jadi
tidak bisa dianimasikan node per node. Kedua diagram ini dibuat dengan
`roughness: 0` — bentuknya geometris bersih, bukan sketsa tangan — sehingga
menggambar ulangnya cuma soal rect / ellipse / diamond / polyline. Tidak perlu
roughjs. Yang dibaca dari berkasnya: `containerId` (teks milik node mana),
`startBinding` / `endBinding` (panah menghubungkan apa ke apa), dan `points`.

**Kenapa kameranya bergeser, padahal itu memperbesar berkas?**
Kanvasnya 4500–4900 px, jadi tiap bab harus dibingkai sendiri supaya teksnya
terbaca. Pertanyaannya cuma: pindah antar bab dengan memotong, atau menggeser.

Versi pertama memotong, dan itu **jauh lebih kecil** — kamera diam membuat
mayoritas piksel identik antar frame, sehingga `palettegen=stats_mode=diff` +
`paletteuse=diff_mode=rectangle` hanya perlu menulis bagian yang berubah.
Tapi memotong membuat mata kehilangan jejak: tiap bab ada di bagian kanvas yang
berbeda dan tidak ada petunjuk ke mana perpindahannya, jadi terasa meloncat.

Sekarang kameranya menggeser dan mem-posisi ulang, dibuka dengan tampilan utuh
lebih dulu supaya penonton punya peta sebelum masuk ke detail. Harganya nyata:

| | frame | kamera memotong | kamera bergeser |
|---|---|---|---|
| `flow-detection.gif` | 441 → 588 | 1,4 MB | **4,1 MB** |
| `flow-api.gif` | 374 → 510 | 1,1 MB | **4,2 MB** |

Selisihnya datang dari ~230 frame yang kameranya sedang bergerak; pada frame itu
setiap piksel berubah dan kompresi antar-frame tidak membantu sama sekali.

**Mengecilkan lebar keluaran TIDAK menolong** — sudah diukur, bukan dikira:
`--width 1040` menghasilkan 4,13 MB dan 4,32 MB, yaitu sedikit lebih BESAR.
Penskalaan lanczos menambah warna antara pada gambar bergaris, dan kerugiannya
di palet melebihi untungnya dari pengurangan piksel. Kalau ukurannya perlu
ditekan, yang berpengaruh adalah memperpendek `TRANS_MS`/`INTRO_MS` di
`build.py` (frame bergeraknya berkurang), bukan memperkecil gambar.

**Kenapa frame di-set manual, bukan direkam real-time?**
`capture.mjs` memanggil `window.__setFrame(n)` satu per satu, bukan merekam
layar. Jadi frame ke-N selalu identik setiap kali dijalankan — tidak ada frame
yang keburu terlewat kalau mesinnya sedang sibuk. Di halaman HTML tidak ada
transisi CSS maupun `requestAnimationFrame` saat mode capture; semua keadaan
elemen dihitung ulang dari cap waktu.

## Mengubah isinya

Alur cerita tiap GIF ada di `SPEC_SISTEM` dan `SPEC_API` di `build.py`, berupa
daftar bab dan langkah:

```python
step(["el0034"], "ya → DUGAAN JATUH, dashboard berubah kuning", 900)
#     ^ id elemen   ^ teks caption                               ^ jeda (ms)
```

Panah tidak perlu disebut — sebuah panah ikut digambar otomatis begitu kedua
ujungnya hidup, berdasarkan binding di berkas Excalidraw.

Kamera tiap bab **dihitung** dari kotak pembatas elemen-elemen bab itu, tidak
ditulis manual, jadi tidak akan meleset kalau diagramnya digeser. Jalankan
`python tools/flowanim/build.py --list` untuk melihat skala tiap bab; di bawah
0,62 skripnya memperingatkan karena teksnya mulai susah dibaca — pecah bab itu
jadi dua kalau kena peringatan.

## Catatan

Sumber di `docs/flow/` adalah salinan dari folder `Flow/` di luar repo. Kalau
diagramnya diedit di excalidraw.com, timpa salinan itu lalu jalankan ulang
kedua perintah di atas.

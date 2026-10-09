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

## Kenapa dibikin begini

**Kenapa menggambar ulang SVG-nya sendiri, bukan ekspor SVG dari excalidraw.com?**
Hasil ekspor excalidraw adalah satu gambar utuh tanpa pegangan per elemen, jadi
tidak bisa dianimasikan node per node. Kedua diagram ini dibuat dengan
`roughness: 0` — bentuknya geometris bersih, bukan sketsa tangan — sehingga
menggambar ulangnya cuma soal rect / ellipse / diamond / polyline. Tidak perlu
roughjs. Yang dibaca dari berkasnya: `containerId` (teks milik node mana),
`startBinding` / `endBinding` (panah menghubungkan apa ke apa), dan `points`.

**Kenapa pakai bab dengan kamera diam, bukan pan-zoom yang halus?**
Dua alasan. Pertama, kanvasnya 4500–4900 px; kalau dimuat utuh ke GIF selebar
README, teksnya menyusut ke ~22% dan tidak terbaca. Kedua — dan ini yang
menentukan ukuran berkas — kamera yang nge-pan mengubah SETIAP piksel di setiap
frame, sehingga kompresi antar-frame GIF mati total dan berkasnya bisa puluhan
MB. Dengan kamera diam, mayoritas piksel identik antar frame:

| | frame | hasil |
|---|---|---|
| `flow-detection.gif` | 441 @ 1280×720 | 1,4 MB |
| `flow-api.gif` | 374 @ 1280×720 | 1,1 MB |

`palettegen=stats_mode=diff` + `paletteuse=diff_mode=rectangle` di `capture.mjs`
yang memanfaatkan sifat itu: palet dan penulisan frame hanya memperhatikan
bagian yang berubah.

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

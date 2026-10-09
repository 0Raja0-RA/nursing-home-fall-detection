#!/usr/bin/env python
"""Satu berkas .excalidraw jadi satu SVG diam untuk disisipkan di README.

```bash
python tools/flowanim/still.py flowchart-arsitektur
python tools/flowanim/still.py flowchart-state-machine
```

Membaca `docs/flow/<nama>.excalidraw`, menulis `docs/assets/<nama>.svg`.

Kenapa SVG, bukan PNG seperti GIF-nya? Diagram ini diam, tidak ada yang perlu
dianimasikan, jadi tidak ada alasan membayar rasterisasi: SVG tetap tajam saat
pembaca memperbesar, ukurannya puluhan kali lebih kecil, dan -- yang paling
menentukan -- pembuatannya tidak butuh puppeteer maupun ffmpeg seperti jalur
GIF. Cukup Python yang sudah ada di virtualenv repo ini.

Perendernya dipakai bersama dengan pembuat GIF (`render.py`), jadi kedua jenis
gambar di README tampil dengan gaya yang sama persis.
"""

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import render  # noqa: E402  (butuh sys.path di atas)

SUMBER = REPO / "docs" / "flow"
TUJUAN = REPO / "docs" / "assets"

PADDING = 40


def jadikan_svg(nama: str) -> Path:
    berkas = SUMBER / f"{nama}.excalidraw"
    if not berkas.exists():
        raise SystemExit(f"tidak ada: {berkas}")

    d = render.load(berkas)
    kotak = render.bbox_of(d, [e["id"] for e in d.elements if not e.get("isDeleted")])

    lebar = round(kotak.w + PADDING * 2)
    tinggi = round(kotak.h + PADDING * 2)
    svg = render.render_svg(d, lebar, tinggi)

    # Geser isinya supaya kotak pembatas diagram duduk rapi di dalam kanvas.
    dx = PADDING - kotak.x0
    dy = PADDING - kotak.y0
    svg = svg.replace('<g id="cam">', f'<g id="cam" transform="translate({dx:.2f},{dy:.2f})">', 1)

    # `halo` adalah lapisan sorot setebal 14px yang hanya dipakai animasi GIF
    # untuk menandai node yang sedang aktif. Pada gambar diam semua node setara,
    # jadi lapisan itu dibuang.
    #
    # Dibuang, bukan disembunyikan lewat <style> di dalam SVG: GitHub menyaring
    # SVG yang ditampilkan di README dan elemen <style> termasuk yang bisa
    # dibuangnya -- kalau itu terjadi, halonya justru muncul semua.
    svg = re.sub(r'<(?:rect|ellipse|polygon) class="halo"[^>]*/>', "", svg)

    TUJUAN.mkdir(parents=True, exist_ok=True)
    keluar = TUJUAN / f"{nama}.svg"
    keluar.write_text(svg, encoding="utf-8")
    print(f"{keluar.relative_to(REPO)}  —  {lebar}x{tinggi} px, {len(svg) / 1024:.0f} KB")
    return keluar


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nama", nargs="*",
                    help="nama berkas di docs/flow tanpa .excalidraw; "
                         "kosong = semua yang belum punya GIF")
    args = ap.parse_args()

    daftar = args.nama or ["flowchart-arsitektur", "flowchart-state-machine"]
    for n in daftar:
        jadikan_svg(n)


if __name__ == "__main__":
    main()

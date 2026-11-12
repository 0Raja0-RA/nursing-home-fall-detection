"""Launcher pameran: tunnel, backend, dan QR pengunjung dalam sekali jalan.

Dipanggil oleh run-pameran.bat. Urutannya:

1. Build dashboard (`npm run build`) bila belum ada atau sudah lebih tua dari kode.
2. Buka Cloudflare quick tunnel ke backend, lalu baca alamat https-nya.
3. Jalankan backend dengan token pengunjung baru dan alamat tunnel itu.
4. Tampilkan QR pengunjung di terminal dan di halaman browser lokal.

Token pengunjung dibuat baru setiap kali launcher dijalankan, jadi QR dari hari
sebelumnya otomatis tidak berlaku. Token ditaruh di fragmen URL (#t=...), yang tidak
pernah dikirim browser ke server, sehingga tidak tercatat di log uvicorn maupun
Cloudflare. Jangan menaruh QR ini di halaman publik seperti landing Vercel.

Pemakaian:
    python tools/pameran.py               # tunnel + backend + QR
    python tools/pameran.py --tanpa-tunnel  # tanpa internet: hanya di laptop ini
"""
from __future__ import annotations

import argparse
import html
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

AKAR = Path(__file__).resolve().parents[1]
FRONTEND = AKAR / "frontend"
BACKEND = AKAR / "backend"
DIST = FRONTEND / "dist"
PORT = int(os.environ.get("PORT", "8000"))
LOKAL = f"http://127.0.0.1:{PORT}"
POLA_TUNNEL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def lapor(teks: str = "") -> None:
    print(teks, flush=True)


def waktu_terbaru(folder: Path) -> float:
    return max((p.stat().st_mtime for p in folder.rglob("*") if p.is_file()), default=0.0)


def build_dashboard(paksa: bool) -> None:
    index = DIST / "index.html"
    kode = max(waktu_terbaru(FRONTEND / "src"), (FRONTEND / "index.html").stat().st_mtime)
    if not paksa and index.is_file() and index.stat().st_mtime >= kode:
        lapor("Dashboard  : build sudah terbaru.")
        return
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("[GAGAL] npm tidak ditemukan. Pasang Node.js, atau jalankan build di komputer lain.")
    if not (FRONTEND / "node_modules").is_dir():
        lapor("Dashboard  : memasang dependensi (npm install)...")
        subprocess.run([npm, "install"], cwd=FRONTEND, check=True)
    lapor("Dashboard  : membangun ulang (npm run build)...")
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def cari_cloudflared() -> str | None:
    """Cari cloudflared di PATH, lalu di folder instalasi winget.

    Jendela terminal yang dibuka sebelum `winget install` belum mengenal PATH baru,
    jadi folder instalasinya ikut diperiksa supaya tidak perlu membuka jendela baru.
    """
    if ketemu := shutil.which("cloudflared"):
        return ketemu
    for folder in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if folder and (calon := Path(folder) / "cloudflared" / "cloudflared.exe").is_file():
            return str(calon)
    return None


def buka_tunnel() -> tuple[subprocess.Popen, str]:
    cloudflared = cari_cloudflared()
    if cloudflared is None:
        sys.exit(
            "[GAGAL] cloudflared tidak ditemukan. Pasang sekali dengan:\n"
            "        winget install --id Cloudflare.cloudflared\n"
            "        lalu buka ulang jendela ini. Atau jalankan dengan --tanpa-tunnel."
        )
    lapor("Tunnel     : membuka Cloudflare quick tunnel...")
    proses = subprocess.Popen(
        [cloudflared, "tunnel", "--no-autoupdate", "--url", LOKAL],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    alamat: list[str] = []
    siap = threading.Event()

    def baca() -> None:
        # Terus dibaca sampai proses selesai, supaya pipa tidak penuh dan cloudflared macet.
        for baris in proses.stdout:
            if not alamat and (cocok := POLA_TUNNEL.search(baris)):
                alamat.append(cocok.group(0))
                siap.set()

    threading.Thread(target=baca, daemon=True).start()
    if not siap.wait(60):
        proses.terminate()
        sys.exit("[GAGAL] Tunnel tidak memberi alamat dalam 60 detik. Periksa koneksi internet.")
    return proses, alamat[0]


def jalankan_backend(token: str, alamat: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["VISITOR_TOKEN"] = token
    # Tombol "Buka dashboard" di pesan Telegram ikut menunjuk ke alamat tunnel.
    env["DASHBOARD_URL"] = f"{alamat}/dashboard"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    lapor("Backend    : menyalakan server...")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND, env=env,
    )


def tunggu_backend(proses: subprocess.Popen, batas: float = 180) -> None:
    import urllib.request

    mulai = time.monotonic()
    while time.monotonic() - mulai < batas:
        if proses.poll() is not None:
            sys.exit("[GAGAL] Backend berhenti saat menyala. Lihat pesan di atas.")
        try:
            with urllib.request.urlopen(f"{LOKAL}/login", timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            time.sleep(1)
    sys.exit("[GAGAL] Backend belum menjawab setelah 3 menit.")


def halaman_qr(url_pengunjung: str, url_tim: str) -> Path:
    import segno

    svg = segno.make(url_pengunjung, error="m").svg_inline(scale=10, border=2, dark="#0f172a", light="#ffffff")
    isi = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>QR Pengunjung FallDetect</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f8fafc;
         font-family: system-ui, sans-serif; color: #0f172a; text-align: center; }}
  main {{ padding: 24px 16px; max-width: 640px; }}
  h1 {{ font-size: 2rem; margin: 0 0 8px; }}
  p {{ margin: 8px 0; font-size: 1.1rem; }}
  .qr svg {{ width: min(80vw, 480px); height: auto; }}
  small {{ display: block; margin-top: 16px; color: #475569; word-break: break-all; }}
</style></head>
<body><main>
  <h1>Lihat FallDetect dari HP</h1>
  <p>Scan untuk melihat kamera, status, dan riwayat secara langsung.</p>
  <div class="qr">{svg}</div>
  <p>Area ini direkam untuk demo.</p>
  <small>Tim stand masuk lewat {html.escape(url_tim)}</small>
</main></body></html>
"""
    berkas = Path(tempfile.gettempdir()) / "falldetect-qr-pengunjung.html"
    berkas.write_text(isi, encoding="utf-8")
    return berkas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tanpa-tunnel", action="store_true", help="Hanya di laptop ini, tanpa internet.")
    parser.add_argument("--build", action="store_true", help="Paksa build ulang dashboard.")
    args = parser.parse_args()

    build_dashboard(args.build)
    token = secrets.token_urlsafe(16)
    tunnel, alamat = (None, LOKAL) if args.tanpa_tunnel else buka_tunnel()
    backend = jalankan_backend(token, alamat)
    try:
        tunggu_backend(backend)
        url_pengunjung = f"{alamat}/lihat#t={token}"
        url_tim = f"{alamat}/login"

        lapor()
        lapor("=" * 60)
        lapor(f" Tim stand  : {url_tim}")
        lapor(f" Pengunjung : scan QR di bawah atau di jendela browser")
        lapor("=" * 60)
        try:
            import segno
            segno.make(url_pengunjung, error="m").terminal(compact=True)
        except Exception:
            lapor(f" {url_pengunjung}")
        if args.tanpa_tunnel:
            lapor(" Mode tanpa tunnel: QR hanya bisa dibuka dari laptop ini.")
        lapor(" QR berlaku sampai jendela ini ditutup. Tekan Ctrl+C untuk berhenti.")
        lapor()
        webbrowser.open(halaman_qr(url_pengunjung, url_tim).as_uri())
        webbrowser.open(url_tim)

        while backend.poll() is None:
            if tunnel is not None and tunnel.poll() is not None:
                lapor("[PERINGATAN] Tunnel terputus. Jalankan ulang launcher untuk alamat dan QR baru.")
                break
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        for proses in (backend, tunnel):
            if proses is not None and proses.poll() is None:
                proses.terminate()
                try:
                    proses.wait(10)
                except subprocess.TimeoutExpired:
                    proses.kill()
        lapor("Backend dan tunnel dihentikan.")


if __name__ == "__main__":
    main()

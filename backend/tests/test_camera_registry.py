"""
test_camera_registry.py
=======================
Uji untuk pendaftaran kamera lewat dashboard: validasi sumber, repository,
dan pemuatan model yang aman saat beberapa kamera berjalan bersamaan.

Tidak memuat model YOLO sungguhan dan tidak membuka kamera fisik, jadi bisa
dijalankan di mana saja.
"""

import asyncio
import ipaddress
import sys
import threading
import types
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repository import CameraRepository
from app.models.schemas import CameraCreate, CameraUpdate
from app.services.camera_service import sumber_adalah_file, validasi_sumber


# ---- Validasi sumber ---------------------------------------

def test_sumber_kosong_ditolak():
    ok, alasan = validasi_sumber("   ")
    assert ok is False
    assert "kosong" in alasan.lower()


def test_file_video_yang_ada_diterima(tmp_path: Path):
    berkas = tmp_path / "rekaman.mp4"
    berkas.write_bytes(b"bukan video sungguhan, cukup ada")
    ok, alasan = validasi_sumber(str(berkas))
    assert ok is True, alasan


def test_file_video_tidak_ada_ditolak():
    ok, alasan = validasi_sumber("D:/jelas/tidak/ada/rekaman.mp4")
    assert ok is False
    assert "tidak ditemukan" in alasan


def test_skema_url_asing_ditolak():
    ok, alasan = validasi_sumber("ftp://192.168.1.50/video")
    assert ok is False
    assert "tidak didukung" in alasan


def test_host_tidak_terjangkau_ditolak_cepat():
    """Alamat yang tidak terjangkau harus gagal dalam hitungan detik, bukan ~90 detik.

    Ini yang membuat tombol "Tambah Kamera" bisa memvalidasi lebih dulu tanpa
    membuat pengguna menunggu lama.
    """
    import time

    mulai = time.monotonic()
    ok, alasan = validasi_sumber("http://10.255.255.1:8080/video", batas=2.0)
    durasi = time.monotonic() - mulai

    assert ok is False
    assert durasi < 10.0, f"validasi makan {durasi:.1f} detik, terlalu lama untuk UI"
    # Pesannya harus menyebut penyebab yang paling sering terjadi di lapangan.
    assert "client isolation" in alasan


def test_sumber_adalah_file_tidak_bingung_dengan_url(tmp_path: Path):
    berkas = tmp_path / "a.mp4"
    berkas.write_bytes(b"x")
    assert sumber_adalah_file(str(berkas)) is True
    assert sumber_adalah_file("0") is False
    assert sumber_adalah_file("http://192.168.1.50:8080/video") is False


# ---- Repository --------------------------------------------

@pytest_asyncio.fixture
async def sesi() -> AsyncSession:
    """Session SQLAlchemy ke SQLite in-memory dengan tabel sudah dibuat."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_id_kamera_berurutan_dan_slot_kosong_dipakai_ulang(sesi: AsyncSession):
    repo = CameraRepository(sesi)

    for n in range(1, 4):
        rec = await repo.create_camera(CameraCreate(name=f"Kamar {n}", source=f"rtsp://10.0.0.{n}:554/s"))
        assert rec.id == f"cam-{n:02d}"

    # Hapus yang di tengah: id-nya harus dipakai ulang, bukan melompat ke cam-04.
    assert await repo.delete_camera("cam-02") is True
    rec = await repo.create_camera(CameraCreate(name="Pengganti", source="rtsp://10.0.0.9:554/s"))
    assert rec.id == "cam-02"
    assert await repo.count() == 3


@pytest.mark.asyncio
async def test_sumber_ganda_terdeteksi(sesi: AsyncSession):
    repo = CameraRepository(sesi)
    await repo.create_camera(CameraCreate(name="A", source="http://10.0.0.5:8080/video"))

    assert await repo.source_dipakai("http://10.0.0.5:8080/video") is True
    assert await repo.source_dipakai("http://10.0.0.6:8080/video") is False
    # Kamera itu sendiri tidak boleh dianggap bentrok dengan dirinya sendiri.
    assert await repo.source_dipakai("http://10.0.0.5:8080/video", kecuali_id="cam-01") is False


@pytest.mark.asyncio
async def test_update_hanya_mengubah_field_yang_dikirim(sesi: AsyncSession):
    repo = CameraRepository(sesi)
    await repo.create_camera(CameraCreate(name="Kamar 01", source="http://10.0.0.5:8080/video", rotate=90))

    # Skenario pindah WiFi: hanya alamatnya yang berganti.
    rec = await repo.update_camera("cam-01", CameraUpdate(source="http://192.168.43.1:8080/video"))
    assert rec.source == "http://192.168.43.1:8080/video"
    assert rec.name == "Kamar 01"
    assert rec.rotate == 90
    assert rec.enabled is True

    assert await repo.update_camera("cam-99", CameraUpdate(name="x")) is None


# ---- Pemuatan model saat banyak kamera ---------------------

def test_model_hanya_dimuat_sekali_walau_banyak_thread(monkeypatch, tmp_path: Path):
    """Empat kamera yang menyala bersamaan tidak boleh memuat model empat kali.

    Setiap kamera memanggil run_inference lewat asyncio.to_thread, sehingga
    beberapa thread bisa lolos pengecekan `_model is None` secara bersamaan dan
    masing-masing membuat salinan YOLO sendiri. Terlihat nyata di log sebagai
    "Model loaded" lima kali, memboroskan RAM dan waktu muat.
    """
    from app.services import inference_service

    jumlah_muat = 0
    kunci = threading.Lock()

    class YOLOPalsu:
        def __init__(self, path):
            nonlocal jumlah_muat
            with kunci:
                jumlah_muat += 1
            # Tiru pemuatan yang lambat supaya thread lain sempat masuk.
            threading.Event().wait(0.2)

    modul_palsu = types.ModuleType("ultralytics")
    modul_palsu.YOLO = YOLOPalsu
    monkeypatch.setitem(sys.modules, "ultralytics", modul_palsu)

    berkas_model = tmp_path / "best.pt"
    berkas_model.write_bytes(b"model palsu")
    monkeypatch.setattr(
        inference_service, "get_settings",
        lambda: types.SimpleNamespace(MODEL_PATH=str(berkas_model)),
    )

    inference_service.unload_model()
    try:
        hasil = []
        threads = [
            threading.Thread(target=lambda: hasil.append(inference_service.load_model()))
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert jumlah_muat == 1, f"model dimuat {jumlah_muat} kali, seharusnya 1"
        assert len(hasil) == 8
        assert all(m is hasil[0] for m in hasil), "tidak semua thread dapat instance yang sama"
    finally:
        inference_service.unload_model()


# ---- Pemindaian jaringan -----------------------------------

def test_subnet_memakai_netmask_sesungguhnya(monkeypatch):
    """Prefiks subnet harus dibaca dari antarmuka, bukan diasumsikan /24.

    Di WiFi kampus (eepiswlan) maskernya 255.255.248.0 (/21), sehingga laptop di
    10.252.144.87 dan HP di 10.252.151.81 berada di satu subnet yang sama meski
    oktet ketiganya berbeda. Pemindai yang mengasumsikan /24 tidak akan pernah
    menemukan HP itu.
    """
    from app.services import network_scan as ns

    monkeypatch.setattr(ns, "antarmuka_lokal", lambda: [("10.252.144.87", "255.255.248.0")])
    jaringan = ns.subnet_yang_dipindai()

    assert len(jaringan) == 1
    assert str(jaringan[0]) == "10.252.144.0/21"
    assert ipaddress.IPv4Address("10.252.151.81") in jaringan[0]


def test_subnet_terlalu_lebar_dipersempit(monkeypatch):
    """Subnet /16 tidak boleh disapu seluruhnya (65 ribu alamat)."""
    from app.services import network_scan as ns

    monkeypatch.setattr(ns, "antarmuka_lokal", lambda: [("192.168.5.10", "255.255.0.0")])
    jaringan = ns.subnet_yang_dipindai()

    assert str(jaringan[0]) == "192.168.5.0/24"
    assert jaringan[0].num_addresses <= ns.MAX_ALAMAT


def test_alamat_publik_dan_link_local_dilewati(monkeypatch):
    from app.services import network_scan as ns

    monkeypatch.setattr(ns, "antarmuka_lokal", lambda: [
        ("8.8.8.8", "255.255.255.0"),          # publik
        ("169.254.20.110", "255.255.0.0"),     # link-local
    ])
    assert ns.subnet_yang_dipindai() == []


# ---- Alamat yang bisa dihubungi tapi bukan aliran video ----

def _server_http(content_type: str, body: bytes = b"<html>halo</html>"):
    """Jalankan server HTTP sekali-pakai di port acak, kembalikan (port, shutdown)."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_port, srv.shutdown


def test_url_yang_mengembalikan_halaman_web_ditolak():
    """http://IP:8080 tanpa /video lolos cek TCP tapi bukan aliran video.

    Ini kesalahan yang mudah terjadi: aplikasi IP Webcam menampilkan alamat akar
    di layar HP, padahal yang dibutuhkan OpenCV adalah path /video. Tanpa
    pemeriksaan ini, kameranya tersimpan lalu gagal diam-diam.
    """
    port, matikan = _server_http("text/html; charset=utf-8")
    try:
        ok, alasan = validasi_sumber(f"http://127.0.0.1:{port}")
        assert ok is False
        assert "/video" in alasan
    finally:
        matikan()


def test_url_yang_mengembalikan_aliran_gambar_diterima():
    port, matikan = _server_http("multipart/x-mixed-replace; boundary=frame", b"x")
    try:
        ok, alasan = validasi_sumber(f"http://127.0.0.1:{port}/video")
        assert ok is True, alasan
    finally:
        matikan()

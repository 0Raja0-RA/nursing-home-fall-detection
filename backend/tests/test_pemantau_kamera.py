"""
test_pemantau_kamera.py
=======================
Kabar kamera terputus dan pulih ke grup Telegram.

Fungsi `periksa` murni (tanpa kamera, jam, atau jaringan), jadi setiap putaran
pemantau bisa diuji dengan jam buatan.
"""

from datetime import datetime, timedelta

from app.runtime.pemantau_kamera import Perubahan, periksa, susun_pesan

T0 = datetime(2026, 11, 12, 7, 0, 0)
KAMERA = [("cam-01", "Kamar 101"), ("cam-02", "Ruang Makan")]


def _putaran(keadaan, detik, mengalir, frame=None, kamera=KAMERA, ambang=30.0):
    return periksa(kamera, mengalir, frame or {}, keadaan, T0 + timedelta(seconds=detik), ambang)


def test_putus_sebentar_tidak_dikabarkan():
    """Kamera yang dinyalakan ulang dari Daftar Kamera putus beberapa detik saja."""
    keadaan = {}
    assert _putaran(keadaan, 0, {"cam-01": False, "cam-02": True}).putus == []
    assert _putaran(keadaan, 20, {"cam-01": False, "cam-02": True}).putus == []
    hasil = _putaran(keadaan, 25, {"cam-01": True, "cam-02": True})
    assert hasil.putus == [] and hasil.pulih == [], "pulih tanpa pernah dikabarkan putus: diam"


def test_putus_lewat_ambang_dikabarkan_sekali_lalu_pulih():
    keadaan = {}
    _putaran(keadaan, 0, {"cam-01": False, "cam-02": True})
    hasil = _putaran(keadaan, 30, {"cam-01": False, "cam-02": True})
    assert hasil.putus == [("Kamar 101", T0)]

    assert _putaran(keadaan, 40, {"cam-01": False, "cam-02": True}).putus == [], "tidak diulang"

    hasil = _putaran(keadaan, 50, {"cam-01": True, "cam-02": True})
    assert hasil.pulih == ["Kamar 101"]
    assert _putaran(keadaan, 60, {"cam-01": True, "cam-02": True}).pulih == []


def test_sejak_memakai_jam_frame_terakhir():
    """Kamera yang putus sebelum pemantau sempat melihatnya: jamnya dari frame terakhir."""
    keadaan = {}
    frame_terakhir = T0 - timedelta(seconds=45)
    hasil = _putaran(keadaan, 0, {"cam-01": False, "cam-02": True}, {"cam-01": frame_terakhir})
    assert hasil.putus == [("Kamar 101", frame_terakhir)]


def test_beberapa_kamera_dikelompokkan_dalam_satu_putaran():
    keadaan = {}
    _putaran(keadaan, 0, {"cam-01": False, "cam-02": False})
    hasil = _putaran(keadaan, 31, {"cam-01": False, "cam-02": False})
    assert [n for n, _ in hasil.putus] == ["Kamar 101", "Ruang Makan"]


def test_kamera_yang_dihapus_dilupakan():
    keadaan = {}
    _putaran(keadaan, 0, {"cam-01": False, "cam-02": True})
    _putaran(keadaan, 10, {"cam-02": True}, kamera=[("cam-02", "Ruang Makan")])
    assert "cam-01" not in keadaan


def test_isi_pesan():
    teks = susun_pesan(Perubahan(putus=[("Kamar <101>", T0)], pulih=["Ruang Makan"]))
    assert "Kamera terputus" in teks and "&lt;101&gt;" in teks and "sejak" in teks
    assert "tidak terdeteksi" in teks, "akibatnya ditulis, bukan hanya statusnya"
    assert "Kamera pulih" in teks and "Ruang Makan" in teks
    assert "Kamera pulih" not in susun_pesan(Perubahan(putus=[("Kamar 101", T0)]))

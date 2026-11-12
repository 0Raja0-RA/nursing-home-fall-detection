"""
test_insiden.py
===============
Penanganan alarm oleh manusia: "Saya ke sana", "Tandai Ditangani" dengan putusan,
dan antrean Riwayat Insiden.

Diuji lewat HTTP (TestClient) dengan router alerts sungguhan. Akun yang sedang
masuk diganti dengan pengganti yang bisa ditukar di tengah uji, supaya dua
perawat bisa diperankan bergantian.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import alerts as api_alerts
from app.api.auth import wajib_login
from app.db.database import get_db
from app.db.models import AlertRecord, AlertSnapshot, Base

SITI = SimpleNamespace(id=1, display_name="Siti", role="perawat", active=True)
BUDI = SimpleNamespace(id=2, display_name="Budi", role="perawat", active=True)


@pytest.fixture
def uji():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    sekarang = datetime(2026, 11, 12, 7, 0, 0)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add_all([
                # 1: alarm sungguhan yang baru masuk, berfoto, pesannya sudah terkirim.
                AlertRecord(camera_id="cam-01", camera_name="Kamar 101", message="uji",
                            fall_duration=5.0, created_at=sekarang, telegram_message_id=501,
                            telegram_foto=True, telegram_status="terkirim"),
                # 2: latihan di kamera lain.
                AlertRecord(camera_id="cam-02", camera_name="Kamar 102", message="uji",
                            fall_duration=5.0, simulated=True, created_at=sekarang - timedelta(hours=1)),
                # 3: alarm kemarin yang Telegram-nya gagal.
                AlertRecord(camera_id="cam-01", camera_name="Kamar 101", message="uji",
                            fall_duration=6.0, created_at=sekarang - timedelta(days=1),
                            telegram_status="gagal"),
            ])
            await s.commit()
            s.add(AlertSnapshot(alert_id=1, jpeg=b"\xff\xd8foto-kejadian\xff\xd9"))
            await s.commit()

    async def db_uji():
        async with factory() as s:
            yield s

    masuk = {"akun": SITI}
    app = FastAPI()
    app.include_router(api_alerts.router, prefix="/api/alerts")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: masuk["akun"]

    with TestClient(app) as c, \
            patch("app.services.insiden_service.manager.broadcast", new=AsyncMock()) as siar, \
            patch("app.services.notification_service.perbarui_pesan", new=AsyncMock()) as sunting:
        c.portal.call(siapkan)
        yield SimpleNamespace(klien=c, masuk=masuk, siar=siar, sunting=sunting, factory=factory)


def _sebagai(uji, akun):
    uji.masuk["akun"] = akun


# ---- Saya ke sana ------------------------------------------

def test_klaim_mencatat_nama_dan_jam_lalu_disiarkan(uji):
    r = uji.klien.put("/api/alerts/1/claim")
    assert r.status_code == 200
    d = r.json()
    assert d["claimed_by"] == "Siti" and d["claimed_at"]
    assert d["acknowledged"] is False, "klaim belum menutup alarm"

    pesan = uji.siar.await_args.args[0]
    assert pesan.event == "alert_update"
    assert pesan.data["claimed_by"] == "Siti"


def test_klaim_menyunting_pesan_telegram_yang_sama(uji):
    uji.klien.put("/api/alerts/1/claim")
    data, message_id, dengan_foto = uji.sunting.call_args.args
    assert message_id == 501 and dengan_foto is True
    assert data["claimed_by"] == "Siti"


def test_klaim_ulang_oleh_orang_yang_sama_tidak_mengubah_jam(uji):
    pertama = uji.klien.put("/api/alerts/1/claim").json()
    kedua = uji.klien.put("/api/alerts/1/claim")
    assert kedua.status_code == 200
    assert kedua.json()["claimed_at"] == pertama["claimed_at"]


def test_klaim_kedua_oleh_orang_lain_ditolak_dengan_nama_penangan(uji):
    uji.klien.put("/api/alerts/1/claim")
    _sebagai(uji, BUDI)
    r = uji.klien.put("/api/alerts/1/claim")
    assert r.status_code == 409
    assert "Siti" in r.json()["detail"]


def test_klaim_sesudah_ditangani_ditolak(uji):
    uji.klien.put("/api/alerts/1/ack", json={"verdict": "jatuh"})
    assert uji.klien.put("/api/alerts/1/claim").status_code == 409


def test_alert_tidak_ada(uji):
    assert uji.klien.put("/api/alerts/999/claim").status_code == 404
    assert uji.klien.put("/api/alerts/999/ack").status_code == 404
    assert uji.klien.put("/api/alerts/999/verdict", json={"verdict": "jatuh"}).status_code == 404


# ---- Tandai Ditangani dan putusan --------------------------

def test_alarm_palsu_wajib_beralasan(uji):
    r = uji.klien.put("/api/alerts/1/ack", json={"verdict": "palsu"})
    assert r.status_code == 422
    assert uji.klien.get("/api/alerts/1").json()["acknowledged"] is False, "tidak boleh setengah tersimpan"

    assert uji.klien.put("/api/alerts/1/ack", json={"verdict": "palsu", "reason": "ngawur"}).status_code == 422


def test_ditangani_dengan_putusan_dan_alasan(uji):
    uji.klien.put("/api/alerts/1/claim")
    _sebagai(uji, BUDI)
    d = uji.klien.put("/api/alerts/1/ack", json={
        "verdict": "palsu", "reason": "berbaring_sengaja", "note": " Tidur siang di karpet. "}).json()

    assert d["acknowledged"] is True and d["acknowledged_by"] == "Budi"
    assert d["claimed_by"] == "Siti", "yang menuju lokasi tetap tercatat"
    assert d["verdict"] == "palsu" and d["verdict_reason"] == "berbaring_sengaja"
    assert d["verdict_by"] == "Budi" and d["verdict_at"]
    assert d["caregiver_note"] == "Tidur siang di karpet."

    pesan = uji.siar.await_args.args[0]
    assert pesan.event == "alert_ack" and pesan.data["verdict"] == "palsu"


def test_alasan_dibuang_bila_bukan_alarm_palsu(uji):
    d = uji.klien.put("/api/alerts/1/ack", json={"verdict": "jatuh", "reason": "bukan_orang"}).json()
    assert d["verdict"] == "jatuh" and d["verdict_reason"] is None


def test_ditutup_tanpa_putusan_tetap_perlu_tindakan(uji):
    """Mis. ditutup dari Telegram atau API lama: penanganannya selesai, penilaiannya belum."""
    d = uji.klien.put("/api/alerts/1/ack").json()
    assert d["acknowledged"] is True and d["verdict"] is None

    antrean = uji.klien.get("/api/alerts/", params={"status": "perlu_tindakan"}).json()
    assert 1 in [a["id"] for a in antrean]


def test_putusan_bisa_diisi_dan_diubah_belakangan(uji):
    assert uji.klien.put("/api/alerts/1/verdict", json={"verdict": "jatuh"}).status_code == 409, \
        "putusan diberikan sesudah penghuni ditolong"

    uji.klien.put("/api/alerts/1/ack")
    _sebagai(uji, BUDI)
    d = uji.klien.put("/api/alerts/1/verdict", json={"verdict": "belum_yakin"}).json()
    assert d["verdict"] == "belum_yakin" and d["verdict_by"] == "Budi"

    d = uji.klien.put("/api/alerts/1/verdict", json={"verdict": "palsu", "reason": "bukan_orang"}).json()
    assert d["verdict"] == "palsu" and d["verdict_reason"] == "bukan_orang"
    assert uji.klien.put("/api/alerts/1/verdict", json={"verdict": "palsu"}).status_code == 422


def test_menutup_ulang_tidak_mengganti_penangan_pertama(uji):
    uji.klien.put("/api/alerts/1/ack")
    _sebagai(uji, BUDI)
    d = uji.klien.put("/api/alerts/1/ack", json={"verdict": "jatuh"}).json()
    assert d["acknowledged_by"] == "Siti"
    assert d["verdict"] == "jatuh" and d["verdict_by"] == "Budi"


# ---- Antrean Riwayat Insiden -------------------------------

def _id(r):
    return [a["id"] for a in r.json()]


def test_filter_antrean(uji):
    k = uji.klien
    assert _id(k.get("/api/alerts/")) == [1, 2, 3], "terbaru lebih dulu"
    assert _id(k.get("/api/alerts/", params={"status": "terbuka"})) == [1, 2, 3]
    assert _id(k.get("/api/alerts/", params={"simulated": "false"})) == [1, 3]
    assert _id(k.get("/api/alerts/", params={"camera_id": "cam-02"})) == [2]
    assert _id(k.get("/api/alerts/", params={"sejak": "2026-11-12T00:00:00"})) == [1, 2]

    k.put("/api/alerts/1/ack", json={"verdict": "jatuh"})
    k.put("/api/alerts/2/ack")                      # latihan: tidak perlu dinilai
    k.put("/api/alerts/3/ack")                      # sungguhan tanpa putusan
    assert _id(k.get("/api/alerts/", params={"status": "terbuka"})) == []
    assert _id(k.get("/api/alerts/", params={"status": "perlu_tindakan"})) == [3]
    assert _id(k.get("/api/alerts/", params={"status": "selesai"})) == [1, 2]
    assert _id(k.get("/api/alerts/", params={"verdict": "belum_dinilai"})) == [2, 3]


def test_ringkasan(uji):
    k = uji.klien
    awal = k.get("/api/alerts/ringkasan").json()
    assert awal["belum_ditangani"] == 3 and awal["perlu_tindakan"] == 3
    assert awal["total"] == 2 and awal["latihan"] == 1 and awal["telegram_gagal"] == 1

    k.put("/api/alerts/1/claim")
    k.put("/api/alerts/3/ack", json={"verdict": "palsu", "reason": "orang_lain"})
    d = k.get("/api/alerts/ringkasan").json()
    assert d["sedang_ditangani"] == 1
    assert d["belum_ditangani"] == 2 and d["belum_dinilai"] == 0 and d["perlu_tindakan"] == 2
    assert d["palsu"] == 1 and d["jatuh"] == 0


def test_nama_rute_tidak_tertukar_dengan_id(uji):
    assert uji.klien.get("/api/alerts/ringkasan").status_code == 200
    assert uji.klien.get("/api/alerts/count").json() == {"count": 3}


# ---- Foto dan Telegram -------------------------------------

def test_foto_kejadian_tidak_disimpan_di_cache_browser(uji):
    r = uji.klien.get("/api/alerts/1/snapshot")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == b"\xff\xd8foto-kejadian\xff\xd9"
    assert uji.klien.get("/api/alerts/3/snapshot").status_code == 404


def test_kirim_ulang_telegram_ditolak_bila_belum_dikonfigurasi(uji, monkeypatch):
    import types

    import app.core.config as config

    monkeypatch.setattr(config, "get_settings", lambda: types.SimpleNamespace(
        TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID=""))
    assert uji.klien.post("/api/alerts/3/telegram").status_code == 409


# ---- Ekspor CSV untuk uji mini -------------------------------

def _isi(uji, alert_id, **kolom):
    """Tulis kolom langsung ke database, supaya selisih waktunya pasti."""
    async def ubah():
        async with uji.factory() as s:
            a = await s.get(AlertRecord, alert_id)
            for nama, nilai in kolom.items():
                setattr(a, nama, nilai)
            await s.commit()
    uji.klien.portal.call(ubah)


def _baris_csv(r):
    import csv
    import io

    assert r.content.startswith(b"\xef\xbb\xbf"), "BOM supaya Excel membaca UTF-8"
    return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))


def test_ekspor_csv_menghitung_waktu_respons(uji):
    awal = datetime(2026, 11, 12, 7, 0, 0)
    _isi(uji, 1, claimed_by="Siti", claimed_at=awal + timedelta(seconds=40),
         acknowledged=True, acknowledged_by="Siti", acknowledged_at=awal + timedelta(seconds=100),
         verdict="palsu", verdict_reason="berbaring_sengaja", verdict_by="Siti",
         verdict_at=awal + timedelta(seconds=100), threshold_sec=3.0, detection_mode="pose",
         caregiver_note="Pasien tidur, posisi miring")
    # Ditutup tanpa klaim: respons pertamanya adalah penutupan itu sendiri.
    _isi(uji, 3, acknowledged=True, acknowledged_by="Budi",
         acknowledged_at=datetime(2026, 11, 11, 7, 2, 30))

    r = uji.klien.get("/api/alerts/ekspor")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="insiden-falldetect-')

    baris = _baris_csv(r)
    assert [b["id"] for b in baris] == ["3", "2", "1"], "urut dari yang terlama"
    pertama = baris[2]
    assert pertama["waktu_alarm"] == awal.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert pertama["ruang"] == "Kamar 101" and pertama["latihan"] == "tidak"
    assert (pertama["detik_sampai_respons"], pertama["detik_sampai_ditangani"]) == ("40", "100")
    assert (pertama["putusan"], pertama["alasan_palsu"]) == ("Alarm palsu", "Berbaring sengaja")
    assert (pertama["ambang_detik"], pertama["lama_tergeletak_detik"], pertama["mode_deteksi"]) == ("3", "5", "pose")
    assert pertama["telegram"] == "terkirim" and pertama["catatan"] == "Pasien tidur, posisi miring"
    assert (baris[0]["detik_sampai_respons"], baris[0]["detik_sampai_ditangani"]) == ("150", "150")
    assert baris[0]["telegram"] == "gagal" and baris[1]["latihan"] == "ya"
    assert baris[1]["detik_sampai_respons"] == "", "belum direspons, sel dibiarkan kosong"


def test_ekspor_csv_memakai_filter_daftar(uji):
    baris = _baris_csv(uji.klien.get("/api/alerts/ekspor", params={"simulated": "false"}))
    assert [b["id"] for b in baris] == ["3", "1"]
    baris = _baris_csv(uji.klien.get("/api/alerts/ekspor", params={"camera_id": "cam-02"}))
    assert [b["id"] for b in baris] == ["2"]


def test_ekspor_csv_menjinakkan_rumus(uji):
    """Nama Telegram ditulis orang luar; jangan sampai menjadi rumus di spreadsheet."""
    _isi(uji, 1, claimed_by='=HYPERLINK("http://contoh.invalid","klik") (Telegram)',
         caregiver_note="-2+3")
    pertama = _baris_csv(uji.klien.get("/api/alerts/ekspor"))[2]
    assert pertama["diklaim_oleh"].startswith("'=HYPERLINK")
    assert pertama["catatan"] == "'-2+3"


def test_pengunjung_tidak_bisa_mengunduh(uji):
    _sebagai(uji, SimpleNamespace(id=0, display_name="Pengunjung", role="pengunjung", active=True))
    r = uji.klien.get("/api/alerts/ekspor")
    assert r.status_code == 403
    assert uji.klien.get("/api/alerts/").status_code == 200, "melihat daftar tetap boleh"


def test_klip_kejadian(uji, monkeypatch, tmp_path):
    from app.services import klip

    monkeypatch.setattr(klip, "get_settings",
                        lambda: SimpleNamespace(KLIP_DIR=str(tmp_path), KLIP_MASA_SIMPAN_HARI=7))
    r = uji.klien.get("/api/alerts/1/klip")
    assert r.status_code == 404 and r.json()["detail"] == "Klip tidak tersimpan untuk kejadian ini."
    _isi(uji, 1, klip_status="dihapus")
    assert "masa simpan" in uji.klien.get("/api/alerts/1/klip").json()["detail"]

    klip.tulis_berkas(1, [(10.0, b"\xff\xd8a"), (10.25, b"\xff\xd8b")], 10.0, 3.0)
    r = uji.klien.get("/api/alerts/1/klip")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert [f["t"] for f in r.json()["frame"]] == [0.0, 0.25]
    assert uji.klien.get("/api/alerts/99/klip").status_code == 404

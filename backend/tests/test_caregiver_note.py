"""
test_caregiver_note.py
======================
Catatan perawat: disimpan saat alert ditandai ditangani, bisa ditambah atau
diubah belakangan, dan tidak boleh hilang karena alert ditandai ulang.

Diuji lewat HTTP sungguhan (TestClient), karena bagian yang paling rawan adalah
body yang OPSIONAL: tombol "Tandai Ditangani" di tabel Riwayat Insiden tetap
mengirim PUT tanpa body sama sekali.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import alerts as api_alerts
from app.db.database import get_db
from app.db.models import AlertRecord, Base


@pytest.fixture
def klien():
    """TestClient dengan database SQLite in-memory yang dipakai bersama."""
    # StaticPool: satu koneksi untuk semua permintaan, supaya tabel in-memory
    # yang dibuat di sini terlihat oleh setiap request.
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(AlertRecord(camera_id="cam-01", message="uji", fall_duration=10.0))
            await s.commit()

    async def db_uji():
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(api_alerts.router, prefix="/api/alerts")
    app.dependency_overrides[get_db] = db_uji

    with TestClient(app) as c, \
            patch("app.api.alerts.manager.broadcast", new=AsyncMock()):
        c.portal.call(siapkan)
        yield c


def test_tandai_ditangani_dengan_catatan(klien):
    r = klien.put("/api/alerts/1/ack", json={"note": "  Dibantu duduk, tidak ada luka.  "})
    assert r.status_code == 200
    d = r.json()
    assert d["acknowledged"] is True
    assert d["caregiver_note"] == "Dibantu duduk, tidak ada luka.", "spasi di tepi harus dibuang"


def test_tandai_ditangani_tanpa_body_tetap_bisa(klien):
    """Tombol di tabel Riwayat Insiden mengirim PUT tanpa body."""
    r = klien.put("/api/alerts/1/ack")
    assert r.status_code == 200
    assert r.json()["acknowledged"] is True
    assert r.json()["caregiver_note"] is None


def test_menandai_ulang_tidak_menghapus_catatan(klien):
    klien.put("/api/alerts/1/ack", json={"note": "Dibantu duduk."})
    for body in (None, {"note": ""}, {"note": "   "}, {}):
        r = klien.put("/api/alerts/1/ack", json=body) if body is not None else klien.put("/api/alerts/1/ack")
        assert r.json()["caregiver_note"] == "Dibantu duduk.", f"catatan terhapus oleh body {body!r}"


def test_catatan_ditambah_dan_diubah_belakangan(klien):
    klien.put("/api/alerts/1/ack")                      # darurat: tandai dulu
    r = klien.put("/api/alerts/1/note", json={"note": "Lutut lecet, sudah dikompres."})
    assert r.status_code == 200
    assert r.json()["caregiver_note"] == "Lutut lecet, sudah dikompres."

    r = klien.put("/api/alerts/1/note", json={"note": "Lutut lecet; dokter jaga dihubungi."})
    assert r.json()["caregiver_note"] == "Lutut lecet; dokter jaga dihubungi."

    # Mengosongkan lewat endpoint catatan memang menghapusnya.
    r = klien.put("/api/alerts/1/note", json={"note": ""})
    assert r.json()["caregiver_note"] is None


def test_catatan_muncul_di_daftar_riwayat(klien):
    klien.put("/api/alerts/1/ack", json={"note": "Dibantu duduk."})
    daftar = klien.get("/api/alerts/").json()
    assert daftar[0]["caregiver_note"] == "Dibantu duduk."


def test_catatan_terlalu_panjang_ditolak(klien):
    r = klien.put("/api/alerts/1/note", json={"note": "x" * 501})
    assert r.status_code == 422


def test_alert_tidak_ada(klien):
    assert klien.put("/api/alerts/999/note", json={"note": "a"}).status_code == 404


# ---- Database lama --------------------------------------------

@pytest_asyncio.fixture
async def engine_lama():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    yield engine
    await engine.dispose()


@pytest.mark.asyncio
async def test_database_lama_mendapat_kolom_catatan_tanpa_kehilangan_riwayat(engine_lama):
    """Database yang dibuat sebelum fitur ini ada harus ditambal, bukan dihapus --
    riwayat alert yang sudah terkumpul adalah bukti."""
    from app.db.database import _tambal_kolom

    async with engine_lama.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY, camera_id VARCHAR NOT NULL, "
            "severity VARCHAR NOT NULL, message VARCHAR NOT NULL, fall_duration FLOAT NOT NULL, "
            "acknowledged BOOLEAN, created_at DATETIME, acknowledged_at DATETIME)"))
        await conn.execute(text(
            "INSERT INTO alerts (camera_id, severity, message, fall_duration, acknowledged) "
            "VALUES ('cam-01', 'critical', 'riwayat lama', 12.0, 1)"))

    async with engine_lama.begin() as conn:
        await _tambal_kolom(conn)

    async with engine_lama.begin() as conn:
        kolom = {b[1] for b in (await conn.execute(text("PRAGMA table_info(alerts)"))).fetchall()}
        isi = (await conn.execute(text("SELECT message, caregiver_note FROM alerts"))).fetchall()

    assert "caregiver_note" in kolom
    assert isi == [("riwayat lama", None)]

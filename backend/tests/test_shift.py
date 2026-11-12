"""
test_shift.py
=============
Ringkasan per shift untuk serah terima: batas shift dalam jam setempat, isi ringkasan,
dan tanda sudah dibaca.
"""

import types
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AlertRecord, Base, JedaKamera
from app.services import shift

TIGA = shift.POLA["3"]


@pytest.mark.parametrize("sekarang, geser, harapan", [
    ("2026-11-12 10:00", 0, ("Pagi", "2026-11-12 07:00", "2026-11-12 14:00")),
    ("2026-11-12 10:00", -1, ("Malam", "2026-11-11 21:00", "2026-11-12 07:00")),
    ("2026-11-12 03:00", 0, ("Malam", "2026-11-11 21:00", "2026-11-12 07:00")),
    ("2026-11-12 03:00", -1, ("Sore", "2026-11-11 14:00", "2026-11-11 21:00")),
    ("2026-11-12 14:00", 0, ("Sore", "2026-11-12 14:00", "2026-11-12 21:00")),
    ("2026-11-12 10:00", -7, ("Malam", "2026-11-09 21:00", "2026-11-10 07:00")),
])
def test_batas_tiga_shift(sekarang, geser, harapan):
    f = "%Y-%m-%d %H:%M"
    nama, mulai, selesai = shift.batas_shift(datetime.strptime(sekarang, f), TIGA, geser)
    assert (nama, mulai.strftime(f), selesai.strftime(f)) == harapan


def test_batas_dua_shift():
    nama, mulai, selesai = shift.batas_shift(datetime(2026, 11, 12, 20, 0), shift.POLA["2"])
    assert (nama, mulai, selesai) == ("Malam", datetime(2026, 11, 12, 19), datetime(2026, 11, 13, 7))


SEKARANG = datetime(2026, 11, 12, 15, 0)        # jam setempat: shift Sore berjalan
PAGI = shift.ke_utc(datetime(2026, 11, 12, 7, 0))


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    def alert(jam, **kolom):
        return AlertRecord(camera_id="cam-01", camera_name="Kamar 101", message="uji", fall_duration=3.0,
                           created_at=PAGI + timedelta(hours=jam), **kolom)

    async with factory() as s:
        s.add_all([
            alert(1, acknowledged=True, claimed_at=PAGI + timedelta(hours=1, seconds=30),
                  acknowledged_at=PAGI + timedelta(hours=1, minutes=2), verdict="jatuh",
                  caregiver_note="Penghuni sadar, dibantu duduk"),
            alert(2, acknowledged=True, acknowledged_at=PAGI + timedelta(hours=2, seconds=90)),   # belum dinilai
            alert(3),                                                                              # belum ditangani
            alert(4, simulated=True),                                                              # latihan
            alert(-1, verdict="palsu", acknowledged=True),                                         # shift sebelumnya
            JedaKamera(camera_id="cam-01", camera_name="Kamar 101", mulai=PAGI + timedelta(hours=5),
                       sampai=PAGI + timedelta(hours=8), oleh="Siti"),                             # melewati pergantian
        ])
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_ringkasan_shift_pagi(db):
    r = await shift.ringkasan(db, TIGA, -1, SEKARANG)
    assert (r.nama, r.berjalan, r.latihan) == ("Pagi", False, 1)
    assert (r.metrik.total, r.metrik.jatuh, r.metrik.belum_dinilai, r.metrik.belum_ditangani) == (3, 1, 1, 1)
    assert r.metrik.median_respons_detik == 60.0, "30 dan 90 detik"
    assert len(r.perlu_tindakan) == 2, "yang belum ditangani dan yang belum dinilai"
    assert [c.caregiver_note for c in r.catatan] == ["Penghuni sadar, dibantu duduk"]
    assert [j.oleh for j in r.jeda] == ["Siti"]
    assert r.kamera_terputus == [], "kamera terputus hanya untuk shift yang berjalan"
    assert r.dibaca_oleh is None


@pytest.mark.asyncio
async def test_tanda_sudah_dibaca(db):
    await shift.tandai_dibaca(db, TIGA, -1, "Budi", SEKARANG)
    await shift.tandai_dibaca(db, TIGA, -1, "Rina", SEKARANG)
    r = await shift.ringkasan(db, TIGA, -1, SEKARANG)
    assert r.dibaca_oleh == "Budi", "pembaca pertama yang dicatat"
    r = await shift.ringkasan(db, TIGA, 0, SEKARANG)
    assert (r.nama, r.dibaca_oleh, r.metrik.total) == ("Sore", None, 0)
    assert [j.oleh for j in r.jeda] == ["Siti"], "jeda yang melewati pergantian ikut di kedua shift"


def test_api_ringkasan_shift(monkeypatch):
    from app.api import shift as api_shift
    from app.api.auth import wajib_login
    from app.db.database import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def db_uji():
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(api_shift.router, prefix="/api/ringkasan-shift")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: types.SimpleNamespace(display_name="Siti", role="perawat")
    with TestClient(app) as c:
        c.portal.call(siapkan)
        r = c.get("/api/ringkasan-shift/", params={"geser": -1})
        assert r.status_code == 200 and r.json()["berjalan"] is False
        assert c.post("/api/ringkasan-shift/dibaca", params={"geser": 0}).status_code == 422, "shift berjalan"
        r = c.post("/api/ringkasan-shift/dibaca", params={"geser": -1})
        assert r.status_code == 200 and r.json()["dibaca_oleh"] == "Siti"

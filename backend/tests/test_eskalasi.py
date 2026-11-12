"""
test_eskalasi.py
================
Alarm tanpa respons: pengingat Telegram setiap N menit sebagai balasan ke pesan alarm,
paling banyak tiga kali, dan berhenti begitu ada yang merespons.
"""

import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AlertRecord, Base
from app.services import eskalasi

AWAL = datetime(2026, 11, 12, 7, 0, 0)


def _alert(**kolom):
    dasar = dict(id=1, camera_id="cam-01", camera_name="Kamar 101", message="uji", fall_duration=3.0,
                 created_at=AWAL, telegram_status="terkirim", telegram_message_id=501)
    dasar.update(kolom)
    return AlertRecord(**dasar)


@pytest.mark.parametrize("kolom, menit_lewat, harapan", [
    ({}, 1.9, False),
    ({}, 2.0, True),
    ({"eskalasi_ke": 1}, 3.0, False),
    ({"eskalasi_ke": 1}, 4.0, True),
    ({"eskalasi_ke": 3}, 60.0, False),
    ({"claimed_by": "Siti"}, 10.0, False),
    ({"acknowledged": True}, 10.0, False),
    ({"telegram_status": "mati"}, 10.0, False),
    ({"telegram_message_id": None}, 10.0, False),
])
def test_jatuh_tempo(kolom, menit_lewat, harapan):
    assert eskalasi.jatuh_tempo(_alert(**kolom), AWAL + timedelta(minutes=menit_lewat), 2) is harapan


def test_isi_pengingat():
    teks = eskalasi.susun_pengingat(_alert(camera_name="Kamar <101>"), AWAL + timedelta(minutes=2, seconds=30))
    assert "Belum ada yang merespons · 2 mnt" in teks
    assert "Kamar &lt;101&gt;" in teks, "nama ruang di-escape untuk HTML Telegram"
    assert eskalasi.susun_pengingat(_alert(simulated=True), AWAL).startswith("🧪 LATIHAN")


@pytest_asyncio.fixture
async def lingkungan(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            _alert(id=1),                                            # jatuh tempo
            _alert(id=2, claimed_by="Siti"),                         # sudah ada yang ke sana
            _alert(id=3, created_at=AWAL + timedelta(minutes=2)),    # belum dua menit
            _alert(id=4, telegram_status="mati", telegram_message_id=None),
        ])
        await s.commit()

    import app.db.database as database
    from app.services import notification_service as ns
    from app.websocket.ws_manager import manager

    terkirim: list[dict] = []
    hasil = {"ok": True}

    async def kirim_palsu(teks, label="pesan", balas_ke=None):
        terkirim.append({"teks": teks, "balas_ke": balas_ke})
        return hasil["ok"]

    siar = AsyncMock()
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    monkeypatch.setattr(ns, "dikonfigurasi", lambda: True)
    monkeypatch.setattr(ns, "kirim_teks", kirim_palsu)
    monkeypatch.setattr(manager, "broadcast", siar)
    monkeypatch.setattr(eskalasi, "_gagal_terakhir", {})
    yield types.SimpleNamespace(factory=factory, terkirim=terkirim, hasil=hasil, siar=siar)
    await engine.dispose()


async def _ke(lingkungan, alert_id):
    async with lingkungan.factory() as s:
        return (await s.get(AlertRecord, alert_id)).eskalasi_ke


@pytest.mark.asyncio
async def test_pengingat_membalas_pesan_alarm(lingkungan):
    assert await eskalasi.putaran(AWAL + timedelta(minutes=2, seconds=10)) == [1]
    [kirim] = lingkungan.terkirim
    assert kirim["balas_ke"] == 501
    assert await _ke(lingkungan, 1) == 1
    pesan = lingkungan.siar.await_args.args[0]
    assert pesan.event == "alert_update" and pesan.data["eskalasi_ke"] == 1

    assert await eskalasi.putaran(AWAL + timedelta(minutes=3)) == [], "pengingat kedua baru di menit ke-4"
    assert await eskalasi.putaran(AWAL + timedelta(minutes=4, seconds=5)) == [1, 3]
    assert await _ke(lingkungan, 1) == 2


@pytest.mark.asyncio
async def test_gagal_kirim_tidak_dihitung_dan_tidak_dihujani(lingkungan):
    lingkungan.hasil["ok"] = False
    assert await eskalasi.putaran(AWAL + timedelta(minutes=2, seconds=10)) == []
    assert await _ke(lingkungan, 1) is None
    assert await eskalasi.putaran(AWAL + timedelta(minutes=2, seconds=20)) == []
    assert len(lingkungan.terkirim) == 1, "tidak dicoba lagi sebelum jeda setelah gagal lewat"


@pytest.mark.asyncio
async def test_diam_bila_telegram_belum_diatur(lingkungan, monkeypatch):
    from app.services import notification_service as ns
    monkeypatch.setattr(ns, "dikonfigurasi", lambda: False)
    assert await eskalasi.putaran(AWAL + timedelta(minutes=10)) == []
    assert lingkungan.terkirim == []


@pytest.mark.asyncio
async def test_balasan_memakai_reply_parameters(monkeypatch):
    from app.services import notification_service as ns

    panggilan = []

    async def panggil_palsu(metode, json_=None, data=None, files=None, timeout=15.0):
        panggilan.append(json_)
        return True, "", {"result": {"message_id": 777}}

    monkeypatch.setattr(ns, "_panggil", panggil_palsu)
    await ns._kirim_sekali("halo", None, None, balas_ke=501)
    await ns._kirim_sekali("halo", None, None)
    assert panggilan[0]["reply_parameters"] == {"message_id": 501, "allow_sending_without_reply": True}
    assert "reply_parameters" not in panggilan[1]


def test_pengaturan_eskalasi():
    from app.api import settings as api_settings
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
    app.include_router(api_settings.router, prefix="/api/settings")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: types.SimpleNamespace(display_name="Siti", role="perawat")
    with TestClient(app) as c:
        c.portal.call(siapkan)
        assert c.get("/api/settings/").json()["eskalasi_menit"] == 2, "bawaan 2 menit"
        assert c.put("/api/settings/eskalasi", json={"eskalasi_menit": 0}).status_code == 422
        assert c.put("/api/settings/eskalasi", json={"eskalasi_menit": 31}).status_code == 422
        assert c.put("/api/settings/eskalasi", json={"eskalasi_menit": 5}).json()["eskalasi_menit"] == 5
        assert c.get("/api/settings/").json()["eskalasi_menit"] == 5

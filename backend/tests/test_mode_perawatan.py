"""
test_mode_perawatan.py
======================
Mode perawatan: jeda deteksi per kamera yang manual, berbatas waktu, tercatat, dan
tidak menayangkan video selama berjalan.
"""

import asyncio
import types
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.logging import utc_now_naive
from app.db.models import Base, CameraRecord, JedaKamera
from app.runtime.registry import registry
from app.services import mode_perawatan as mp


@pytest.fixture
def bersih(monkeypatch):
    """Registry kosong per tes, dan kabar Telegram dicatat, bukan dikirim."""
    monkeypatch.setattr(registry, "jeda", {})
    monkeypatch.setattr(registry, "state_machines", {})
    monkeypatch.setattr(registry, "simulasi_sampai", {})
    kabar: list[str] = []
    monkeypatch.setattr(mp, "_kabari", kabar.append)
    return kabar


@pytest_asyncio.fixture
async def db(bersih):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _baris(db):
    return (await db.execute(select(JedaKamera))).scalars().all()


# ---- Layanan ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mulai_mencatat_dan_menghentikan_hitungan(db, bersih):
    fsm = MagicMock()
    registry.state_machines["cam-01"] = fsm
    registry.simulasi_sampai["cam-01"] = 10**9

    jeda = await mp.mulai(db, "cam-01", "Kamar 101", 30, "Siti")

    assert mp.aktif("cam-01") is jeda
    assert jeda.sampai - utc_now_naive() == pytest.approx(timedelta(minutes=30), abs=timedelta(seconds=5))
    [baris] = await _baris(db)
    assert (baris.camera_name, baris.oleh, baris.selesai) == ("Kamar 101", "Siti", None)
    fsm.reset.assert_called_once()
    assert "cam-01" not in registry.simulasi_sampai, "latihan yang berjalan ikut berhenti"
    assert "Kamar 101 tidak dipantau sampai" in bersih[0] and "30 menit" in bersih[0]


@pytest.mark.asyncio
async def test_perpanjang_dibatasi_dua_jam(db, bersih):
    await mp.mulai(db, "cam-01", "Kamar 101", 60, "Siti")
    await mp.mulai(db, "cam-01", "Kamar 101", 15, "Budi")
    jeda = mp.aktif("cam-01")
    assert jeda.sampai - utc_now_naive() == pytest.approx(timedelta(minutes=75), abs=timedelta(seconds=5))
    await mp.mulai(db, "cam-01", "Kamar 101", 120, "Budi")
    assert jeda.sampai - utc_now_naive() <= timedelta(minutes=mp.MAKS_MENIT)
    assert len(await _baris(db)) == 1, "perpanjangan memakai baris yang sama"
    assert "diperpanjang" in bersih[1]


@pytest.mark.asyncio
async def test_akhiri_lebih_awal_tercatat(db, bersih):
    await mp.mulai(db, "cam-01", "Kamar 101", 30, "Siti")
    assert await mp.akhiri(db, "cam-01", "Kamar 101", "Budi") is True
    assert mp.aktif("cam-01") is None
    [baris] = await _baris(db)
    assert baris.diakhiri_oleh == "Budi" and baris.selesai is not None
    assert "dipantau lagi" in bersih[-1]
    assert await mp.akhiri(db, "cam-01", "Kamar 101", "Budi") is False


@pytest.mark.asyncio
async def test_jeda_dipulihkan_saat_backend_menyala(db, bersih):
    sekarang = utc_now_naive()
    db.add_all([
        JedaKamera(camera_id="cam-01", mulai=sekarang, sampai=sekarang + timedelta(minutes=10), oleh="Siti"),
        JedaKamera(camera_id="cam-02", mulai=sekarang, sampai=sekarang - timedelta(minutes=1), oleh="Siti"),
        JedaKamera(camera_id="cam-03", mulai=sekarang, sampai=sekarang + timedelta(minutes=10),
                   oleh="Siti", selesai=sekarang),
    ])
    await db.commit()
    await mp.muat_dari_db(db)
    assert set(registry.jeda) == {"cam-01"}


def test_jeda_habis_dilepas(bersih):
    registry.jeda["cam-01"] = mp.JedaAktif(id=1, sampai=utc_now_naive() - timedelta(seconds=1), oleh="Siti")
    assert mp.aktif("cam-01") is None
    assert mp.kedaluwarsa("cam-01") is True
    assert "cam-01" not in registry.jeda
    assert mp.kedaluwarsa("cam-01") is False


# ---- API -------------------------------------------------------------------------

@pytest.fixture
def api(bersih, monkeypatch):
    from app.api import cameras as api_cameras
    from app.api.auth import wajib_login
    from app.db.database import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add_all([CameraRecord(id="cam-01", name="Kamar 101", source="0"),
                       CameraRecord(id="cam-02", name="Kamar 102", source="1")])
            await s.commit()

    async def db_uji():
        async with factory() as s:
            yield s

    monkeypatch.setattr(registry, "cameras", {"cam-01": types.SimpleNamespace(sedang_mengalir=True)})
    app = FastAPI()
    app.include_router(api_cameras.router, prefix="/api/cameras")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: types.SimpleNamespace(display_name="Siti", role="perawat")
    with TestClient(app) as c:
        c.portal.call(siapkan)
        yield c


def test_api_mulai_dan_akhiri_jeda(api):
    assert api.post("/api/cameras/cam-01/jeda", json={"menit": 0}).status_code == 422
    assert api.post("/api/cameras/cam-01/jeda", json={"menit": 121}).status_code == 422
    assert api.post("/api/cameras/cam-99/jeda", json={"menit": 15}).status_code == 404
    assert api.post("/api/cameras/cam-02/jeda", json={"menit": 15}).status_code == 409, "kamera mati"

    r = api.post("/api/cameras/cam-01/jeda", json={"menit": 15})
    assert r.status_code == 200
    assert r.json()["dijeda_sampai"] and r.json()["dijeda_oleh"] == "Siti"
    latihan = api.post("/api/cameras/cam-01/simulate-fall")
    assert latihan.status_code == 409 and "Mode perawatan" in latihan.json()["detail"]

    r = api.delete("/api/cameras/cam-01/jeda")
    assert r.status_code == 200 and r.json()["dijeda_sampai"] is None
    assert api.delete("/api/cameras/cam-01/jeda").status_code == 200, "aman dipanggil dua kali"


# ---- Pipeline ------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_berhenti_selama_jeda_lalu_jalan_lagi(bersih, monkeypatch):
    from app.models.schemas import FallState
    from app.runtime.detection_pipeline import camera_pipeline
    from app.services.state_machine import FallStateMachine

    habis: list[str] = []
    monkeypatch.setattr(mp, "kabari_habis", habis.append)
    monkeypatch.setattr(registry, "latest_status", {})
    monkeypatch.setattr(registry, "latest_jpeg", {})
    cam = MagicMock(camera_id="cam-test", is_active=True, fps=10.0, waktu_frame_terakhir=None)
    cam.get_latest_frame.return_value = np.zeros((48, 64, 3), dtype=np.uint8)
    fsm = FallStateMachine(camera_id="cam-test", fall_duration_threshold=5.0, possible_fall_threshold=1.0)
    registry.jeda["cam-test"] = mp.JedaAktif(id=1, sampai=utc_now_naive() + timedelta(seconds=0.6), oleh="Siti")

    dipanggil: list[float] = []
    selama_jeda: dict = {}

    async def amati():
        await asyncio.sleep(0.3)
        selama_jeda["status"] = registry.latest_status.get("cam-test")
        selama_jeda["jpeg"] = registry.latest_jpeg.get("cam-test", "tidak ada")
        selama_jeda["inferensi"] = len(dipanggil)
        await asyncio.sleep(1.2)
        cam.is_active = False

    with patch("app.runtime.detection_pipeline.run_inference", side_effect=lambda f: dipanggil.append(1) or []), \
            patch("app.runtime.detection_pipeline.manager.broadcast", new=AsyncMock()):
        await asyncio.gather(camera_pipeline(cam, fsm), amati())

    assert selama_jeda["inferensi"] == 0, "model tidak dijalankan selama jeda"
    assert selama_jeda["jpeg"] is None, "video tidak ditayangkan selama jeda"
    assert selama_jeda["status"].dijeda_oleh == "Siti" and selama_jeda["status"].is_active
    assert habis == ["cam-test"] and "cam-test" not in registry.jeda
    assert len(dipanggil) > 0, "pemantauan berjalan lagi setelah jeda habis"
    assert fsm.state == FallState.MONITORING

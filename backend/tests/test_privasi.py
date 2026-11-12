"""
test_privasi.py
===============
Privasi per kamera: tampilan utuh, buram, atau kerangka saja, dan video asli yang hanya
bisa dibuka sementara saat ada alarm, tercatat, dan tidak untuk pengunjung.
"""

import types

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AksesVideo, AlertRecord, Base, CameraRecord
from app.models.schemas import CameraCreate
from app.runtime.registry import registry
from app.services.overlay import dasar_privasi


def _gambar():
    rng = np.random.default_rng(1)
    return rng.integers(0, 255, (240, 320, 3), dtype=np.uint8)


def test_dasar_privasi():
    asli = _gambar()
    assert dasar_privasi(asli, "utuh") is asli
    buram = dasar_privasi(asli, "buram")
    assert buram.shape == asli.shape
    assert np.abs(np.diff(buram.astype(int), axis=1)).mean() < np.abs(np.diff(asli.astype(int), axis=1)).mean() / 4, \
        "detail halus hilang"
    assert (dasar_privasi(asli, "kerangka") == 24).all(), "kerangka saja: tanpa gambar orang"


def test_jpeg_asli_hanya_saat_diminta_dan_berprivasi():
    from app.runtime.detection_pipeline import _jpeg_dan_klip

    settings = types.SimpleNamespace(CONFIDENCE_THRESHOLD=0.5, SHOW_UNCERTAIN_BOXES=True,
                                     TRIGGER_MIN_CONF=0.5, TRIGGER_CLASSES=["lying_on_ground"])
    _, _, asli = _jpeg_dan_klip(_gambar(), [], settings, False, "buram", True)
    assert asli is not None
    assert _jpeg_dan_klip(_gambar(), [], settings, False, "buram", False)[2] is None
    assert _jpeg_dan_klip(_gambar(), [], settings, False, "utuh", True)[2] is None


def test_kamera_baru_bawaannya_buram():
    assert CameraCreate(name="Kamar 101", source="0").privasi == "buram"


@pytest.mark.asyncio
async def test_kamera_lama_tetap_utuh_setelah_ditambal():
    from app.db.database import _tambal_kolom

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE cameras (id VARCHAR PRIMARY KEY, name VARCHAR NOT NULL, "
                                "source VARCHAR NOT NULL, rotate INTEGER NOT NULL, enabled BOOLEAN NOT NULL, "
                                "created_at DATETIME)"))
        await conn.execute(text("INSERT INTO cameras VALUES ('cam-01', 'Kamar 101', '0', 0, 1, NULL)"))
        await _tambal_kolom(conn)
        assert (await conn.execute(text("SELECT privasi FROM cameras"))).scalar() == "utuh"
    await engine.dispose()


@pytest.fixture
def api(monkeypatch):
    from app.api import cameras as api_cameras
    from app.api.auth import wajib_login
    from app.db.database import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add_all([CameraRecord(id="cam-01", name="Kamar 101", source="0", privasi="buram"),
                       CameraRecord(id="cam-02", name="Kamar 102", source="1", privasi="utuh")])
            await s.commit()

    async def db_uji():
        async with factory() as s:
            yield s

    async def tambah_alarm():
        async with factory() as s:
            s.add(AlertRecord(camera_id="cam-01", message="uji", fall_duration=3.0))
            await s.commit()

    async def akses():
        async with factory() as s:
            return (await s.execute(select(AksesVideo))).scalars().all()

    kamera = {"cam-01": types.SimpleNamespace(sedang_mengalir=True, privasi="buram"),
              "cam-02": types.SimpleNamespace(sedang_mengalir=True, privasi="utuh")}
    monkeypatch.setattr(registry, "cameras", kamera)
    monkeypatch.setattr(registry, "asli_sampai", {})
    masuk = {"akun": types.SimpleNamespace(display_name="Siti", role="perawat")}
    app = FastAPI()
    app.include_router(api_cameras.router, prefix="/api/cameras")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: masuk["akun"]
    with TestClient(app) as c:
        c.portal.call(siapkan)
        yield types.SimpleNamespace(klien=c, masuk=masuk, kamera=kamera,
                                    tambah_alarm=lambda: c.portal.call(tambah_alarm),
                                    akses=lambda: c.portal.call(akses))


def test_video_asli_hanya_saat_alarm_dan_tercatat(api):
    c = api.klien
    assert c.post("/api/cameras/cam-02/buka-asli").status_code == 409, "kamera utuh tidak perlu dibuka"
    r = c.post("/api/cameras/cam-01/buka-asli")
    assert r.status_code == 409 and "alarm" in r.json()["detail"]

    api.tambah_alarm()
    r = c.post("/api/cameras/cam-01/buka-asli")
    assert r.status_code == 200 and r.json()["asli_sampai"] and r.json()["privasi"] == "buram"
    [catatan] = api.akses()
    assert (catatan.camera_id, catatan.oleh, catatan.alert_id) == ("cam-01", "Siti", 1)

    api.masuk["akun"] = types.SimpleNamespace(display_name="Pengunjung", role="pengunjung")
    assert c.post("/api/cameras/cam-01/buka-asli").status_code == 403
    assert c.get("/api/cameras/cam-01/stream", params={"asli": "true"}).status_code == 403


def test_ubah_privasi_berlaku_tanpa_menyalakan_ulang(api):
    r = api.klien.patch("/api/cameras/cam-01", json={"privasi": "kerangka"})
    assert r.status_code == 200 and r.json()["privasi"] == "kerangka"
    assert api.kamera["cam-01"].privasi == "kerangka"
    assert api.klien.patch("/api/cameras/cam-01", json={"privasi": "telanjang"}).status_code == 422


def test_letak_denah(api):
    r = api.klien.patch("/api/cameras/cam-01", json={"denah_baris": 2, "denah_kolom": 3})
    assert (r.json()["denah_baris"], r.json()["denah_kolom"]) == (2, 3)
    r = api.klien.patch("/api/cameras/cam-01", json={"denah_baris": 0, "denah_kolom": 0})
    assert (r.json()["denah_baris"], r.json()["denah_kolom"]) == (None, None), "0 mengeluarkan dari denah"
    assert api.klien.patch("/api/cameras/cam-01", json={"denah_baris": 13}).status_code == 422

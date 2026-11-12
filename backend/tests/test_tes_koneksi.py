"""
test_tes_koneksi.py
===================
Tes koneksi kamera sebelum disimpan: pratinjau, ukuran setelah diputar, fps, dan alasan
yang jelas bila gagal.
"""

import types

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base, CameraRecord
from app.services.camera_service import tes_koneksi


@pytest.fixture
def video(tmp_path):
    jalur = tmp_path / "kamar.avi"
    tulis = cv2.VideoWriter(str(jalur), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    for i in range(30):
        tulis.write(np.full((48, 64, 3), i * 8, dtype=np.uint8))
    tulis.release()
    return str(jalur)


def test_tes_koneksi_berkas_video(video):
    h = tes_koneksi(video, rotate=90)
    assert h["ok"] is True
    assert (h["lebar"], h["tinggi"]) == (48, 64), "ukuran sesudah diputar 90 derajat"
    assert h["fps"] == 10.0, "fps bawaan berkas, bukan kecepatan baca"
    assert cv2.imdecode(np.frombuffer(h["jpeg"], np.uint8), cv2.IMREAD_COLOR) is not None


def test_tes_koneksi_gagal_dengan_alasan(tmp_path):
    h = tes_koneksi(str(tmp_path / "tidak-ada.mp4"))
    assert h["ok"] is False and "tidak ditemukan" in h["pesan"]
    assert tes_koneksi("ftp://192.0.2.1/x")["pesan"].startswith("Skema URL")


def test_api_tes_koneksi(video):
    from app.api import cameras as api_cameras
    from app.api.auth import wajib_login
    from app.db.database import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as s:
            s.add(CameraRecord(id="cam-01", name="Kamar 101", source="0"))
            await s.commit()

    async def db_uji():
        async with factory() as s:
            yield s

    app = FastAPI()
    app.include_router(api_cameras.router, prefix="/api/cameras")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: types.SimpleNamespace(display_name="Siti", role="perawat")
    with TestClient(app) as c:
        c.portal.call(siapkan)
        r = c.post("/api/cameras/tes", json={"source": video})
        assert r.status_code == 200 and r.json()["ok"] and r.json()["gambar"]
        r = c.post("/api/cameras/tes", json={"source": "0"})
        assert r.json() == {**r.json(), "ok": False}
        assert "sudah dipakai" in r.json()["pesan"]

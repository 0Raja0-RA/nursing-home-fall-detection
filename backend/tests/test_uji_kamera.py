"""
test_uji_kamera.py
==================
Halaman Uji Kamera: panel diagnostik dan Mode uji.
"""

import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.schemas import DetectionResult, PostureClass
from app.runtime.registry import registry


def test_rata_rata_diagnostik(monkeypatch):
    from app.runtime.detection_pipeline import _catat_diagnostik
    monkeypatch.setattr(registry, "diagnostik", {})
    _catat_diagnostik("cam-01", 0.050, 100.0)
    _catat_diagnostik("cam-01", 0.100, 100.1)
    d = registry.diagnostik["cam-01"]
    assert d["inferensi_ms"] == 60.0, "rata-rata bergerak, bukan nilai terakhir"
    assert d["fps_analisis"] == pytest.approx(10.0, abs=0.1)


@pytest.fixture
def klien(monkeypatch):
    from app.api import cameras as api_cameras
    from app.api.auth import wajib_login

    monkeypatch.setattr(registry, "cameras", {"cam-01": types.SimpleNamespace(fps=14.96, sedang_mengalir=True)})
    monkeypatch.setattr(registry, "latest_detection", {"cam-01": [
        DetectionResult(posture=PostureClass.LYING_ON_GROUND, confidence=0.8123, bbox=[10.4, 20.6, 110.2, 80.9]),
        DetectionResult(posture=PostureClass.NORMAL, confidence=0.55, bbox=None),
    ]})
    monkeypatch.setattr(registry, "diagnostik", {"cam-01": {"inferensi_ms": 42.5, "fps_analisis": 9.8, "terakhir": 1.0}})
    monkeypatch.setattr(registry, "uji_sampai", {})
    masuk = {"akun": types.SimpleNamespace(display_name="Siti", role="perawat")}
    app = FastAPI()
    app.include_router(api_cameras.router, prefix="/api/cameras")
    app.dependency_overrides[wajib_login] = lambda: masuk["akun"]
    with TestClient(app) as c:
        yield types.SimpleNamespace(klien=c, masuk=masuk)


def test_diagnostik_dan_mode_uji(klien):
    c = klien.klien
    d = c.get("/api/cameras/cam-01/diagnostik").json()
    assert d["deteksi"][0] == {"postur": "lying_on_ground", "keyakinan": 0.812, "kotak": [10, 21, 110, 81]}
    assert d["deteksi"][1]["kotak"] == []
    assert (d["inferensi_ms"], d["fps_tangkap"], d["fps_analisis"], d["uji_sampai"]) == (42.5, 15.0, 9.8, None)

    assert c.post("/api/cameras/cam-01/uji", json={"menit": 31}).status_code == 422
    assert c.post("/api/cameras/cam-01/uji", json={"menit": 10}).json()["uji_sampai"]
    assert registry.sedang_diuji("cam-01")
    assert c.delete("/api/cameras/cam-01/uji").json()["uji_sampai"] is None
    assert not registry.sedang_diuji("cam-01")
    assert c.get("/api/cameras/cam-99/diagnostik").status_code == 404

    klien.masuk["akun"] = types.SimpleNamespace(display_name="Pengunjung", role="pengunjung")
    assert c.get("/api/cameras/cam-01/diagnostik").status_code == 403

"""
test_log_pengaturan.py
======================
Log perubahan pengaturan (siapa mengubah apa, kapan, dari nilai berapa ke berapa)
dan masa simpan foto serta klip yang ditampilkan di Pengaturan.
"""

import types

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import Base

PERAWAT = types.SimpleNamespace(display_name="Siti", role="perawat")


def _klien(pengguna) -> TestClient:
    from app.api import settings as api_settings
    from app.api.auth import wajib_login
    from app.db.database import get_db

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def db_uji():
        async with factory() as s:
            yield s

    async def siapkan():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    app.include_router(api_settings.router, prefix="/api/settings")
    app.dependency_overrides[get_db] = db_uji
    app.dependency_overrides[wajib_login] = lambda: pengguna
    klien = TestClient(app)
    klien.siapkan = siapkan
    return klien


def test_perubahan_pengaturan_tercatat():
    from app.core.config import get_settings
    from app.services import inference_service

    ambang_semula = get_settings().FALL_DURATION_THRESHOLD
    try:
        with _klien(PERAWAT) as c:
            c.portal.call(c.siapkan)
            sama = c.put("/api/settings/threshold", json={"fall_duration_threshold": ambang_semula})
            assert sama.status_code == 200
            assert c.get("/api/settings/riwayat").json() == [], "nilai yang tidak berubah tidak dicatat"

            c.put("/api/settings/threshold", json={"fall_duration_threshold": 12.5})
            c.put("/api/settings/mode", json={"detection_mode": "bbox" if inference_service.mode_aktif() == "pose" else "pose"})
            c.put("/api/settings/telegram", json={"photo_mode": "utuh", "send_drills": False})
            c.put("/api/settings/eskalasi", json={"eskalasi_menit": 5})
            riwayat = c.get("/api/settings/riwayat").json()
            assert len(c.get("/api/settings/riwayat", params={"limit": 2}).json()) == 2
    finally:
        get_settings().FALL_DURATION_THRESHOLD = ambang_semula
        inference_service.unload_model()

    assert [r["kunci"] for r in riwayat] == [
        "eskalasi_menit", "telegram_photo_mode", "detection_mode", "fall_duration_threshold",
    ], "terbaru lebih dulu; latihan Telegram tidak berubah jadi tidak dicatat"
    assert all(r["oleh"] == "Siti" and r["waktu"] for r in riwayat)
    ambang = riwayat[-1]
    assert (ambang["label"], ambang["nilai_lama"], ambang["nilai_baru"]) == (
        "Tunggu sebelum alarm (detik)", f"{ambang_semula:g}", "12.5")
    assert (riwayat[0]["nilai_lama"], riwayat[0]["nilai_baru"]) == ("2", "5")
    assert (riwayat[1]["nilai_lama"], riwayat[1]["nilai_baru"]) == ("buram", "utuh")


def test_masa_simpan_terlihat_di_pengaturan():
    from app.core.config import get_settings

    with _klien(PERAWAT) as c:
        c.portal.call(c.siapkan)
        s = c.get("/api/settings/").json()
    assert s["foto_masa_simpan_hari"] == get_settings().FOTO_MASA_SIMPAN_HARI
    assert s["klip_masa_simpan_hari"] == get_settings().KLIP_MASA_SIMPAN_HARI


def test_riwayat_perubahan_hanya_untuk_tim():
    with _klien(types.SimpleNamespace(display_name="Pengunjung pameran", role="pengunjung")) as c:
        c.portal.call(c.siapkan)
        assert c.get("/api/settings/riwayat").status_code == 403

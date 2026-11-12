"""
test_klip.py
============
Klip sebelum dan sesudah kejadian: penyangga frame, potongan di sekitar alarm,
berkas klip, masa simpan, dan endpoint-nya.
"""

import base64
import os
import time
import types
from unittest.mock import AsyncMock

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AlertRecord, Base
from app.services import klip


@pytest.fixture
def setelan(monkeypatch, tmp_path):
    """Folder klip sementara dan masa simpan yang bisa diubah per tes."""
    nilai = types.SimpleNamespace(KLIP_DIR=str(tmp_path / "klip"), KLIP_MASA_SIMPAN_HARI=7,
                                  FOTO_MASA_SIMPAN_HARI=30)
    monkeypatch.setattr(klip, "get_settings", lambda: nilai)
    return nilai


def _isi_penyangga(p, camera_id, dari, sampai):
    """Frame tiap 0,1 detik seperti pipeline 10 fps; penyangga sendiri yang menjarangkan."""
    t = dari
    while t <= sampai + 1e-9:
        if p.perlu_frame(camera_id, t):
            p.tambah(camera_id, t, f"jpeg@{t:.2f}".encode())
        t += 0.1


# ---- Penyangga -----------------------------------------------------------------

def test_penyangga_menjarangkan_dan_membuang_frame_lama(setelan):
    p = klip.PenyanggaKlip()
    _isi_penyangga(p, "cam-01", 1000.0, 1040.0)
    frame = p.potong("cam-01", 0, 10_000)
    jarak = [b[0] - a[0] for a, b in zip(frame, frame[1:])]
    assert min(jarak) >= 1 / klip.FPS - 1e-6, "paling banyak FPS frame per detik"
    assert frame[-1][0] - frame[0][0] <= klip.BUFFER_DETIK, "hanya BUFFER_DETIK detik terakhir"
    assert frame[0][0] > 1005.0, "frame awal sudah dibuang"
    assert p.potong("cam-02", 0, 10_000) == []


def test_penyangga_diam_bila_klip_dimatikan(setelan):
    setelan.KLIP_MASA_SIMPAN_HARI = 0
    assert not klip.PenyanggaKlip().perlu_frame("cam-01", 1000.0)


def test_pipeline_membuat_jpeg_kecil_hanya_bila_diminta():
    import cv2

    from app.runtime.detection_pipeline import _jpeg_dan_klip

    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    settings = types.SimpleNamespace(CONFIDENCE_THRESHOLD=0.5, SHOW_UNCERTAIN_BOXES=True,
                                     TRIGGER_MIN_CONF=0.5, TRIGGER_CLASSES=["lying_on_ground"])
    besar, kecil, _ = _jpeg_dan_klip(frame, [], settings, True)
    gambar = cv2.imdecode(np.frombuffer(kecil, np.uint8), cv2.IMREAD_COLOR)
    assert gambar.shape[:2] == (360, klip.LEBAR)
    assert cv2.imdecode(np.frombuffer(besar, np.uint8), cv2.IMREAD_COLOR).shape[:2] == (720, 1280)
    assert _jpeg_dan_klip(frame, [], settings, False)[1] is None


# ---- Berkas dan masa simpan -------------------------------------------------------

def test_berkas_klip_bolak_balik(setelan):
    frame = [(100.0 + i * 0.25, f"jpeg-{i}".encode()) for i in range(5)]
    klip.tulis_berkas(7, frame, waktu_alarm=100.5, detik_tergeletak=3.0)

    isi = klip.baca_berkas(7)
    assert [f["t"] for f in isi["frame"]] == [-0.5, -0.25, 0.0, 0.25, 0.5]
    assert base64.b64decode(isi["frame"][2]["jpeg"]) == b"jpeg-2"
    assert isi["detik_tergeletak"] == 3.0
    assert "dihapus_pada" in isi
    assert not list(klip.folder().glob("*.tmp")), "berkas sementara sudah diganti nama"
    assert klip.baca_berkas(8) is None


def test_klip_kedaluwarsa_dihapus(setelan):
    klip.tulis_berkas(1, [(0.0, b"a")], 0.0, 3.0)
    klip.tulis_berkas(2, [(0.0, b"b")], 0.0, 3.0)
    lama = time.time() - 8 * 86400
    os.utime(klip.jalur(1), (lama, lama))

    assert klip.hapus_kedaluwarsa() == [1]
    assert not klip.jalur(1).exists() and klip.jalur(2).exists()


def test_semua_klip_dihapus_bila_perekaman_dimatikan(setelan):
    klip.tulis_berkas(2, [(0.0, b"b")], 0.0, 3.0)
    setelan.KLIP_MASA_SIMPAN_HARI = 0
    assert klip.hapus_kedaluwarsa() == [2]


# ---- Merekam sesudah alarm ----------------------------------------------------------

@pytest_asyncio.fixture
async def db(monkeypatch, setelan):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(AlertRecord(id=1, camera_id="cam-01", message="uji", fall_duration=3.0, klip_status="merekam"))
        await s.commit()

    import app.db.database as database
    from app.websocket.ws_manager import manager
    siar = AsyncMock()
    monkeypatch.setattr(database, "get_session_factory", lambda: factory)
    monkeypatch.setattr(manager, "broadcast", siar)
    monkeypatch.setattr(klip, "penyangga", klip.PenyanggaKlip())
    yield types.SimpleNamespace(factory=factory, siar=siar)
    await engine.dispose()


async def _alert(db):
    async with db.factory() as s:
        return await s.get(AlertRecord, 1)


@pytest.mark.asyncio
async def test_rekam_memotong_dari_sebelum_tergeletak_sampai_sesudah_alarm(db):
    alarm = 5000.0
    _isi_penyangga(klip.penyangga, "cam-01", alarm - 29, alarm + klip.DETIK_SESUDAH + 2)

    await klip.rekam(1, "cam-01", alarm, detik_tergeletak=3.0, tunggu=0)

    isi = klip.baca_berkas(1)
    waktu = [f["t"] for f in isi["frame"]]
    assert waktu[0] >= -(3.0 + klip.JEDA_SEBELUM_TERGELETAK) and waktu[0] < -7.5
    assert waktu[-1] <= klip.DETIK_SESUDAH and waktu[-1] > 4.5
    alert = await _alert(db)
    assert alert.klip_status == "tersimpan"
    assert alert.klip_detik == pytest.approx(waktu[-1] - waktu[0], abs=0.11)
    pesan = db.siar.await_args.args[0]
    assert pesan.event == "alert_update" and pesan.data["klip_status"] == "tersimpan"


@pytest.mark.asyncio
async def test_bagian_sebelum_alarm_dibatasi(db):
    alarm = 5000.0
    _isi_penyangga(klip.penyangga, "cam-01", alarm - 29, alarm + klip.DETIK_SESUDAH)
    await klip.rekam(1, "cam-01", alarm, detik_tergeletak=60.0, tunggu=0)
    assert klip.baca_berkas(1)["frame"][0]["t"] >= -klip.DETIK_SEBELUM_MAKS


@pytest.mark.asyncio
async def test_rekam_tanpa_gambar_berstatus_kosong(db):
    await klip.rekam(1, "cam-01", 5000.0, detik_tergeletak=3.0, tunggu=0)
    assert (await _alert(db)).klip_status == "kosong"
    assert klip.baca_berkas(1) is None


@pytest.mark.asyncio
async def test_pembersih_menandai_klip_yang_dihapus(db):
    klip.tulis_berkas(1, [(0.0, b"a")], 0.0, 3.0)
    lama = time.time() - 8 * 86400
    os.utime(klip.jalur(1), (lama, lama))
    await klip.bersihkan()
    assert (await _alert(db)).klip_status == "dihapus"


@pytest.mark.asyncio
async def test_foto_kejadian_kedaluwarsa_dihapus(db, setelan):
    from datetime import timedelta

    from app.core.logging import utc_now_naive
    from app.db.models import AlertSnapshot

    sekarang = utc_now_naive()
    async with db.factory() as s:
        s.add(AlertRecord(id=2, camera_id="cam-01", message="uji", fall_duration=3.0))
        s.add(AlertSnapshot(alert_id=1, jpeg=b"lama", created_at=sekarang - timedelta(days=31)))
        s.add(AlertSnapshot(alert_id=2, jpeg=b"baru", created_at=sekarang - timedelta(days=29)))
        await s.commit()

    assert await klip.hapus_foto_kedaluwarsa(sekarang) == 1
    async with db.factory() as s:
        assert await s.get(AlertSnapshot, 1) is None
        assert (await s.get(AlertSnapshot, 2)).jpeg == b"baru"

    setelan.FOTO_MASA_SIMPAN_HARI = 0
    assert await klip.hapus_foto_kedaluwarsa(sekarang + timedelta(seconds=1)) == 1, "0: semua foto dihapus"

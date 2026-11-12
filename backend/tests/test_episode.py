"""
test_episode.py
===============
Episode berbaring dan pratinjau ambang: alarm mana yang hilang bila ambang dinaikkan,
dan berapa tambahan bila diturunkan.
"""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.logging import utc_now_naive
from app.db.models import AlertRecord, Base, EpisodeBerbaring
from app.models.schemas import FallState
from app.services import episode as ep


@pytest.mark.asyncio
async def test_pencatat_merekam_satu_episode(monkeypatch):
    simpan = AsyncMock()
    monkeypatch.setattr(ep, "_simpan", simpan)
    p = ep.PencatatEpisode()

    assert p.amati("cam-01", FallState.MONITORING, 0.0, False) is None
    p.amati("cam-01", FallState.POSSIBLE_FALL, 1.0, False)
    p.amati("cam-01", FallState.CONFIRMED_FALL, 3.2, False)
    p.amati("cam-01", FallState.CONFIRMED_FALL, 7.5, False)
    p.tandai_dipotong("cam-01")
    selesai = p.amati("cam-01", FallState.MONITORING, 0.0, False)

    assert (selesai.durasi_maks, selesai.alarm, selesai.dipotong, selesai.latihan) == (7.5, True, True, False)
    assert selesai.selesai >= selesai.mulai
    await p._tugas.pop() if p._tugas else None
    simpan.assert_awaited_once()
    assert p.amati("cam-01", FallState.MONITORING, 0.0, False) is None, "episode tidak tercatat dua kali"


@pytest.mark.asyncio
async def test_episode_tanpa_alarm_dan_latihan(monkeypatch):
    monkeypatch.setattr(ep, "_simpan", AsyncMock())
    p = ep.PencatatEpisode()
    p.amati("cam-02", FallState.POSSIBLE_FALL, 1.8, True)
    selesai = p.amati("cam-02", FallState.UNKNOWN, 0.0, False)      # kamera putus juga mengakhiri
    assert (selesai.durasi_maks, selesai.alarm, selesai.latihan) == (1.8, False, True)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    sekarang = utc_now_naive()

    def episode(menit_lalu, maks, alarm, dipotong=False, latihan=False):
        mulai = sekarang - timedelta(minutes=menit_lalu)
        return EpisodeBerbaring(camera_id="cam-01", mulai=mulai, selesai=mulai + timedelta(seconds=maks + 1),
                                durasi_maks=maks, alarm=alarm, dipotong=dipotong, latihan=latihan)

    def alert(menit_lalu, verdict):
        return AlertRecord(camera_id="cam-01", message="uji", fall_duration=3.0, verdict=verdict,
                           created_at=sekarang - timedelta(minutes=menit_lalu) + timedelta(seconds=3))

    async with factory() as s:
        s.add_all([
            # Pada ambang 3 detik: empat alarm dan dua episode yang tidak sampai berbunyi.
            episode(100, 4.0, True), alert(100, "palsu"),               # bangun sendiri di detik 4
            episode(90, 60.0, True), alert(90, "jatuh"),                # tergeletak lama
            episode(80, 3.5, True, dipotong=True), alert(80, "palsu"),  # ditutup di detik 3,5
            episode(70, 4.5, True), alert(70, "jatuh"),                 # jatuh, cepat ditolong bangun
            episode(60, 2.0, False),
            episode(50, 2.8, False),
            episode(40, 9.0, True, latihan=True),                       # latihan tidak dihitung
            episode(60 * 24 * 40, 9.0, True),                           # di luar 30 hari
        ])
        await s.commit()
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_pratinjau_ambang_dinaikkan(db):
    hasil = await ep.pratinjau(db, ambang=5.0, ambang_kini=3.0)
    assert hasil["episode"] == 6
    assert hasil["hilang"] == {"palsu": 1, "jatuh": 1}, "yang hilang tidak hanya alarm palsu"
    assert hasil["belum_tentu"] == 1, "alarm yang ditutup di detik 3,5 tidak bisa dipastikan"
    assert hasil["tambahan"] == 0
    assert hasil["berbunyi"] == 2


@pytest.mark.asyncio
async def test_pratinjau_ambang_diturunkan(db):
    hasil = await ep.pratinjau(db, ambang=2.0, ambang_kini=3.0)
    assert hasil["hilang"] == {} and hasil["belum_tentu"] == 0
    assert hasil["tambahan"] == 2, "dua episode di bawah 3 detik akan berbunyi"
    assert hasil["berbunyi"] == 6

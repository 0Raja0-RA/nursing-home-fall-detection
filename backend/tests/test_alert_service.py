"""
test_alert_service.py
=====================
Uji alur alert dari CONFIRMED_FALL sampai tercatat: database, WebSocket, lalu
Telegram.

Tidak menyentuh Telegram sungguhan dan tidak butuh jaringan -- pengirimnya
diganti fungsi tiruan yang mencatat apa yang diterimanya.
"""

import asyncio
import time

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repository import AlertRepository, CameraRepository
from app.models.schemas import CameraCreate
from app.services import alert_service as mod


@pytest_asyncio.fixture
async def lingkungan(monkeypatch):
    """Database sementara + penangkap panggilan WebSocket dan Telegram."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Satu kamera terdaftar, supaya nama kamarnya bisa dipakai di pesan.
    async with factory() as s:
        await CameraRepository(s).create_camera(
            CameraCreate(name="Kamar 01 - Jenderal Ilham", source="0"), camera_id="cam-01"
        )

    urutan: list[str] = []
    ws_pesan: list = []
    tg_panggilan: list[dict] = []
    hasil_telegram = {"ok": True}

    async def broadcast_palsu(msg):
        urutan.append("websocket")
        ws_pesan.append(msg)

    async def telegram_palsu(camera_name, fall_duration, foto=None, waktu=None,
                             message=None, simulasi=False):
        urutan.append("telegram")
        tg_panggilan.append({
            "camera_name": camera_name, "fall_duration": fall_duration,
            "foto": foto, "simulasi": simulasi,
        })
        return hasil_telegram["ok"]

    monkeypatch.setattr(mod, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mod.manager, "broadcast", broadcast_palsu)
    monkeypatch.setattr(
        "app.services.notification_service.send_telegram_alert", telegram_palsu
    )

    from app.runtime.registry import registry
    registry.latest_jpeg["cam-01"] = b"\xff\xd8potret-palsu\xff\xd9"

    yield {
        "factory": factory, "urutan": urutan, "ws": ws_pesan,
        "telegram": tg_panggilan, "hasil_telegram": hasil_telegram,
    }

    registry.latest_jpeg.pop("cam-01", None)
    await engine.dispose()


def _service() -> mod.AlertService:
    """AlertService baru, supaya cooldown satu uji tidak bocor ke uji lain."""
    return mod.AlertService()


@pytest.mark.asyncio
async def test_alert_tersimpan_dengan_nama_kamar(lingkungan):
    """Perawat mengenal nama kamar, bukan cam-01."""
    await _service().process_confirmed_fall("cam-01", 12.3)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert len(alerts) == 1
    assert "Kamar 01 - Jenderal Ilham" in alerts[0].message
    assert alerts[0].camera_id == "cam-01"
    assert alerts[0].fall_duration == pytest.approx(12.3)


@pytest.mark.asyncio
async def test_websocket_disiarkan_sebelum_telegram(lingkungan):
    """Dashboard harus menyala seketika, tidak menunggu jaringan.

    Kalau Telegram dipanggil lebih dulu, perawat yang sedang menatap dashboard
    ikut menunggu timeout HTTP -- bisa belasan detik saat jaringan bermasalah.
    """
    await _service().process_confirmed_fall("cam-01", 10.0)

    assert lingkungan["urutan"] == ["websocket", "telegram"]


@pytest.mark.asyncio
async def test_potret_ikut_dikirim(lingkungan):
    """Frame beranotasi sudah ada di registry, jadi melampirkannya gratis."""
    await _service().process_confirmed_fall("cam-01", 10.0)

    panggilan = lingkungan["telegram"][0]
    assert panggilan["foto"] == b"\xff\xd8potret-palsu\xff\xd9"
    assert panggilan["camera_name"] == "Kamar 01 - Jenderal Ilham"


@pytest.mark.asyncio
async def test_notified_true_saat_berhasil(lingkungan):
    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()
    assert alerts[0].notified is True


@pytest.mark.asyncio
async def test_telegram_gagal_tidak_membatalkan_alert(lingkungan):
    """Telegram itu lapisan kedua. Kegagalannya harus tercatat, bukan menghapus alert."""
    lingkungan["hasil_telegram"]["ok"] = False

    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert len(alerts) == 1, "alert tetap harus tersimpan"
    assert alerts[0].notified is False, "kegagalan harus terlihat, bukan hilang diam-diam"
    assert len(lingkungan["ws"]) == 1, "dashboard tetap harus diberi tahu"


@pytest.mark.asyncio
async def test_cooldown_menahan_alert_beruntun(lingkungan):
    """Satu orang yang tergeletak lama tidak boleh membanjiri grup perawat."""
    svc = _service()
    await svc.process_confirmed_fall("cam-01", 10.0)
    await svc.process_confirmed_fall("cam-01", 11.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert len(alerts) == 1
    assert len(lingkungan["telegram"]) == 1


@pytest.mark.asyncio
async def test_kamera_tak_dikenal_tetap_mengirim_alert(lingkungan):
    """Kamera yang sudah dihapus dari daftar tidak boleh membuat alert hilang.

    Namanya jatuh balik ke camera_id, tapi peringatannya tetap sampai.
    """
    await _service().process_confirmed_fall("cam-99", 10.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert len(alerts) == 1
    assert "cam-99" in alerts[0].message
    assert lingkungan["telegram"][0]["camera_name"] == "cam-99"
    assert lingkungan["telegram"][0]["foto"] is None


# ---- Simulasi jatuh ----------------------------------------

@pytest.mark.asyncio
async def test_alert_simulasi_ditandai_dan_diberi_awalan(lingkungan):
    """Alert dari tombol simulasi tidak boleh tertukar dengan kejadian nyata.

    Sistem deteksi jatuh yang bisa memunculkan alarm tanpa meninggalkan jejak
    membuat seluruh riwayat insidennya kehilangan nilai sebagai bukti.
    """
    import time

    from app.runtime.registry import registry

    registry.simulasi_sampai["cam-01"] = time.monotonic() + 30
    try:
        await _service().process_confirmed_fall("cam-01", 10.0)
    finally:
        registry.simulasi_sampai.pop("cam-01", None)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert alerts[0].simulated is True
    assert alerts[0].message.startswith("[SIMULASI]")
    assert lingkungan["telegram"][0]["simulasi"] is True
    assert lingkungan["ws"][0].data["simulated"] is True


@pytest.mark.asyncio
async def test_alert_biasa_tidak_tertandai_simulasi(lingkungan):
    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert alerts[0].simulated is False
    assert not alerts[0].message.startswith("[SIMULASI]")
    assert lingkungan["telegram"][0]["simulasi"] is False


def test_masa_simulasi_berakhir_sendiri():
    """Simulasi dibatasi waktu, bukan tombol mati/hidup.

    Kalau tidak, satu kali tekan bisa membuat kamera berbohong selamanya saat
    seseorang lupa mematikannya.
    """
    import time

    from app.runtime.registry import registry

    registry.simulasi_sampai["cam-uji"] = time.monotonic() + 0.3
    assert registry.sedang_disimulasikan("cam-uji") is True
    time.sleep(0.4)
    assert registry.sedang_disimulasikan("cam-uji") is False
    registry.simulasi_sampai.pop("cam-uji", None)


def test_kamera_tanpa_simulasi_tidak_pernah_dianggap_disimulasikan():
    from app.runtime.registry import registry
    assert registry.sedang_disimulasikan("cam-entah") is False


def test_waktu_pesan_dikonversi_dari_utc_ke_jam_setempat():
    """created_at tersimpan UTC; pesan Telegram harus memakai jam setempat."""
    from datetime import datetime, timezone

    utc = datetime(2026, 10, 10, 13, 53, 17)
    hasil = mod.AlertService._waktu_lokal(utc)
    harapan = utc.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert hasil == harapan


@pytest.mark.asyncio
async def test_menandai_ditangani_disiarkan_ke_semua_dashboard():
    """Banner alarm harus hilang di semua layar, bukan hanya di layar tempat
    tombolnya diklik -- termasuk saat ditangani dari halaman Riwayat Insiden."""
    from unittest.mock import AsyncMock, patch

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.alerts import acknowledge_alert
    from app.db.models import AlertRecord, Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as sesi:
            sesi.add(AlertRecord(camera_id="cam-01", message="uji", fall_duration=10.0))
            await sesi.commit()

            with patch("app.api.alerts.manager.broadcast", new=AsyncMock()) as siar:
                hasil = await acknowledge_alert(1, sesi)

        assert hasil.acknowledged
        pesan = siar.await_args.args[0]
        assert pesan.event == "alert_ack" and pesan.data == {"id": 1}
    finally:
        await engine.dispose()


# ---- "Tandai Ditangani" menutup insiden di kamera ----------

def _fsm_dalam_keadaan(state_tujuan):
    """State machine sungguhan yang dibawa ke keadaan tertentu lewat observasi."""
    from app.models.schemas import FallState, Observation
    from app.services.state_machine import FallStateMachine

    fsm = FallStateMachine(camera_id="cam-03", fall_duration_threshold=0.05,
                           possible_fall_threshold=0.0)
    for _ in range(40):
        fsm.update(Observation.TRIGGER_POSTURE)
        if fsm.state == state_tujuan:
            break
        if state_tujuan == FallState.POSSIBLE_FALL:
            break
        time.sleep(0.01)
    return fsm


@pytest_asyncio.fixture
async def db_alert():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sesi:
        yield sesi
    await engine.dispose()


async def _tambah_alert(sesi, camera_id="cam-03"):
    from app.db.models import AlertRecord
    a = AlertRecord(camera_id=camera_id, message="uji", fall_duration=5.0)
    sesi.add(a)
    await sesi.commit()
    return a.id


@pytest.mark.asyncio
async def test_ditangani_mengembalikan_kamera_ke_monitoring(db_alert):
    """Kamera tersangkut di CONFIRMED_FALL setelah alarm ditangani: deteksi yang
    ragu-ragu menahan timer, jadi tidak ada observasi yang bisa mengeluarkannya."""
    from unittest.mock import AsyncMock, patch
    from app.api.alerts import acknowledge_alert
    from app.models.schemas import FallState, Observation
    from app.runtime.registry import registry

    fsm = _fsm_dalam_keadaan(FallState.CONFIRMED_FALL)
    assert fsm.state == FallState.CONFIRMED_FALL
    fsm.update(Observation.UNCERTAIN)            # wajah memenuhi frame
    assert fsm.state == FallState.CONFIRMED_FALL, "UNCERTAIN memang menahan state"

    registry.state_machines["cam-03"] = fsm
    registry.simulasi_sampai["cam-03"] = time.monotonic() + 30
    try:
        alert_id = await _tambah_alert(db_alert)
        with patch("app.api.alerts.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(alert_id, db_alert)
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0
        assert not registry.sedang_disimulasikan("cam-03"), "simulasi harus ikut berakhir"
    finally:
        registry.state_machines.pop("cam-03", None)
        registry.simulasi_sampai.pop("cam-03", None)


@pytest.mark.asyncio
async def test_alert_lama_tidak_mereset_kejadian_yang_sedang_berjalan(db_alert):
    """Menandai alert kemarin dari halaman Riwayat Insiden tidak boleh menghapus
    timer insiden yang sedang terjadi sekarang di kamera yang sama."""
    from unittest.mock import AsyncMock, patch
    from app.api.alerts import acknowledge_alert
    from app.models.schemas import FallState
    from app.runtime.registry import registry

    fsm = _fsm_dalam_keadaan(FallState.CONFIRMED_FALL)
    registry.state_machines["cam-03"] = fsm
    try:
        lama = await _tambah_alert(db_alert)
        await _tambah_alert(db_alert)            # insiden yang sedang berjalan
        with patch("app.api.alerts.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(lama, db_alert)
        assert fsm.state == FallState.CONFIRMED_FALL
    finally:
        registry.state_machines.pop("cam-03", None)


@pytest.mark.asyncio
async def test_jatuh_baru_yang_sedang_dihitung_tidak_ikut_terhapus(db_alert):
    from unittest.mock import AsyncMock, patch
    from app.api.alerts import acknowledge_alert
    from app.models.schemas import FallState
    from app.runtime.registry import registry

    fsm = _fsm_dalam_keadaan(FallState.POSSIBLE_FALL)
    fsm.fall_duration_threshold = 60.0            # pastikan belum terkonfirmasi
    assert fsm.state == FallState.POSSIBLE_FALL
    registry.state_machines["cam-03"] = fsm
    try:
        alert_id = await _tambah_alert(db_alert)
        with patch("app.api.alerts.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(alert_id, db_alert)
        assert fsm.state == FallState.POSSIBLE_FALL
    finally:
        registry.state_machines.pop("cam-03", None)

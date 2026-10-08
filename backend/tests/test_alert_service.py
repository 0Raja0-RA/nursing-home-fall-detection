"""
test_alert_service.py
=====================
Uji alur alert dari CONFIRMED_FALL sampai tercatat: database, WebSocket, lalu
Telegram.

Tidak menyentuh Telegram sungguhan dan tidak butuh jaringan -- pengirimnya
diganti fungsi tiruan yang mencatat apa yang diterimanya.
"""

import asyncio

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

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
import types

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.repository import AlertRepository, CameraRepository
from app.models.schemas import AlertResponse, CameraCreate, CameraUpdate
from app.services import alert_service as mod

# Pengganti akun yang sedang masuk, untuk memanggil endpoint langsung.
PERAWAT = types.SimpleNamespace(id=1, display_name="Perawat Uji", role="perawat", active=True)


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

    from app.services import notification_service as ns

    async def telegram_palsu(alert, foto=None, mode_foto="buram"):
        urutan.append("telegram")
        tg_panggilan.append({
            "camera_name": alert["camera_name"], "fall_duration": alert["fall_duration"],
            "foto": foto, "simulasi": alert["simulated"], "mode_foto": mode_foto,
        })
        ok = hasil_telegram["ok"]
        return ns.HasilKirim(ok, 501 if ok else None, bool(foto))

    disunting: list[dict] = []

    async def sunting_palsu(alert, message_id, dengan_foto, tahap=None):
        disunting.append({"alert": alert, "message_id": message_id})
        return True

    monkeypatch.setattr(mod, "get_session_factory", lambda: factory)
    monkeypatch.setattr(mod.manager, "broadcast", broadcast_palsu)
    monkeypatch.setattr(ns, "kirim_alert", telegram_palsu)
    monkeypatch.setattr(ns, "perbarui_pesan", sunting_palsu)
    # Seolah token dan chat id sudah diisi; pengirimnya tetap tiruan di atas.
    monkeypatch.setattr(ns, "dikonfigurasi", lambda: True)
    # Perekam klip dicatat saja: yang sungguhan menunggu beberapa detik lalu menulis berkas.
    from app.services import klip
    klip_dimulai: list[tuple] = []
    monkeypatch.setattr(klip, "mulai_rekam", lambda *a: klip_dimulai.append(a))
    monkeypatch.setattr(klip, "aktif", lambda: True)

    from app.runtime.registry import registry
    registry.latest_jpeg["cam-01"] = b"\xff\xd8potret-palsu\xff\xd9"

    yield {
        "factory": factory, "urutan": urutan, "ws": ws_pesan,
        "telegram": tg_panggilan, "hasil_telegram": hasil_telegram, "disunting": disunting,
        "klip": klip_dimulai,
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
async def test_alert_tetap_menyebut_ruang_saat_kejadian(lingkungan):
    """Kamera diganti namanya, dihapus, lalu kamera baru didaftarkan: riwayat tidak berubah."""
    await _service().process_confirmed_fall("cam-01", 12.3)

    async with lingkungan["factory"]() as s:
        repo = CameraRepository(s)
        await repo.update_camera("cam-01", CameraUpdate(name="Gudang"))
        await repo.delete_camera("cam-01")
        baru = await repo.create_camera(CameraCreate(name="Kamar Baru", source="rtsp://10.0.0.9:554/s"))
        alerts = await AlertRepository(s).get_recent_alerts()

    assert baru.id != "cam-01"
    assert alerts[0].camera_id == "cam-01"
    assert alerts[0].camera_name == "Kamar 01 - Jenderal Ilham"
    assert AlertResponse.model_validate(alerts[0]).camera_name == "Kamar 01 - Jenderal Ilham"


@pytest.mark.asyncio
async def test_nama_ruang_kosong_kalau_kamera_tidak_dikenal(lingkungan):
    """camera_id bukan nama ruang, jadi tidak boleh tersimpan sebagai nama."""
    await _service().process_confirmed_fall("cam-99", 10.0)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert alerts[0].camera_id == "cam-99"
    assert alerts[0].camera_name is None


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

    from app.db.repository import KUNCI_TG_LATIHAN, SettingRepository

    async with lingkungan["factory"]() as s:
        await SettingRepository(s).simpan(KUNCI_TG_LATIHAN, "1")   # latihan ikut dikirim

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
async def test_latihan_tidak_dikirim_ke_telegram_secara_bawaan(lingkungan):
    """Grup perawat yang sering menerima pesan latihan belajar mengabaikan pesan alarm."""
    from app.runtime.registry import registry

    registry.simulasi_sampai["cam-01"] = time.monotonic() + 30
    try:
        await _service().process_confirmed_fall("cam-01", 10.0)
    finally:
        registry.simulasi_sampai.pop("cam-01", None)

    async with lingkungan["factory"]() as s:
        alerts = await AlertRepository(s).get_recent_alerts()

    assert lingkungan["telegram"] == []
    assert alerts[0].telegram_status == "dilewati"
    assert len(lingkungan["ws"]) == 1, "dashboard tetap menampilkan latihannya"


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

            with patch("app.services.insiden_service.manager.broadcast", new=AsyncMock()) as siar:
                hasil = await acknowledge_alert(1, user=PERAWAT, db=sesi)

        assert hasil.acknowledged
        assert hasil.acknowledged_by == "Perawat Uji"
        pesan = siar.await_args.args[0]
        assert pesan.event == "alert_ack"
        assert pesan.data["id"] == 1 and pesan.data["acknowledged"] is True
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
        with patch("app.services.insiden_service.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(alert_id, user=PERAWAT, db=db_alert)
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
        with patch("app.services.insiden_service.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(lama, user=PERAWAT, db=db_alert)
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
        with patch("app.services.insiden_service.manager.broadcast", new=AsyncMock()):
            await acknowledge_alert(alert_id, user=PERAWAT, db=db_alert)
        assert fsm.state == FallState.POSSIBLE_FALL
    finally:
        registry.state_machines.pop("cam-03", None)


# ---- Keadaan saat kejadian dan status Telegram -------------

@pytest.mark.asyncio
async def test_ambang_mode_dan_foto_ikut_tersimpan(lingkungan):
    """Tanpa ambang dan mode saat kejadian, angka alarm palsu tidak bisa ditafsirkan."""
    from app.db.models import AlertSnapshot
    from app.services import inference_service

    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]
        foto = await s.get(AlertSnapshot, alert.id)

    assert alert.threshold_sec == pytest.approx(mod.get_settings().FALL_DURATION_THRESHOLD)
    assert alert.detection_mode == inference_service.mode_aktif()
    assert foto is not None and foto.jpeg == b"\xff\xd8potret-palsu\xff\xd9"


@pytest.mark.asyncio
async def test_status_dan_id_pesan_telegram_dicatat(lingkungan):
    """id pesan dipakai untuk menyunting pesan yang sama saat ada yang menekan tombol."""
    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]

    assert alert.telegram_status == "terkirim"
    assert alert.telegram_message_id == 501
    assert alert.telegram_foto is True
    assert lingkungan["telegram"][0]["mode_foto"] == "buram", "foto bawaan bukan foto utuh"


@pytest.mark.asyncio
async def test_status_gagal_tercatat(lingkungan):
    lingkungan["hasil_telegram"]["ok"] = False
    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]
    assert alert.telegram_status == "gagal"
    assert alert.telegram_message_id is None


@pytest.mark.asyncio
async def test_telegram_belum_diisi_tercatat_mati(lingkungan, monkeypatch):
    from app.services import notification_service as ns

    monkeypatch.setattr(ns, "dikonfigurasi", lambda: False)
    await _service().process_confirmed_fall("cam-01", 10.0)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]
    assert alert.telegram_status == "mati"
    assert lingkungan["telegram"] == []


@pytest.mark.asyncio
async def test_klaim_selama_pengiriman_menyunting_pesan_sesudahnya(lingkungan, monkeypatch):
    """Perawat menekan Saya ke sana di dashboard sebelum pesan Telegram selesai terkirim."""
    from app.db.models import AlertRecord
    from app.services import notification_service as ns

    kirim_asli = ns.kirim_alert

    async def kirim_lambat(alert, foto=None, mode_foto="buram"):
        async with lingkungan["factory"]() as s:
            baris = await s.get(AlertRecord, alert["id"])
            baris.claimed_by = "Siti"
            await s.commit()
        return await kirim_asli(alert, foto, mode_foto)

    monkeypatch.setattr(ns, "kirim_alert", kirim_lambat)
    await _service().process_confirmed_fall("cam-01", 10.0)

    assert len(lingkungan["disunting"]) == 1
    assert lingkungan["disunting"][0]["message_id"] == 501
    assert lingkungan["disunting"][0]["alert"]["claimed_by"] == "Siti"


@pytest.mark.asyncio
async def test_alarm_memulai_rekaman_klip(lingkungan):
    """Klip dimulai dari alert yang sudah tersimpan, dengan waktu alarm dan lama tergeletak."""
    sebelum = time.time()
    await _service().process_confirmed_fall("cam-01", 12.3)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]
    assert alert.klip_status == "merekam"
    [(alert_id, camera_id, waktu_alarm, lama)] = lingkungan["klip"]
    assert (alert_id, camera_id, lama) == (alert.id, "cam-01", 12.3)
    assert sebelum <= waktu_alarm <= time.time()
    pesan = next(m for m in lingkungan["ws"] if m.event == "alert")
    assert pesan.data["klip_status"] == "merekam", "dashboard tahu klipnya sedang direkam"


@pytest.mark.asyncio
async def test_tanpa_klip_bila_perekaman_dimatikan(lingkungan, monkeypatch):
    from app.services import klip
    monkeypatch.setattr(klip, "aktif", lambda: False)
    await _service().process_confirmed_fall("cam-01", 12.3)

    async with lingkungan["factory"]() as s:
        alert = (await AlertRepository(s).get_recent_alerts())[0]
    assert alert.klip_status is None
    assert lingkungan["klip"] == []

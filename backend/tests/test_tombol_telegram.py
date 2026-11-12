"""
test_tombol_telegram.py
=======================
Tombol di pesan alarm Telegram menjalankan langkah yang sama dengan dashboard.

Tidak ada panggilan ke Telegram sungguhan: jawaban dan penyuntingan pesan
diganti tiruan yang mencatat panggilannya.
"""

import asyncio
import types
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AlertRecord, Base
from app.services import notification_service as ns
from app.services import telegram_bot as bot

GRUP = "-100123"


@pytest_asyncio.fixture
async def tg(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            AlertRecord(camera_id="cam-01", camera_name="Kamar 101", message="uji", fall_duration=5.0,
                        telegram_message_id=501, telegram_foto=True),
            AlertRecord(camera_id="cam-02", camera_name="Kamar 102", message="uji", fall_duration=5.0,
                        simulated=True, telegram_message_id=502, telegram_foto=False),
        ])
        await s.commit()

    setelan = types.SimpleNamespace(TELEGRAM_BOT_TOKEN="x", TELEGRAM_CHAT_ID=GRUP, DASHBOARD_URL="")
    monkeypatch.setattr(bot, "get_settings", lambda: setelan)
    monkeypatch.setattr(bot, "get_session_factory", lambda: factory)
    alat = types.SimpleNamespace(
        jawab=AsyncMock(), ganti=AsyncMock(), sunting=AsyncMock(), siar=AsyncMock(), factory=factory)
    monkeypatch.setattr(ns, "jawab_callback", alat.jawab)
    monkeypatch.setattr(ns, "ganti_tombol", alat.ganti)
    monkeypatch.setattr(ns, "perbarui_pesan", alat.sunting)
    monkeypatch.setattr("app.services.insiden_service.manager.broadcast", alat.siar)
    yield alat
    await engine.dispose()


def _tekan(data, nama=("Siti", "Aminah"), chat=GRUP, message_id=501):
    return {
        "id": "cb-1",
        "data": data,
        "from": {"id": 9, "first_name": nama[0], "last_name": nama[1]},
        "message": {"message_id": message_id, "chat": {"id": int(chat)}},
    }


async def _alert(tg, alert_id=1) -> AlertRecord:
    async with tg.factory() as s:
        return await s.get(AlertRecord, alert_id)


def _jawaban(tg):
    """(teks, peringatan) dari jawaban terakhir ke penekan tombol."""
    args, kwargs = tg.jawab.call_args
    return args[1], kwargs.get("peringatan", False)


@pytest.mark.asyncio
async def test_saya_ke_sana_dari_telegram(tg):
    await bot.tangani_callback(_tekan("fd:klaim:1"))

    alert = await _alert(tg)
    assert alert.claimed_by == "Siti Aminah (Telegram)"
    assert alert.acknowledged is False
    teks, peringatan = _jawaban(tg)
    assert "menuju lokasi" in teks and not peringatan
    assert tg.siar.await_args.args[0].event == "alert_update", "dashboard ikut berubah"


@pytest.mark.asyncio
async def test_penekan_kedua_melihat_siapa_yang_sudah_menangani(tg):
    await bot.tangani_callback(_tekan("fd:klaim:1"))
    await bot.tangani_callback(_tekan("fd:klaim:1", nama=("Budi", None)))

    assert (await _alert(tg)).claimed_by == "Siti Aminah (Telegram)"
    teks, peringatan = _jawaban(tg)
    assert peringatan is True
    assert "Siti Aminah (Telegram)" in teks


@pytest.mark.asyncio
async def test_alarm_palsu_meminta_alasan_dulu(tg):
    await bot.tangani_callback(_tekan("fd:palsu:1"))

    assert (await _alert(tg)).acknowledged is False, "belum ada yang ditutup"
    assert tg.ganti.await_args.kwargs["tahap"] == "alasan"

    await bot.tangani_callback(_tekan("fd:alasan:1:bukan_orang"))
    alert = await _alert(tg)
    assert alert.acknowledged is True
    assert alert.acknowledged_by == "Siti Aminah (Telegram)"
    assert (alert.verdict, alert.verdict_reason) == ("palsu", "bukan_orang")


@pytest.mark.asyncio
async def test_alasan_yang_tidak_dikenal_tidak_menutup_alarm(tg):
    await bot.tangani_callback(_tekan("fd:alasan:1:ngawur"))
    assert (await _alert(tg)).acknowledged is False


@pytest.mark.asyncio
async def test_putusan_jatuh_sesudah_klaim(tg):
    await bot.tangani_callback(_tekan("fd:klaim:1"))
    await bot.tangani_callback(_tekan("fd:jatuh:1"))

    alert = await _alert(tg)
    assert alert.acknowledged is True and alert.verdict == "jatuh"
    assert tg.siar.await_args.args[0].event == "alert_ack"


@pytest.mark.asyncio
async def test_latihan_ditutup_tanpa_putusan(tg):
    await bot.tangani_callback(_tekan("fd:klaim:2", message_id=502))
    await bot.tangani_callback(_tekan("fd:tutup:2", message_id=502))

    alert = await _alert(tg, 2)
    assert alert.acknowledged is True and alert.verdict is None


@pytest.mark.asyncio
async def test_tombol_dari_grup_lain_diabaikan(tg):
    await bot.tangani_callback(_tekan("fd:klaim:1", chat="-999"))

    assert (await _alert(tg)).claimed_by is None
    assert "bukan dari grup" in _jawaban(tg)[0]


@pytest.mark.asyncio
async def test_tombol_pada_alarm_yang_sudah_selesai(tg):
    await bot.tangani_callback(_tekan("fd:jatuh:1"))
    await asyncio.sleep(0.05)       # biarkan penyuntingan latar dari langkah pertama selesai
    tg.sunting.reset_mock()

    await bot.tangani_callback(_tekan("fd:klaim:1", nama=("Budi", None)))
    teks, peringatan = _jawaban(tg)
    assert peringatan and "sudah ditangani" in teks
    assert tg.sunting.await_count == 1, "pesannya disamakan dengan keadaan terakhir"


@pytest.mark.asyncio
async def test_data_tombol_rusak(tg):
    for data in ("", "fd:klaim", "fd:klaim:abc", "lain:klaim:1", "fd:entah:1"):
        await bot.tangani_callback(_tekan(data))
        assert "tidak dikenal" in _jawaban(tg)[0]
    assert (await _alert(tg)).claimed_by is None


def test_nama_penekan():
    assert bot.nama_penekan({"first_name": "Siti", "last_name": "Aminah"}) == "Siti Aminah (Telegram)"
    assert bot.nama_penekan({"username": "siti_a"}) == "siti_a (Telegram)"
    assert bot.nama_penekan({}) == "Seseorang (Telegram)"


# ---- Balasan menjadi catatan -------------------------------------------------------

def _balas(teks, ke=501, chat=GRUP, message_id=900, nama=("Siti", "Aminah")):
    return {
        "message_id": message_id,
        "from": {"id": 9, "first_name": nama[0], "last_name": nama[1]},
        "chat": {"id": int(chat)},
        "text": teks,
        "reply_to_message": {"message_id": ke},
    }


@pytest.fixture
def balasan(tg, monkeypatch):
    tg.tandai = AsyncMock()
    tg.teks = AsyncMock(return_value=True)
    monkeypatch.setattr(ns, "tandai_diterima", tg.tandai)
    monkeypatch.setattr(ns, "kirim_teks", tg.teks)
    return tg


@pytest.mark.asyncio
async def test_balasan_ke_pesan_alarm_menjadi_catatan(balasan):
    await bot.tangani_balasan(_balas("  Sudah dibantu duduk, sadar  "))
    await bot.tangani_balasan(_balas("Keluarga sudah dikabari", message_id=901, nama=("Budi", "")))

    alert = await _alert(balasan)
    assert alert.caregiver_note == ("Siti Aminah (Telegram): Sudah dibantu duduk, sadar\n"
                                    "Budi (Telegram): Keluarga sudah dikabari")
    assert [c.args[0] for c in balasan.tandai.call_args_list] == [900, 901], "tiap balasan ditandai 👍"
    pesan = balasan.siar.await_args.args[0]
    assert pesan.event == "alert_update" and pesan.data["caregiver_note"].endswith("Keluarga sudah dikabari")


@pytest.mark.asyncio
@pytest.mark.parametrize("pesan", [
    _balas("dari grup lain", chat="-100999"),
    _balas("balasan ke pesan lain", ke=777),
    _balas("/start"),
    _balas("   "),
    {"message_id": 902, "chat": {"id": int(GRUP)}, "from": {"first_name": "Siti"}, "text": "bukan balasan"},
])
async def test_pesan_yang_bukan_catatan_diabaikan(balasan, pesan):
    await bot.tangani_balasan(pesan)
    assert (await _alert(balasan)).caregiver_note is None
    balasan.tandai.assert_not_awaited()
    balasan.teks.assert_not_awaited()


@pytest.mark.asyncio
async def test_catatan_terlalu_panjang_tidak_disimpan(balasan):
    await bot.tangani_balasan(_balas("x" * 600))
    assert (await _alert(balasan)).caregiver_note is None
    assert balasan.teks.await_args.kwargs["balas_ke"] == 900, "pengirim diberi tahu lewat balasan"
    balasan.tandai.assert_not_awaited()


@pytest.mark.asyncio
async def test_penerima_meminta_pesan_dan_tombol(monkeypatch):
    panggilan = {}

    async def panggil(metode, json_=None, **_):
        panggilan[metode] = json_
        return True, "", {"result": []}

    monkeypatch.setattr(ns, "_panggil", panggil)
    await bot._ambil_update(None)
    assert set(panggilan["getUpdates"]["allowed_updates"]) == {"callback_query", "message"}

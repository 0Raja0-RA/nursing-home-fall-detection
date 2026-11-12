"""
test_telegram.py
================
Uji jalur notifikasi Telegram memakai server tiruan.

Tidak ada pesan sungguhan yang dikirim, tidak ada token asli yang dipakai, dan
tidak butuh koneksi internet -- `api.telegram.org` digantikan server HTTP lokal
yang mencatat apa saja yang diterimanya.
"""

import json
import threading
import types
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import cv2
import numpy as np
import pytest

from app.services import notification_service as ns


# Token palsu untuk pengujian, dirakit saat program berjalan.
#
# Sengaja TIDAK ditulis sebagai satu string utuh. Pemindai rahasia GitHub
# mencocokkan pola <angka>:<rahasia> di dalam berkas sumber, dan literal
# berbentuk token tetap memicu peringatan "publicly leaked secret" walaupun
# isinya karangan -- peringatan yang harus ditutup manusia satu per satu.
# Merakitnya dari potongan membuat polanya hanya muncul saat dijalankan.
#
# Nomornya juga sengaja bukan id bot siapa pun.
_ID_PALSU = "999" + "0000001"
_RAHASIA_PALSU = "AAH" + "JanganDipakaiIniCumaUntukUji123"
TOKEN_PALSU = f"{_ID_PALSU}:{_RAHASIA_PALSU}"


class ServerTelegramTiruan:
    """Server HTTP yang berpura-pura jadi Bot API dan mencatat permintaan masuk."""

    def __init__(self, status_berurutan: list[int] | None = None, badan_gagal: str = "gagal"):
        # Status HTTP yang dikembalikan berurutan; yang terakhir dipakai berulang.
        self.status_berurutan = status_berurutan or [200]
        self.badan_gagal = badan_gagal
        self.permintaan: list[dict] = []
        self._srv: HTTPServer | None = None

    def mulai(self) -> str:
        luar = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                panjang = int(self.headers.get("Content-Length", 0))
                badan = self.rfile.read(panjang) if panjang else b""
                indeks = min(len(luar.permintaan), len(luar.status_berurutan) - 1)
                status = luar.status_berurutan[indeks]
                luar.permintaan.append({
                    "path": self.path,
                    "content_type": self.headers.get("Content-Type", ""),
                    "badan": badan,
                })
                if status == 200:
                    isi = {"ok": True, "result": {"message_id": 501}}
                else:
                    isi = {"ok": False, "error_code": status, "description": luar.badan_gagal}
                data = json.dumps(isi).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self._srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._srv.server_port}/bot{{token}}/{{metode}}"

    def hentikan(self):
        if self._srv:
            self._srv.shutdown()


def _setelan(token=TOKEN_PALSU, chat="-100123", dashboard=""):
    return types.SimpleNamespace(TELEGRAM_BOT_TOKEN=token, TELEGRAM_CHAT_ID=chat, DASHBOARD_URL=dashboard)


@pytest.fixture
def telegram(monkeypatch):
    """Arahkan notification_service ke server tiruan, dengan token & chat id palsu."""

    def pasang(status_berurutan=None, badan_gagal="gagal", dashboard=""):
        srv = ServerTelegramTiruan(status_berurutan, badan_gagal)
        monkeypatch.setattr(ns, "API_URL", srv.mulai())
        monkeypatch.setattr(ns, "get_settings", lambda: _setelan(dashboard=dashboard))
        # Jangan menunggu jeda retry yang sebenarnya saat uji.
        monkeypatch.setattr(ns, "JEDA_RETRY", (0.0, 0.0, 0.0))
        return srv

    srv_terpakai: list[ServerTelegramTiruan] = []

    def pabrik(status_berurutan=None, badan_gagal="gagal", dashboard=""):
        s = pasang(status_berurutan, badan_gagal, dashboard)
        srv_terpakai.append(s)
        return s

    yield pabrik
    for s in srv_terpakai:
        s.hentikan()


@pytest.fixture(autouse=True)
def tanpa_dashboard_url(monkeypatch):
    """Uji isi pesan tidak bergantung pada .env komputer yang menjalankannya."""
    monkeypatch.setattr(ns, "get_settings", lambda: _setelan())


def _alert(**ubah) -> dict:
    """Alert dalam bentuk JSON seperti jawaban API."""
    dasar = {
        "id": 7, "camera_id": "cam-01", "camera_name": "Kamar 01 - Jenderal Ilham",
        "fall_duration": 12.4, "simulated": False, "created_at": "2026-10-08T15:15:30",
        "acknowledged": False, "acknowledged_at": None, "acknowledged_by": None,
        "claimed_by": None, "claimed_at": None,
        "verdict": None, "verdict_reason": None,
    }
    dasar.update(ubah)
    return dasar


def _jam_lokal(iso: str) -> str:
    return datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).astimezone().strftime("%H.%M")


def _jpeg() -> bytes:
    gambar = np.zeros((120, 160, 3), dtype=np.uint8)
    cv2.rectangle(gambar, (40, 30), (120, 90), (255, 255, 255), -1)
    return cv2.imencode(".jpg", gambar)[1].tobytes()


def _data_tombol(tombol: dict) -> list[str]:
    return [t.get("callback_data") or t.get("url") for baris in tombol["inline_keyboard"] for t in baris]


# ---- Isi pesan ---------------------------------------------

def test_pesan_memuat_nama_ruang_durasi_dan_jam_setempat():
    teks = ns.susun_pesan(_alert())
    assert "Kamar 01 - Jenderal Ilham" in teks
    assert "Terbaca berbaring 12 detik" in teks
    assert _jam_lokal("2026-10-08T15:15:30") in teks
    assert "8 Okt 2026" in teks


def test_kata_yang_dipakai_kemungkinan_jatuh_bukan_terdeteksi():
    """Model membaca postur berbaring, bukan kejadian jatuh. Kata yang terlalu pasti
    membuat perawat berhenti percaya setelah beberapa alarm palsu."""
    teks = ns.susun_pesan(_alert())
    assert "Kemungkinan jatuh" in teks.splitlines()[0]
    assert "TERDETEKSI JATUH" not in teks
    assert "tidak bergerak" not in teks


def test_pesan_latihan_ditandai_di_baris_pertama():
    """Perawat membaca notifikasi dalam hitungan detik.

    Kalau penandanya ada di bawah, mereka sudah terlanjur bereaksi pada alarm
    yang bukan kejadian sungguhan.
    """
    baris_pertama = ns.susun_pesan(_alert(simulated=True)).splitlines()[0]
    assert "LATIHAN" in baris_pertama
    assert "bukan kejadian sungguhan" in baris_pertama
    assert "LATIHAN" not in ns.susun_pesan(_alert())


def test_nama_kamar_dengan_karakter_html_di_escape():
    """Nama kamar diisi bebas oleh perawat.

    Tanpa escape, nama seperti <Kamar> membuat Telegram menolak pesannya karena
    HTML-nya tidak valid -- jadi alertnya hilang sama sekali, bukan sekadar
    tampil aneh.
    """
    teks = ns.susun_pesan(_alert(camera_name="Kamar <01> & Ruang \"Tengah\"", claimed_by="<i>Siti</i>",
                                 claimed_at="2026-10-08T15:16:00"))
    assert "<01>" not in teks and "<i>" not in teks
    assert "&lt;01&gt;" in teks
    assert "&amp;" in teks


def test_status_pesan_mengikuti_penanganan():
    assert "Belum ada yang merespons" in ns.susun_pesan(_alert())

    diklaim = ns.susun_pesan(_alert(claimed_by="Siti", claimed_at="2026-10-08T15:16:00"))
    assert "Siti" in diklaim and "menuju lokasi" in diklaim
    assert _jam_lokal("2026-10-08T15:16:00") in diklaim

    palsu = ns.susun_pesan(_alert(acknowledged=True, acknowledged_by="Siti",
                                  acknowledged_at="2026-10-08T15:20:00",
                                  verdict="palsu", verdict_reason="berbaring_sengaja"))
    assert "Ditangani" in palsu and "Alarm palsu, berbaring sengaja" in palsu

    tanpa_putusan = ns.susun_pesan(_alert(acknowledged=True, acknowledged_by="Siti (Telegram)",
                                          acknowledged_at="2026-10-08T15:20:00"))
    assert "Putusan belum diisi" in tanpa_putusan


def test_nama_ruang_kosong_memakai_camera_id():
    assert "cam-01" in ns.susun_pesan(_alert(camera_name=None))


# ---- Tombol ------------------------------------------------

def test_tombol_mengikuti_keadaan_insiden():
    assert _data_tombol(ns.susun_tombol(_alert())) == ["fd:klaim:7", "fd:palsu:7"]
    assert _data_tombol(ns.susun_tombol(_alert(claimed_by="Siti"))) == [
        "fd:jatuh:7", "fd:palsu:7", "fd:ragu:7"]
    assert ns.susun_tombol(_alert(acknowledged=True)) == {"inline_keyboard": []}


def test_latihan_tidak_menawarkan_putusan():
    """Latihan tidak ikut dihitung sebagai alarm benar atau palsu."""
    assert _data_tombol(ns.susun_tombol(_alert(simulated=True))) == ["fd:klaim:7"]
    assert _data_tombol(ns.susun_tombol(_alert(simulated=True, claimed_by="Siti"))) == ["fd:tutup:7"]


def test_alasan_alarm_palsu_wajib_dipilih_lewat_tombol():
    from app.models.schemas import ALASAN_PALSU

    data = _data_tombol(ns.susun_tombol(_alert(), tahap="alasan"))
    assert data[:-1] == [f"fd:alasan:7:{k}" for k in ALASAN_PALSU]
    assert data[-1] == "fd:kembali:7"


def test_data_tombol_muat_dalam_batas_64_byte():
    """Telegram menolak callback_data yang lebih dari 64 byte."""
    besar = _alert(id=2_000_000_000)
    for tahap in (None, "alasan"):
        for d in _data_tombol(ns.susun_tombol(besar, tahap)):
            assert len(d.encode()) <= 64


def test_tombol_buka_dashboard_hanya_bila_alamatnya_diisi(monkeypatch):
    assert not any("url" in t for b in ns.susun_tombol(_alert())["inline_keyboard"] for t in b)
    monkeypatch.setattr(ns, "get_settings", lambda: _setelan(dashboard="http://192.168.1.5:5173/dashboard"))
    assert "http://192.168.1.5:5173/dashboard" in _data_tombol(ns.susun_tombol(_alert()))


# ---- Pengiriman --------------------------------------------

def _bagian_form(badan: bytes, nama: str) -> bytes:
    """Isi satu bagian multipart/form-data."""
    penanda = f'name="{nama}"'.encode()
    awal = badan.index(penanda)
    isi_awal = badan.index(b"\r\n\r\n", awal) + 4
    return badan[isi_awal:badan.index(b"\r\n--", isi_awal)]


@pytest.mark.asyncio
async def test_foto_bawaan_diburamkan_dan_dilindungi(telegram):
    srv = telegram()
    asli = _jpeg()
    hasil = await ns.kirim_alert(_alert(), foto=asli)

    assert hasil.berhasil and hasil.message_id == 501 and hasil.dengan_foto
    req = srv.permintaan[0]
    assert req["path"].endswith("/sendPhoto")
    terkirim = _bagian_form(req["badan"], "photo")
    assert terkirim != asli, "foto bawaan tidak boleh foto utuh"
    assert cv2.imdecode(np.frombuffer(terkirim, np.uint8), cv2.IMREAD_COLOR) is not None
    assert _bagian_form(req["badan"], "protect_content") == b"true"
    assert b"has_spoiler" not in req["badan"]
    tombol = json.loads(_bagian_form(req["badan"], "reply_markup"))
    assert _data_tombol(tombol) == ["fd:klaim:7", "fd:palsu:7"]


@pytest.mark.asyncio
async def test_foto_utuh_ditutup_spoiler(telegram):
    srv = telegram()
    asli = _jpeg()
    await ns.kirim_alert(_alert(), foto=asli, mode_foto="utuh")

    req = srv.permintaan[0]
    assert _bagian_form(req["badan"], "photo") == asli
    assert _bagian_form(req["badan"], "has_spoiler") == b"true"


@pytest.mark.asyncio
async def test_mode_tanpa_foto_mengirim_teks(telegram):
    srv = telegram()
    hasil = await ns.kirim_alert(_alert(), foto=_jpeg(), mode_foto="tanpa")

    assert hasil.berhasil and not hasil.dengan_foto
    req = srv.permintaan[0]
    assert req["path"].endswith("/sendMessage")
    badan = json.loads(req["badan"])
    assert badan["chat_id"] == "-100123"
    assert badan["protect_content"] is True
    assert "Kemungkinan jatuh" in badan["text"]


@pytest.mark.asyncio
async def test_foto_yang_tidak_bisa_diburamkan_tidak_dikirim_utuh(telegram):
    """Lebih baik tanpa gambar daripada membocorkan foto utuh."""
    srv = telegram()
    await ns.kirim_alert(_alert(), foto=b"\xff\xd8bukan-jpeg\xff\xd9")
    assert srv.permintaan[0]["path"].endswith("/sendMessage")


@pytest.mark.asyncio
async def test_gagal_sekali_lalu_berhasil(telegram):
    """Gangguan jaringan sesaat tidak boleh menghilangkan alert."""
    srv = telegram([500, 200])
    hasil = await ns.kirim_alert(_alert())

    assert hasil.berhasil is True
    assert len(srv.permintaan) == 2


@pytest.mark.asyncio
async def test_menyerah_setelah_tiga_percobaan(telegram):
    srv = telegram([500])
    hasil = await ns.kirim_alert(_alert())

    assert hasil.berhasil is False and hasil.message_id is None
    assert len(srv.permintaan) == len(ns.JEDA_RETRY)


@pytest.mark.asyncio
async def test_alamat_dashboard_yang_ditolak_tidak_menggagalkan_alarm(telegram):
    srv = telegram([400, 200], badan_gagal="Bad Request: BUTTON_URL_INVALID",
                   dashboard="http://localhost:5173/dashboard")
    hasil = await ns.kirim_alert(_alert())

    assert hasil.berhasil
    assert len(srv.permintaan) == 2
    kedua = json.loads(srv.permintaan[1]["badan"])
    assert "url" not in json.dumps(kedua["reply_markup"])


@pytest.mark.asyncio
async def test_tanpa_konfigurasi_tidak_mengirim_apa_pun(telegram, monkeypatch):
    srv = telegram()
    monkeypatch.setattr(ns, "get_settings", lambda: _setelan(token="", chat=""))
    hasil = await ns.kirim_alert(_alert())

    assert hasil.berhasil is False
    assert srv.permintaan == []


# ---- Menyunting pesan yang sama ----------------------------

@pytest.mark.asyncio
async def test_pesan_foto_disunting_lewat_caption(telegram):
    srv = telegram()
    ok = await ns.perbarui_pesan(_alert(claimed_by="Siti", claimed_at="2026-10-08T15:16:00"), 501, True)

    assert ok
    req = srv.permintaan[0]
    assert req["path"].endswith("/editMessageCaption")
    badan = json.loads(req["badan"])
    assert badan["message_id"] == 501
    assert "Siti" in badan["caption"]
    assert _data_tombol(badan["reply_markup"]) == ["fd:jatuh:7", "fd:palsu:7", "fd:ragu:7"]


@pytest.mark.asyncio
async def test_pesan_teks_disunting_lewat_text_dan_tombolnya_hilang_saat_selesai(telegram):
    srv = telegram()
    await ns.perbarui_pesan(_alert(acknowledged=True, acknowledged_by="Siti",
                                   acknowledged_at="2026-10-08T15:20:00", verdict="jatuh"), 501, False)

    req = srv.permintaan[0]
    assert req["path"].endswith("/editMessageText")
    badan = json.loads(req["badan"])
    assert "Jatuh sungguhan" in badan["text"]
    assert badan["reply_markup"] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_pesan_yang_sudah_sama_dianggap_berhasil(telegram):
    telegram([400], badan_gagal="Bad Request: message is not modified")
    assert await ns.perbarui_pesan(_alert(), 501, True) is True


# ---- Kerahasiaan token -------------------------------------

@pytest.mark.asyncio
async def test_token_tidak_pernah_masuk_log(telegram, caplog):
    """Seluruh percobaan kirim yang gagal tidak boleh meninggalkan token di log.

    Log backend sering ditempel ke chat atau issue saat minta bantuan. Uji ini
    pernah menangkap kebocoran sungguhan: bukan dari kode kita, melainkan dari
    httpx, yang mencatat URL permintaan secara utuh di level INFO -- dan URL Bot
    API memuat token di dalam path-nya.
    """
    import logging

    telegram([500], badan_gagal=f"gagal untuk bot{TOKEN_PALSU}")

    with caplog.at_level(logging.INFO):
        await ns.kirim_alert(_alert())
        await ns.perbarui_pesan(_alert(), 501, True)

    seluruh_log = "\n".join(r.getMessage() for r in caplog.records)
    assert TOKEN_PALSU not in seluruh_log, "token bocor ke log"
    assert _RAHASIA_PALSU not in seluruh_log


def test_penyaring_log_menyensor_catatan_dari_library_lain():
    """Penyaring dipasang di tingkat handler supaya mencakup library mana pun.

    Meredam logger httpx saja tidak cukup sebagai pertahanan: library lain bisa
    saja mencatat URL yang sama, sekarang atau nanti.
    """
    import logging

    from app.core.logging import SensorRahasia

    rahasia = TOKEN_PALSU
    record = logging.LogRecord(
        name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
        msg=f"HTTP Request: POST https://api.telegram.org/bot{rahasia}/sendPhoto",
        args=(), exc_info=None,
    )

    SensorRahasia().filter(record)

    assert rahasia not in record.getMessage()
    assert "<TOKEN-DISENSOR>" in record.getMessage()
    assert "api.telegram.org" in record.getMessage()   # sisanya tetap berguna


def test_penyensor_mengenali_bentuk_token():
    teks = f"gagal memanggil https://api.telegram.org/bot{TOKEN_PALSU}/sendPhoto"
    hasil = ns._sensor(teks)
    assert TOKEN_PALSU not in hasil
    assert "<TOKEN>" in hasil
    assert "api.telegram.org" in hasil   # sisanya tetap berguna untuk diagnosa

"""
test_telegram.py
================
Uji jalur notifikasi Telegram memakai server tiruan.

Tidak ada pesan sungguhan yang dikirim, tidak ada token asli yang dipakai, dan
tidak butuh koneksi internet -- `api.telegram.org` digantikan server HTTP lokal
yang mencatat apa saja yang diterimanya.
"""

import asyncio
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

    def __init__(self, status_berurutan: list[int] | None = None):
        # Status HTTP yang dikembalikan berurutan; yang terakhir dipakai berulang.
        self.status_berurutan = status_berurutan or [200]
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
                isi = json.dumps({"ok": status == 200}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(isi)))
                self.end_headers()
                self.wfile.write(isi)

            def log_message(self, *a):
                pass

        self._srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._srv.server_port}/bot{{token}}/{{metode}}"

    def hentikan(self):
        if self._srv:
            self._srv.shutdown()


@pytest.fixture
def telegram(monkeypatch):
    """Arahkan notification_service ke server tiruan, dengan token & chat id palsu."""
    import types

    def pasang(status_berurutan=None):
        srv = ServerTelegramTiruan(status_berurutan)
        monkeypatch.setattr(ns, "API_URL", srv.mulai())
        monkeypatch.setattr(ns, "get_settings", lambda: types.SimpleNamespace(
            TELEGRAM_BOT_TOKEN=TOKEN_PALSU, TELEGRAM_CHAT_ID="-100123",
        ))
        # Jangan menunggu jeda retry yang sebenarnya saat uji.
        monkeypatch.setattr(ns, "JEDA_RETRY", (0.0, 0.0, 0.0))
        return srv

    srv_terpakai: list[ServerTelegramTiruan] = []

    def pabrik(status_berurutan=None):
        s = pasang(status_berurutan)
        srv_terpakai.append(s)
        return s

    yield pabrik
    for s in srv_terpakai:
        s.hentikan()


# ---- Isi pesan ---------------------------------------------

def test_pesan_memuat_nama_kamar_durasi_dan_waktu():
    from datetime import datetime

    teks = ns.susun_pesan("Kamar 01 - Jenderal Ilham", 12.4, datetime(2026, 10, 8, 22, 15, 30))
    assert "Kamar 01 - Jenderal Ilham" in teks
    assert "12.4" in teks
    assert "22:15:30" in teks


def test_nama_kamar_dengan_karakter_html_di_escape():
    """Nama kamar diisi bebas oleh perawat.

    Tanpa escape, nama seperti <Kamar> membuat Telegram menolak pesannya karena
    HTML-nya tidak valid -- jadi alertnya hilang sama sekali, bukan sekadar
    tampil aneh.
    """
    teks = ns.susun_pesan("Kamar <01> & Ruang \"Tengah\"", 3.0)
    assert "<Kamar>" not in teks
    assert "&lt;01&gt;" in teks
    assert "&amp;" in teks


# ---- Pengiriman --------------------------------------------

@pytest.mark.asyncio
async def test_kirim_dengan_foto_memakai_sendphoto(telegram):
    srv = telegram()
    ok = await ns.send_telegram_alert("Kamar 02", 11.0, foto=b"\xff\xd8jpeg-palsu\xff\xd9")

    assert ok is True
    assert len(srv.permintaan) == 1
    req = srv.permintaan[0]
    assert req["path"].endswith("/sendPhoto")
    assert "multipart/form-data" in req["content_type"]
    assert b"jpeg-palsu" in req["badan"]
    assert b"Kamar 02" in req["badan"]


@pytest.mark.asyncio
async def test_tanpa_foto_jatuh_ke_sendmessage(telegram):
    srv = telegram()
    ok = await ns.send_telegram_alert("Kamar 03", 10.0, foto=None)

    assert ok is True
    assert srv.permintaan[0]["path"].endswith("/sendMessage")
    assert json.loads(srv.permintaan[0]["badan"])["chat_id"] == "-100123"


@pytest.mark.asyncio
async def test_gagal_sekali_lalu_berhasil(telegram):
    """Gangguan jaringan sesaat tidak boleh menghilangkan alert."""
    srv = telegram([500, 200])
    ok = await ns.send_telegram_alert("Kamar 04", 10.0)

    assert ok is True
    assert len(srv.permintaan) == 2


@pytest.mark.asyncio
async def test_menyerah_setelah_tiga_percobaan(telegram):
    srv = telegram([500])
    ok = await ns.send_telegram_alert("Kamar 05", 10.0)

    assert ok is False
    assert len(srv.permintaan) == len(ns.JEDA_RETRY)


@pytest.mark.asyncio
async def test_tanpa_konfigurasi_tidak_mengirim_apa_pun(telegram, monkeypatch):
    import types

    srv = telegram()
    monkeypatch.setattr(ns, "get_settings", lambda: types.SimpleNamespace(
        TELEGRAM_BOT_TOKEN="", TELEGRAM_CHAT_ID="",
    ))
    ok = await ns.send_telegram_alert("Kamar 06", 10.0)

    assert ok is False
    assert srv.permintaan == []


# ---- Kerahasiaan token -------------------------------------

@pytest.mark.asyncio
async def test_token_tidak_pernah_masuk_log(telegram, caplog, monkeypatch):
    """Seluruh percobaan kirim yang gagal tidak boleh meninggalkan token di log.

    Log backend sering ditempel ke chat atau issue saat minta bantuan. Uji ini
    pernah menangkap kebocoran sungguhan: bukan dari kode kita, melainkan dari
    httpx, yang mencatat URL permintaan secara utuh di level INFO -- dan URL Bot
    API memuat token di dalam path-nya.
    """
    import logging
    import types

    rahasia = TOKEN_PALSU
    telegram([500])
    monkeypatch.setattr(ns, "get_settings", lambda: types.SimpleNamespace(
        TELEGRAM_BOT_TOKEN=rahasia, TELEGRAM_CHAT_ID="-100123",
    ))

    with caplog.at_level(logging.INFO):
        await ns.send_telegram_alert("Kamar 07", 10.0)

    seluruh_log = "\n".join(r.getMessage() for r in caplog.records)
    assert rahasia not in seluruh_log, "token bocor ke log"
    assert "AAHrahasiaSekali" not in seluruh_log


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

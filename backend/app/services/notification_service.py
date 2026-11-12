"""
notification_service.py
=======================
Mengirim dan menyunting pesan alarm di grup Telegram lewat Bot API.

Setup:
    1. Buka @BotFather di Telegram, buat bot baru, simpan tokennya di
       TELEGRAM_BOT_TOKEN pada backend/.env.
    2. Ajak bot ke grup perawat, lalu kirim /start@NamaBot_bot di grup itu.
       Bot Telegram tidak bisa mengirim pesan ke pihak yang belum menyapanya.
    3. Ambil chat_id-nya:  python tools/get_chat_id.py

Yang sengaja diperhatikan di sini:

- **Satu insiden, satu pesan.** Pesan alarm membawa tombol `Saya ke sana` dan
  `Alarm palsu`. Saat seseorang menekan tombol, di Telegram atau di dashboard,
  pesan yang sama disunting supaya seluruh grup melihat siapa yang sudah menuju
  lokasi. Tanpa ini perawat saling menunggu, atau sama-sama berangkat.
- **Kata yang jujur.** Model membaca postur berbaring, bukan kejadian jatuh, jadi
  pesannya "Kemungkinan jatuh" dan "terbaca berbaring N detik".
- **Foto bawaan diburamkan.** Foto penghuni yang tergeletak adalah data kesehatan,
  dan pesan grup mudah diteruskan. Pilihannya diatur dari halaman Pengaturan:
  buram, utuh tetapi tertutup sampai diketuk, atau tanpa foto. Semua pesan memakai
  protect_content supaya tidak bisa diteruskan atau disimpan.
- **Token tidak pernah masuk log.** URL Bot API memuat token, jadi pesan
  kesalahan dari httpx disensor dulu sebelum dicatat.
"""

import asyncio
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import get_settings
from app.models.schemas import ALASAN_PALSU, LABEL_PUTUSAN

from app.core.logging import get_logger
log = get_logger("app.services.notification_service")

API_URL = "https://api.telegram.org/bot{token}/{metode}"

# Token berbentuk <angka>:<rahasia>; dipakai untuk menyensornya dari pesan error.
_POLA_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_\-]{20,}")

# Jeda antar percobaan ulang, dalam detik. Percobaan pertama langsung.
JEDA_RETRY = (0.0, 5.0, 20.0)

_BULAN = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


@dataclass
class HasilKirim:
    """Hasil mengirim pesan alarm."""
    berhasil: bool
    message_id: Optional[int] = None
    dengan_foto: bool = False


def _sensor(teks: str) -> str:
    """Hilangkan token dari teks apa pun sebelum dicatat ke log."""
    return _POLA_TOKEN.sub("<TOKEN>", teks)


def dikonfigurasi() -> bool:
    s = get_settings()
    return bool(s.TELEGRAM_BOT_TOKEN and s.TELEGRAM_CHAT_ID)


def _lokal(waktu) -> Optional[datetime]:
    """Waktu UTC tanpa zona (datetime atau teks ISO) menjadi jam setempat."""
    if waktu is None:
        return None
    if isinstance(waktu, str):
        try:
            waktu = datetime.fromisoformat(waktu.replace("Z", ""))
        except ValueError:
            return None
    return waktu.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def _jam(waktu) -> str:
    w = _lokal(waktu)
    return w.strftime("%H.%M") if w else ""


def _tanggal_jam(waktu) -> str:
    w = _lokal(waktu)
    return f"{w:%H.%M}, {w.day} {_BULAN[w.month - 1]} {w.year}" if w else ""


# ---- Isi pesan ---------------------------------------------------------------

def _baris_status(alert: dict) -> str:
    """Satu baris yang berubah sepanjang hidup insiden."""
    e = html.escape
    if alert.get("acknowledged"):
        oleh = alert.get("acknowledged_by")
        teks = f"✅ Ditangani{f' <b>{e(oleh)}</b>' if oleh else ''} ({_jam(alert.get('acknowledged_at'))})."
        if alert.get("simulated"):
            return teks
        putusan = alert.get("verdict")
        if putusan:
            label = LABEL_PUTUSAN.get(putusan, putusan)
            alasan = ALASAN_PALSU.get(alert.get("verdict_reason") or "")
            teks += f"\nPutusan: {e(label)}" + (f", {e(alasan.lower())}" if alasan else "") + "."
        else:
            teks += "\nPutusan belum diisi. Lengkapi di Riwayat Insiden."
        return teks + "\nBalas pesan ini untuk menambah catatan."
    if alert.get("claimed_by"):
        return f"🟠 <b>{e(alert['claimed_by'])}</b> menuju lokasi ({_jam(alert.get('claimed_at'))})."
    return "Belum ada yang merespons. Tekan <b>Saya ke sana</b> bila Anda menuju lokasi."


def susun_pesan(alert: dict) -> str:
    """Isi pesan untuk keadaan alert saat ini, dalam HTML.

    Memakai HTML, bukan Markdown, karena nama kamar bebas diisi perawat dan
    karakter seperti _ atau * akan membuat Markdown gagal diurai Telegram --
    pesannya ditolak, bukan sekadar tampil aneh.

    Penanda latihan diletakkan paling atas. Perawat membaca notifikasi dalam
    hitungan detik; kalau penandanya di bawah, mereka sudah terlanjur bereaksi.
    """
    nama = html.escape(alert.get("camera_name") or alert.get("camera_id") or "?")
    durasi = float(alert.get("fall_duration") or 0)
    if alert.get("simulated"):
        kepala = f"🧪 <b>LATIHAN, bukan kejadian sungguhan</b>\n<b>{nama}</b>"
    else:
        kepala = f"🚨 <b>Kemungkinan jatuh</b>\n<b>{nama}</b>"
    return (
        f"{kepala}\n"
        f"Terbaca berbaring {durasi:.0f} detik · {_tanggal_jam(alert.get('created_at'))}\n\n"
        f"{_baris_status(alert)}"
    )


def susun_tombol(alert: dict, tahap: Optional[str] = None) -> dict:
    """Tombol untuk keadaan alert saat ini.

    tahap="alasan" menampilkan pilihan alasan alarm palsu. Alasan wajib dipilih,
    sama seperti di dashboard, supaya angka alarm palsu bisa dipakai.
    """
    aid = alert["id"]
    if alert.get("acknowledged"):
        return {"inline_keyboard": []}

    tombol = lambda teks, aksi: {"text": teks, "callback_data": f"fd:{aksi}:{aid}"}  # noqa: E731
    if tahap == "alasan":
        pilihan = [{"text": label, "callback_data": f"fd:alasan:{aid}:{kode}"}
                   for kode, label in ALASAN_PALSU.items()]
        baris = [pilihan[i:i + 2] for i in range(0, len(pilihan), 2)]
        baris.append([tombol("« Kembali", "kembali")])
        return {"inline_keyboard": baris}

    latihan = bool(alert.get("simulated"))
    if alert.get("claimed_by"):
        if latihan:
            baris = [[tombol("Tandai ditangani", "tutup")]]
        else:
            baris = [[tombol("Jatuh sungguhan", "jatuh"), tombol("Alarm palsu", "palsu")],
                     [tombol("Belum yakin", "ragu")]]
    else:
        baris = [[tombol("Saya ke sana", "klaim")]]
        if not latihan:
            baris[0].append(tombol("Alarm palsu", "palsu"))

    url = get_settings().DASHBOARD_URL
    if url:
        baris.append([{"text": "Buka dashboard", "url": url}])
    return {"inline_keyboard": baris}


def _tanpa_url(tombol: Optional[dict]) -> Optional[dict]:
    if not tombol:
        return tombol
    return {"inline_keyboard": [b for b in tombol["inline_keyboard"] if not any("url" in t for t in b)]}


def _ada_url(tombol: Optional[dict]) -> bool:
    return bool(tombol) and any("url" in t for b in tombol["inline_keyboard"] for t in b)


def buramkan(jpeg: bytes) -> Optional[bytes]:
    """Buramkan foto sampai wajah tidak dikenali, tetapi posisi tubuh masih terbaca.

    None kalau gambarnya tidak bisa dibaca. Pemanggil lalu mengirim teks saja,
    bukan foto utuh: lebih baik tanpa gambar daripada membocorkannya.
    """
    import cv2
    import numpy as np

    gambar = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    if gambar is None:
        return None
    h, w = gambar.shape[:2]
    k = max(15, (min(h, w) // 10) | 1)      # ukuran kernel ganjil, sebanding dengan gambar
    ok, buf = cv2.imencode(".jpg", cv2.GaussianBlur(gambar, (k, k), 0), [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else None


# ---- Panggilan Bot API -----------------------------------------------------------

async def _panggil(metode: str, *, json_: Optional[dict] = None, data: Optional[dict] = None,
                   files: Optional[dict] = None, timeout: float = 15.0) -> tuple[bool, str, dict]:
    """Satu panggilan Bot API. Returns: (berhasil, alasan kalau gagal, isi jawaban)."""
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(API_URL.format(token=s.TELEGRAM_BOT_TOKEN, metode=metode),
                                  json=json_, data=data, files=files)
        try:
            isi = r.json()
        except ValueError:
            isi = {}
        if r.status_code == 200:
            return True, "", isi if isinstance(isi, dict) else {}
        return False, f"HTTP {r.status_code}: {_sensor(r.text)[:200]}", isi if isinstance(isi, dict) else {}
    except httpx.HTTPError as e:
        return False, _sensor(str(e))[:200] or type(e).__name__, {}


async def _kirim_sekali(teks: str, foto: Optional[bytes], tombol: Optional[dict],
                        spoiler: bool = False, balas_ke: Optional[int] = None) -> tuple[bool, str, Optional[int]]:
    """Satu kali percobaan kirim. Pakai sendPhoto kalau ada gambarnya."""
    chat_id = get_settings().TELEGRAM_CHAT_ID
    if foto:
        data = {"chat_id": chat_id, "caption": teks, "parse_mode": "HTML", "protect_content": "true"}
        if spoiler:
            data["has_spoiler"] = "true"
        if tombol:
            data["reply_markup"] = json.dumps(tombol)
        ok, alasan, isi = await _panggil("sendPhoto", data=data,
                                         files={"photo": ("kejadian.jpg", foto, "image/jpeg")})
    else:
        payload = {"chat_id": chat_id, "text": teks, "parse_mode": "HTML", "protect_content": True}
        if tombol:
            payload["reply_markup"] = tombol
        if balas_ke:
            # Tetap terkirim walau pesan asalnya sudah dihapus dari grup.
            payload["reply_parameters"] = {"message_id": balas_ke, "allow_sending_without_reply": True}
        ok, alasan, isi = await _panggil("sendMessage", json_=payload)
    message_id = (isi.get("result") or {}).get("message_id") if ok else None
    return ok, alasan, message_id


async def _kirim_dengan_ulang(teks: str, foto: Optional[bytes] = None, tombol: Optional[dict] = None,
                              spoiler: bool = False, label: str = "pesan",
                              balas_ke: Optional[int] = None) -> HasilKirim:
    """Kirim dengan percobaan ulang bila gagal.

    Gangguan jaringan sesaat itu lumrah, apalagi kalau laptop sedang berbagi
    koneksi lewat hotspot. Tiga percobaan dengan jeda menutup kasus itu tanpa
    menahan apa pun: alert sudah tersimpan dan sudah disiarkan ke dashboard.
    """
    if not dikonfigurasi():
        log.info("⚠️  Telegram belum dikonfigurasi (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID kosong)")
        return HasilKirim(False)

    percobaan = 0
    while percobaan < len(JEDA_RETRY):
        jeda = JEDA_RETRY[percobaan]
        percobaan += 1
        if jeda:
            await asyncio.sleep(jeda)
        ok, alasan, message_id = await _kirim_sekali(teks, foto, tombol, spoiler, balas_ke)
        if ok:
            log.info(f"✅ Telegram terkirim ({'foto' if foto else 'teks'}) untuk {label}"
                     + (f" pada percobaan ke-{percobaan}" if percobaan > 1 else ""))
            return HasilKirim(True, message_id, bool(foto))
        # Alamat dashboard yang ditolak Telegram tidak boleh menggagalkan alarm:
        # buang tombol tautannya dan coba lagi saat itu juga.
        if alasan.startswith("HTTP 400") and _ada_url(tombol):
            log.info("⚠️  Tombol Buka dashboard ditolak Telegram; dikirim tanpa tombol itu. "
                     "Periksa DASHBOARD_URL.")
            tombol = _tanpa_url(tombol)
            percobaan -= 1
            continue
        log.info(f"⚠️  Telegram gagal (percobaan {percobaan}/{len(JEDA_RETRY)}): {alasan}")

    log.info(f"❌ Telegram menyerah setelah {len(JEDA_RETRY)} percobaan untuk {label}")
    return HasilKirim(False)


async def kirim_alert(alert: dict, foto: Optional[bytes] = None, mode_foto: str = "buram") -> HasilKirim:
    """Kirim pesan alarm untuk satu alert, dengan tombol dan foto sesuai pengaturan."""
    gambar, spoiler = None, False
    if foto and mode_foto != "tanpa":
        if mode_foto == "utuh":
            gambar, spoiler = foto, True
        else:
            gambar = await asyncio.to_thread(buramkan, foto)
            if gambar is None:
                log.info("⚠️  Foto kejadian tidak bisa diburamkan; dikirim tanpa foto.")
    return await _kirim_dengan_ulang(
        susun_pesan(alert), gambar, susun_tombol(alert), spoiler,
        label=alert.get("camera_name") or alert.get("camera_id") or "alert",
    )


async def perbarui_pesan(alert: dict, message_id: int, dengan_foto: bool,
                         tahap: Optional[str] = None) -> bool:
    """Sunting pesan alarm supaya statusnya sama dengan dashboard.

    Gagal menyunting tidak menggagalkan apa pun: statusnya tetap benar di dashboard.
    """
    if not dikonfigurasi() or not message_id:
        return False
    teks = susun_pesan(alert)
    payload = {
        "chat_id": get_settings().TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "parse_mode": "HTML",
        "reply_markup": susun_tombol(alert, tahap),
        ("caption" if dengan_foto else "text"): teks,
    }
    metode = "editMessageCaption" if dengan_foto else "editMessageText"
    ok, alasan, _ = await _panggil(metode, json_=payload)
    if not ok and "not modified" in alasan:
        return True
    if not ok and _ada_url(payload["reply_markup"]) and alasan.startswith("HTTP 400"):
        payload["reply_markup"] = _tanpa_url(payload["reply_markup"])
        ok, alasan, _ = await _panggil(metode, json_=payload)
    if not ok:
        log.info(f"⚠️  Gagal menyunting pesan Telegram alert #{alert.get('id')}: {alasan}")
    return ok


async def ganti_tombol(alert: dict, message_id: int, tahap: Optional[str] = None) -> bool:
    """Ganti tombolnya saja, mis. memunculkan pilihan alasan alarm palsu."""
    if not dikonfigurasi() or not message_id:
        return False
    ok, alasan, _ = await _panggil("editMessageReplyMarkup", json_={
        "chat_id": get_settings().TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "reply_markup": susun_tombol(alert, tahap),
    })
    if not ok and "not modified" not in alasan:
        log.info(f"⚠️  Gagal mengganti tombol Telegram alert #{alert.get('id')}: {alasan}")
    return ok


async def jawab_callback(callback_id: str, teks: str, peringatan: bool = False) -> None:
    """Jawaban kecil di layar penekan tombol. peringatan=True memunculkan jendela yang harus ditutup."""
    await _panggil("answerCallbackQuery", json_={
        "callback_query_id": callback_id, "text": teks[:200], "show_alert": peringatan,
    })


async def tandai_diterima(message_id: int) -> None:
    """Reaksi 👍 pada balasan yang sudah tersimpan sebagai catatan. Bila grup tidak
    mengizinkan reaksi itu, kirim balasan teks pendek sebagai gantinya."""
    ok, _, _ = await _panggil("setMessageReaction", json_={
        "chat_id": get_settings().TELEGRAM_CHAT_ID, "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": "👍"}],
    })
    if not ok:
        await kirim_teks("Catatan tersimpan di Riwayat Insiden.", label="tanda catatan", balas_ke=message_id)


async def kirim_teks(teks: str, label: str = "pesan", balas_ke: Optional[int] = None) -> bool:
    """Pesan teks biasa ke grup, dengan percobaan ulang. Dipakai untuk kabar kamera dan
    pengingat eskalasi (`balas_ke`: id pesan alarm yang dibalas)."""
    return (await _kirim_dengan_ulang(teks, label=label, balas_ke=balas_ke)).berhasil


async def send_test_notification() -> bool:
    """Kirim notifikasi uji untuk memverifikasi konfigurasi."""
    return await kirim_teks(
        "🔔 <b>Uji koneksi</b>\n\n"
        "FallDetect berhasil terhubung ke grup ini.\n"
        "Pesan ini dikirim manual dari halaman Pengaturan, bukan karena ada yang jatuh.",
        label="uji koneksi",
    )

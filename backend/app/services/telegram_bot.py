"""
telegram_bot.py
===============
Menerima tekanan tombol di pesan alarm Telegram.

Backend berjalan di laptop tanpa alamat publik, jadi webhook tidak bisa dipakai.
Gantinya long polling: backend bertanya ke Telegram "ada tombol yang ditekan?",
dan Telegram menahan pertanyaan itu sampai ada jawaban atau 25 detik lewat.

Setiap tombol menjalankan langkah yang sama dengan tombol di dashboard
(insiden_service), jadi aturannya satu: klaim kedua oleh orang lain ditolak,
alarm palsu wajib beralasan, dan semua dashboard ikut berubah.

Balasan (reply) ke pesan alarm di grup menjadi catatan insiden atas nama
pengirimnya, ditandai 👍 bila tersimpan. Bot dalam privacy mode tetap menerima
balasan ke pesannya sendiri, jadi grup tidak perlu menjadikan bot admin.

Hanya tombol dan balasan dari grup yang ada di TELEGRAM_CHAT_ID yang dilayani. Nama
pengirim diambil dari profil Telegram-nya, dengan akhiran "(Telegram)" supaya riwayat
membedakannya dari akun dashboard.

Satu token bot hanya boleh punya satu penerima. Kalau backend lain (mis. laptop
teman) memakai token yang sama, Telegram menjawab 409 dan penerima ini menunggu
lalu mencoba lagi, tanpa mengganggu pengiriman alarm.
"""

import asyncio
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.database import get_session_factory
from app.models.schemas import ALASAN_PALSU, Putusan
from app.services import insiden_service as insiden
from app.services import notification_service as ns

log = get_logger("app.services.telegram_bot")

_PUTUSAN_TOMBOL = {
    "jatuh": Putusan.JATUH,
    "ragu": Putusan.BELUM_YAKIN,
    "tutup": None,          # latihan: ditutup tanpa putusan
}


def nama_penekan(pengirim: dict) -> str:
    nama = " ".join(filter(None, [pengirim.get("first_name"), pengirim.get("last_name")])).strip()
    nama = nama or pengirim.get("username") or "Seseorang"
    return f"{nama[:40]} (Telegram)"


async def tangani_callback(cq: dict) -> None:
    """Jalankan satu tekanan tombol, lalu beri jawaban kecil ke penekannya."""
    cid = cq.get("id", "")
    pesan = cq.get("message") or {}
    chat_id = str((pesan.get("chat") or {}).get("id", ""))
    if chat_id != str(get_settings().TELEGRAM_CHAT_ID):
        await ns.jawab_callback(cid, "Tombol ini bukan dari grup FallDetect.")
        return

    bagian = (cq.get("data") or "").split(":")
    if len(bagian) < 3 or bagian[0] != "fd":
        await ns.jawab_callback(cid, "Tombol tidak dikenal.")
        return
    aksi = bagian[1]
    try:
        alert_id = int(bagian[2])
    except ValueError:
        await ns.jawab_callback(cid, "Tombol tidak dikenal.")
        return
    nama = nama_penekan(cq.get("from") or {})
    message_id = pesan.get("message_id")

    async with get_session_factory()() as db:
        try:
            alert = await insiden.ambil(db, alert_id)
        except insiden.InsidenTidakAda:
            await ns.jawab_callback(cid, "Alarm ini tidak ada lagi di sistem.", peringatan=True)
            return

        if alert.acknowledged and aksi != "kembali":
            await ns.jawab_callback(
                cid, f"Alarm ini sudah ditangani {alert.acknowledged_by or ''}".rstrip() + ".", peringatan=True)
            await ns.perbarui_pesan(insiden.alert_ke_dict(alert), message_id, bool(alert.telegram_foto))
            return

        try:
            if aksi == "klaim":
                await insiden.klaim(db, alert_id, nama)
                await ns.jawab_callback(cid, "Tercatat: Anda menuju lokasi. Grup dan dashboard sudah tahu.")
            elif aksi == "palsu":
                # Alasan wajib: tampilkan pilihannya dulu, belum menutup apa pun.
                await ns.ganti_tombol(insiden.alert_ke_dict(alert), message_id, tahap="alasan")
                await ns.jawab_callback(cid, "Pilih alasannya.")
            elif aksi == "kembali":
                await ns.ganti_tombol(insiden.alert_ke_dict(alert), message_id)
                await ns.jawab_callback(cid, "")
            elif aksi == "alasan" and len(bagian) == 4 and bagian[3] in ALASAN_PALSU:
                await insiden.tutup(db, alert_id, nama, verdict=Putusan.PALSU, alasan=bagian[3])
                await ns.jawab_callback(cid, "Ditutup sebagai alarm palsu. Terima kasih.")
            elif aksi in _PUTUSAN_TOMBOL:
                await insiden.tutup(db, alert_id, nama, verdict=_PUTUSAN_TOMBOL[aksi])
                await ns.jawab_callback(cid, "Alarm ditutup. Catatan bisa ditambah di Riwayat Insiden.")
            else:
                await ns.jawab_callback(cid, "Tombol tidak dikenal.")
        except insiden.KonflikInsiden as e:
            # Penekan kedua melihat siapa yang sudah menangani, dalam jendela yang harus ditutup.
            await ns.jawab_callback(cid, str(e), peringatan=True)


async def tangani_balasan(pesan: dict) -> None:
    """Balasan ke pesan alarm menjadi satu baris catatan insiden: "Nama (Telegram): isi"."""
    chat_id = str((pesan.get("chat") or {}).get("id", ""))
    teks = (pesan.get("text") or pesan.get("caption") or "").strip()
    induk = (pesan.get("reply_to_message") or {}).get("message_id")
    if chat_id != str(get_settings().TELEGRAM_CHAT_ID) or not teks or induk is None or teks.startswith("/"):
        return
    nama = nama_penekan(pesan.get("from") or {})
    async with get_session_factory()() as db:
        alert = await insiden.alert_dari_pesan(db, induk)
        if alert is None:
            return                  # balasan ke pesan lain, mis. kabar kamera
        try:
            await insiden.tambah_catatan(db, alert, f"{nama}: {teks}")
        except insiden.CatatanPenuh:
            await ns.kirim_teks("Catatan tidak tersimpan karena terlalu panjang. Ringkas lalu kirim lagi, "
                                "atau tulis di Riwayat Insiden.", label="catatan penuh",
                                balas_ke=pesan.get("message_id"))
            return
    log.info(f"[{alert.camera_id}] catatan dari Telegram untuk alert #{alert.id} oleh {nama}")
    await ns.tandai_diterima(pesan.get("message_id"))


async def _ambil_update(offset: Optional[int]) -> tuple[bool, str, list]:
    payload = {"timeout": 25, "allowed_updates": ["callback_query", "message"]}
    if offset is not None:
        payload["offset"] = offset
    ok, alasan, isi = await ns._panggil("getUpdates", json_=payload, timeout=40.0)
    return ok, alasan, isi.get("result") or []


async def jalankan_penerima() -> None:
    """Loop long polling. Berhenti hanya saat task-nya dibatalkan (backend dimatikan)."""
    if not ns.dikonfigurasi():
        log.info("Penerima tombol Telegram tidak dijalankan: Telegram belum dikonfigurasi.")
        return
    log.info("📨 Penerima tombol dan balasan Telegram berjalan")
    offset: Optional[int] = None
    sudah_lapor_bentrok = False
    while True:
        try:
            ok, alasan, update = await _ambil_update(offset)
            if not ok:
                if alasan.startswith("HTTP 409"):
                    if not sudah_lapor_bentrok:
                        log.info("⚠️  Token bot ini sedang dipakai backend lain; tombol Telegram "
                                 "dilayani backend itu. Dicoba lagi tiap 30 detik.")
                        sudah_lapor_bentrok = True
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(5)
                continue
            sudah_lapor_bentrok = False
            for u in update:
                offset = u["update_id"] + 1
                try:
                    if "callback_query" in u:
                        await tangani_callback(u["callback_query"])
                    elif "message" in u:
                        await tangani_balasan(u["message"])
                except Exception as e:      # satu pembaruan rusak tidak boleh menghentikan loop
                    log.info(f"⚠️  Gagal menangani pembaruan Telegram: {ns._sensor(str(e))}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.info(f"⚠️  Penerima tombol Telegram tersendat: {ns._sensor(str(e))}")
            await asyncio.sleep(5)

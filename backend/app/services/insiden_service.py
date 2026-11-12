"""
insiden_service.py
==================
Langkah manusia pada satu insiden: klaim, tutup, dan putusan.

Dipakai oleh endpoint REST (dashboard) dan oleh tombol Telegram, supaya aturannya
ditulis sekali. Setiap langkah:
  1. disimpan ke database,
  2. disiarkan ke semua dashboard lewat WebSocket, supaya banner di semua layar
     berubah bersamaan (merah -> amber -> hilang),
  3. menyunting pesan Telegram insiden itu, supaya grup melihat status yang sama.

Urutannya sama dengan alert baru: database, WebSocket, lalu Telegram. Telegram
dijalankan di latar belakang dan kegagalannya tidak membatalkan apa pun.
"""

import asyncio
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, utc_now_naive
from app.db.models import AlertRecord
from app.models.schemas import AlertResponse, FallState, Putusan, WSMessage
from app.websocket.ws_manager import manager

log = get_logger("app.services.insiden_service")


class InsidenTidakAda(Exception):
    """Alert dengan id itu tidak ada."""


class KonflikInsiden(Exception):
    """Langkah ditolak karena keadaan insiden sudah berubah, mis. sudah diklaim orang lain."""


def alert_ke_dict(alert: AlertRecord) -> dict:
    """Bentuk JSON alert yang sama dengan jawaban API, untuk WebSocket dan Telegram."""
    return AlertResponse.model_validate(alert).model_dump(mode="json")


def jam(waktu) -> str:
    """Jam setempat 14.32 dari waktu UTC tanpa zona."""
    from datetime import timezone
    if waktu is None:
        return ""
    return waktu.replace(tzinfo=timezone.utc).astimezone().strftime("%H.%M")


async def ambil(db: AsyncSession, alert_id: int) -> AlertRecord:
    alert = await db.get(AlertRecord, alert_id)
    if alert is None:
        raise InsidenTidakAda(alert_id)
    return alert


async def _umumkan(alert: AlertRecord, event: str) -> None:
    """Siarkan ke dashboard, lalu perbarui pesan Telegram-nya di latar belakang."""
    data = alert_ke_dict(alert)
    await manager.broadcast(WSMessage(event=event, data=data))
    if alert.telegram_message_id:
        from app.services.notification_service import perbarui_pesan
        asyncio.create_task(perbarui_pesan(data, alert.telegram_message_id, bool(alert.telegram_foto)))


async def klaim(db: AsyncSession, alert_id: int, nama: str) -> AlertRecord:
    """"Saya ke sana": tandai bahwa seseorang menuju lokasi.

    Klaim kedua oleh orang yang sama tidak mengubah apa-apa. Klaim oleh orang lain
    ditolak dengan nama dan jam klaim pertama, supaya dua perawat tidak saling
    menunggu atau sama-sama berangkat tanpa tahu.
    """
    alert = await ambil(db, alert_id)
    if alert.acknowledged:
        raise KonflikInsiden(f"Alarm ini sudah ditangani {alert.acknowledged_by or ''}".rstrip() + ".")
    if alert.claimed_by and alert.claimed_by != nama:
        raise KonflikInsiden(f"Sudah ditangani {alert.claimed_by} sejak {jam(alert.claimed_at)}.")
    if not alert.claimed_by:
        alert.claimed_by = nama
        alert.claimed_at = utc_now_naive()
        await db.commit()
        await db.refresh(alert)
        log.info(f"[{alert.camera_id}] alert #{alert.id} diklaim {nama}")
    await _umumkan(alert, "alert_update")
    return alert


def _isi_putusan(alert: AlertRecord, nama: str, verdict: Optional[Putusan], alasan: Optional[str]) -> None:
    alert.verdict = verdict.value if verdict else None
    alert.verdict_reason = alasan if verdict == Putusan.PALSU else None
    alert.verdict_by = nama if verdict else None
    alert.verdict_at = utc_now_naive() if verdict else None


async def tutup(
    db: AsyncSession,
    alert_id: int,
    nama: str,
    verdict: Optional[Putusan] = None,
    alasan: Optional[str] = None,
    catatan: Optional[str] = None,
) -> AlertRecord:
    """"Tandai Ditangani", dengan putusan dan catatan opsional.

    Menutup ulang alert yang sudah ditangani boleh: penangan dan jamnya tetap,
    catatan dan putusan yang dikirim menimpa yang lama, yang tidak dikirim dibiarkan.
    """
    alert = await ambil(db, alert_id)
    if not alert.acknowledged:
        alert.acknowledged = True
        alert.acknowledged_at = utc_now_naive()
        alert.acknowledged_by = nama
    if catatan is not None:
        alert.caregiver_note = catatan
    if verdict is not None:
        _isi_putusan(alert, nama, verdict, alasan)
    await db.commit()
    await db.refresh(alert)
    log.info(f"[{alert.camera_id}] alert #{alert.id} ditangani {nama}"
             + (f", putusan {alert.verdict}" if alert.verdict else ", belum dinilai"))

    await tutup_insiden_kamera(alert, db)
    # Nama event lama dipertahankan: dashboard menghapus banner saat menerima alert_ack.
    await _umumkan(alert, "alert_ack")
    return alert


async def putuskan(db: AsyncSession, alert_id: int, nama: str,
                   verdict: Putusan, alasan: Optional[str]) -> AlertRecord:
    """Isi atau ubah putusan belakangan, mis. dari halaman Riwayat Insiden."""
    alert = await ambil(db, alert_id)
    if not alert.acknowledged:
        raise KonflikInsiden("Tandai ditangani dulu, baru beri putusan.")
    _isi_putusan(alert, nama, verdict, alasan)
    await db.commit()
    await db.refresh(alert)
    await _umumkan(alert, "alert_update")
    return alert


async def tutup_insiden_kamera(alert: AlertRecord, db: AsyncSession) -> bool:
    """Alert yang ditangani menutup insiden yang sedang berjalan di kameranya.

    Tanpa ini kamera bisa tersangkut di CONFIRMED_FALL setelah alarm ditangani:
    deteksi yang ragu-ragu (mis. wajah memenuhi frame sehingga bahu dan pinggul
    tidak terlihat) MENAHAN timer, jadi tidak ada observasi yang bisa
    mengembalikannya ke MONITORING. Dashboard tetap merah, dan jatuh berikutnya
    di kamera itu tidak berbunyi karena alarmnya dianggap sudah terkirim.

    Dua pengaman supaya penutupan tidak salah sasaran:
      - hanya kalau kamera memang sedang CONFIRMED_FALL. Jatuh baru yang masih
        dihitung (POSSIBLE_FALL) tidak boleh ikut terhapus timernya;
      - hanya alert TERBARU kamera itu. Menandai alert lama dari halaman Riwayat
        Insiden tidak boleh mereset kejadian yang sedang berlangsung sekarang.

    Kalau orangnya ternyata masih tergeletak, timer mulai lagi dari nol dan alarm
    berbunyi lagi setelah ambang -- itu perilaku yang aman.

    Returns:
        True kalau state machine kamera direset.
    """
    from app.runtime.registry import registry

    fsm = registry.state_machines.get(alert.camera_id)
    if fsm is None or fsm.state != FallState.CONFIRMED_FALL:
        return False

    lebih_baru = await db.scalar(
        select(func.count(AlertRecord.id)).where(
            AlertRecord.camera_id == alert.camera_id,
            AlertRecord.id > alert.id,
        )
    )
    if lebih_baru:
        return False

    fsm.reset()
    # Simulasi yang masih berjalan akan langsung memicu timer lagi, jadi ikut
    # diakhiri: "ditangani" berarti kejadiannya -- simulasi atau bukan -- selesai.
    registry.simulasi_sampai.pop(alert.camera_id, None)
    log.info(f"[{alert.camera_id}] insiden ditutup lewat alert #{alert.id}, kembali ke MONITORING")
    return True

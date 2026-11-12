"""
alert_service.py
================
Service yang menangani logika pengiriman alert ketika
terjadi deteksi jatuh (CONFIRMED_FALL).

Tugas utama:
1. Mengecek cooldown per kamera (mencegah spam alert).
2. Menyimpan record ke database via AlertRepository, beserta foto kejadian,
   ambang, dan mode detektor yang berlaku saat itu.
3. Melakukan broadcast ke WebSocket (untuk frontend).
4. (Opsional) Mengirim pesan ke Telegram, sesuai pengaturan di dashboard.
"""

import time
from typing import Dict, Optional

from app.core.config import get_settings
from app.db.database import get_session_factory
from app.db.models import AlertRecord, AlertSnapshot
from app.db.repository import AlertRepository, SettingRepository
from app.models.schemas import AlertCreate, AlertSeverity, TelegramSettings, WSMessage
from app.services.insiden_service import alert_ke_dict
from app.websocket.ws_manager import manager

from app.core.logging import get_logger
log = get_logger("app.services.alert_service")


class AlertService:
    def __init__(self):
        self.settings = get_settings()
        # Menyimpan timestamp alert terakhir per camera_id
        self._last_alert_time: Dict[str, float] = {}

    async def process_confirmed_fall(self, camera_id: str, duration: float) -> None:
        """Dipanggil oleh detection_pipeline saat CONFIRMED_FALL."""
        now = time.time()
        last_time = self._last_alert_time.get(camera_id, 0.0)

        # 1. Cek Cooldown
        if (now - last_time) < self.settings.ALERT_COOLDOWN_SEC:
            log.info(f"[{camera_id}] Alert ditekan (cooldown aktif).")
            return

        self._last_alert_time[camera_id] = now

        log.info(f"[{camera_id}] 🚨 Memicu AlertService untuk jatuh berdurasi {duration:.1f}s")

        nama_kamera = await self._nama_kamera(camera_id)

        # Apakah alert ini berasal dari tombol simulasi? Ditentukan di sini, saat
        # alertnya dipicu, bukan belakangan -- masa simulasinya bisa saja sudah
        # lewat ketika baris ini tersimpan.
        from app.runtime.registry import registry
        from app.services import inference_service, klip
        from app.services.notification_service import dikonfigurasi

        disimulasikan = registry.sedang_disimulasikan(camera_id)
        awalan = "[SIMULASI] " if disimulasikan else ""
        fsm = registry.state_machines.get(camera_id)
        foto = registry.latest_jpeg.get(camera_id)

        factory = get_session_factory()
        async with factory() as session:
            tg = await SettingRepository(session).telegram()
            status_tg = self._status_awal_telegram(disimulasikan, tg, dikonfigurasi())
            alert_data = AlertCreate(
                camera_id=camera_id,
                # _nama_kamera jatuh ke camera_id kalau namanya tidak terbaca, dan itu
                # bukan nama ruang, jadi kolomnya dibiarkan kosong.
                camera_name=nama_kamera if nama_kamera != camera_id else None,
                severity=AlertSeverity.CRITICAL,
                message=f"{awalan}Terdeteksi jatuh pada {nama_kamera} selama {duration:.1f} detik.",
                fall_duration=duration,
                simulated=disimulasikan,
                # Ambang dan mode saat ini ikut dicatat: tanpa keduanya, angka alarm
                # palsu di riwayat tidak bisa ditafsirkan.
                threshold_sec=fsm.fall_duration_threshold if fsm else self.settings.FALL_DURATION_THRESHOLD,
                detection_mode=inference_service.mode_aktif(),
                telegram_status=status_tg,
                klip_status="merekam" if klip.aktif() else None,
            )
            # 2. Simpan ke Database, berikut frame beranotasi yang sudah ada di registry.
            db_alert = await AlertRepository(session).create_alert(alert_data, foto=foto)
            data = alert_ke_dict(db_alert)

        # Klip dari sebelum orangnya tergeletak sampai beberapa detik sesudah alarm.
        if data.get("klip_status") == "merekam":
            klip.mulai_rekam(data["id"], camera_id, now, duration)

        # 3. Broadcast ke WebSocket -- SEBELUM Telegram, dan di luar sesi database.
        # Dashboard harus menyala seketika. Telegram boleh lambat atau gagal; ia
        # lapisan kedua, bukan jalur utama. Menaruhnya lebih dulu berarti perawat
        # yang sedang menatap dashboard ikut menunggu timeout jaringan.
        data["camera_name"] = nama_kamera
        await manager.broadcast(WSMessage(event="alert", data=data))

        # 4. Telegram, lengkap dengan potret kejadiannya.
        if status_tg == "mengirim":
            await self.kirim_telegram(db_alert.id, foto=foto, tg=tg, nama_ruang=nama_kamera)
        elif status_tg == "dilewati":
            log.info(f"[{camera_id}] Latihan tidak dikirim ke Telegram (pengaturan bawaan).")

    @staticmethod
    def _status_awal_telegram(latihan: bool, tg: TelegramSettings, siap: bool) -> str:
        if latihan and not tg.send_drills:
            return "dilewati"
        return "mengirim" if siap else "mati"

    async def kirim_telegram(
        self,
        alert_id: int,
        foto: Optional[bytes] = None,
        tg: Optional[TelegramSettings] = None,
        nama_ruang: Optional[str] = None,
    ) -> None:
        """Kirim pesan alarm untuk satu alert dan catat hasilnya. Dipakai juga oleh Coba lagi.

        Hasilnya dicatat di kolom telegram_status dan notified. Kolom itu yang membuat
        kegagalan terlihat di Riwayat Insiden, bukan hilang diam-diam dan menyisakan
        keyakinan palsu bahwa notifikasi sudah sampai.
        """
        from app.services import notification_service as ns

        factory = get_session_factory()
        async with factory() as session:
            alert = await session.get(AlertRecord, alert_id)
            if alert is None:
                return
            if tg is None:
                tg = await SettingRepository(session).telegram()
            if foto is None:
                tersimpan = await session.get(AlertSnapshot, alert_id)
                foto = tersimpan.jpeg if tersimpan else None
            data = alert_ke_dict(alert)
        data["camera_name"] = nama_ruang or data.get("camera_name") or data["camera_id"]

        hasil = await ns.kirim_alert(data, foto, tg.photo_mode)

        async with factory() as session:
            alert = await session.get(AlertRecord, alert_id)
            if alert is None:
                return
            alert.telegram_status = "terkirim" if hasil.berhasil else "gagal"
            alert.notified = hasil.berhasil
            alert.telegram_message_id = hasil.message_id
            alert.telegram_foto = hasil.dengan_foto
            await session.commit()
            await session.refresh(alert)
            berubah = bool(alert.claimed_by or alert.acknowledged)
            data = alert_ke_dict(alert)
        data["camera_name"] = nama_ruang or data.get("camera_name") or data["camera_id"]

        # Perawat bisa sudah menekan "Saya ke sana" selama pesan ini masih dikirim
        # (percobaan ulang bisa makan puluhan detik). Samakan pesannya sekarang.
        if hasil.berhasil and hasil.message_id and berubah:
            await ns.perbarui_pesan(data, hasil.message_id, hasil.dengan_foto)

    @staticmethod
    def _waktu_lokal(utc_naive):
        """created_at tersimpan sebagai UTC tanpa zona. Perawat membaca jam setempat;
        tanpa konversi ini pesan Telegram selisih 7 jam di WIB."""
        from datetime import timezone
        return utc_naive.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)

    async def _nama_kamera(self, camera_id: str) -> str:
        """Nama kamar untuk ditampilkan, dengan camera_id sebagai cadangan.

        Perawat mengenal "Kamar 01 - Jenderal Ilham", bukan "cam-01".
        """
        from app.db.repository import CameraRepository

        try:
            async with get_session_factory()() as session:
                record = await CameraRepository(session).get_camera(camera_id)
                if record and record.name:
                    return record.name
        except Exception as e:   # database bermasalah tidak boleh membatalkan alert
            log.info(f"[{camera_id}] gagal membaca nama kamera: {e}")
        return camera_id


# Singleton
alert_service = AlertService()

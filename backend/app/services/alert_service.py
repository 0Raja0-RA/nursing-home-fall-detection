"""
alert_service.py
================
Service yang menangani logika pengiriman alert ketika
terjadi deteksi jatuh (CONFIRMED_FALL).

Tugas utama:
1. Mengecek cooldown per kamera (mencegah spam alert).
2. Menyimpan record ke database via AlertRepository.
3. Melakukan broadcast ke WebSocket (untuk frontend).
4. (Opsional) Mengirim notifikasi ke Telegram.
"""

import time
from typing import Dict

from app.core.config import get_settings
from app.db.database import get_session_factory
from app.db.repository import AlertRepository
from app.models.schemas import AlertCreate, AlertSeverity, WSMessage
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
        disimulasikan = registry.sedang_disimulasikan(camera_id)
        awalan = "[SIMULASI] " if disimulasikan else ""

        # Siapkan payload
        message_text = f"{awalan}Terdeteksi jatuh pada {nama_kamera} selama {duration:.1f} detik."
        alert_data = AlertCreate(
            camera_id=camera_id,
            severity=AlertSeverity.CRITICAL,
            message=message_text,
            fall_duration=duration,
            simulated=disimulasikan,
        )
        
        # 2. Simpan ke Database
        factory = get_session_factory()
        db_alert = None
        async with factory() as session:
            db_alert = await AlertRepository(session).create_alert(alert_data)

        if not db_alert:
            return

        # 3. Broadcast ke WebSocket -- SEBELUM Telegram, dan di luar sesi database.
        # Dashboard harus menyala seketika. Telegram boleh lambat atau gagal; ia
        # lapisan kedua, bukan jalur utama. Menaruhnya lebih dulu berarti perawat
        # yang sedang menatap dashboard ikut menunggu timeout jaringan.
        await manager.broadcast(WSMessage(
            event="alert",
            data={
                "id": db_alert.id,
                "camera_id": db_alert.camera_id,
                "camera_name": nama_kamera,
                "message": db_alert.message,
                "severity": db_alert.severity,
                "created_at": db_alert.created_at.isoformat(),
                "fall_duration": db_alert.fall_duration,
                "simulated": db_alert.simulated,
            }
        ))

        # 4. Telegram, lengkap dengan potret kejadiannya.
        # Frame terakhir sudah digambari kotak dan dikemas jadi JPEG oleh pipeline,
        # jadi melampirkannya tidak menambah pekerjaan sama sekali.
        from app.services.notification_service import send_telegram_alert

        foto = registry.latest_jpeg.get(camera_id)
        terkirim = await send_telegram_alert(
            camera_name=nama_kamera,
            fall_duration=duration,
            foto=foto,
            waktu=db_alert.created_at,
            simulasi=disimulasikan,
        )

        # 5. Catat hasilnya. Kolom ini yang membuat kegagalan terlihat di Riwayat
        # Insiden, bukan hilang diam-diam dan menyisakan keyakinan palsu bahwa
        # notifikasi sudah sampai.
        async with factory() as session:
            await AlertRepository(session).mark_as_notified(db_alert.id, terkirim)

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

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
        
        # Siapkan payload
        message_text = f"Peringatan: Terdeteksi jatuh pada {camera_id} selama {duration:.1f} detik."
        alert_data = AlertCreate(
            camera_id=camera_id,
            severity=AlertSeverity.CRITICAL,
            message=message_text,
            fall_duration=duration,
        )
        
        # 2. Simpan ke Database
        factory = get_session_factory()
        db_alert = None
        async with factory() as session:
            repo = AlertRepository(session)
            db_alert = await repo.create_alert(alert_data)
            
            # TODO: Di sini kita bisa panggil API Telegram secara async
            # jika berhasil -> await repo.mark_as_notified(db_alert.id, True)
        
        # 3. Broadcast ke WebSocket
        if db_alert:
            ws_msg = WSMessage(
                event="alert",
                data={
                    "id": db_alert.id,
                    "camera_id": db_alert.camera_id,
                    "message": db_alert.message,
                    "severity": db_alert.severity,
                    "created_at": db_alert.created_at.isoformat(),
                    "fall_duration": db_alert.fall_duration,
                }
            )
            await manager.broadcast(ws_msg)


# Singleton
alert_service = AlertService()

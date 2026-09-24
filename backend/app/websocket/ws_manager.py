"""
ws_manager.py
=============
WebSocket manager untuk push live status ke frontend.

Mengelola koneksi WebSocket dari dashboard dan broadcast
status update serta alert secara real-time tanpa polling.

Event types yang dikirim:
    - status_update : Update postur & state per kamera (setiap frame)
    - alert         : Notifikasi fall confirmed
    - heartbeat     : Keep-alive setiap 30 detik
"""

import asyncio
import json
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.schemas import WSMessage

router = APIRouter()


class ConnectionManager:
    """Mengelola koneksi WebSocket aktif."""

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Terima koneksi WebSocket baru."""
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        print(f"🔌 WebSocket connected (total: {len(self._connections)})")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Hapus koneksi WebSocket."""
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        print(f"🔌 WebSocket disconnected (total: {len(self._connections)})")

    async def broadcast(self, message: WSMessage) -> None:
        """Kirim pesan ke semua client yang terhubung."""
        data = message.model_dump_json()
        disconnected = []

        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    disconnected.append(ws)

        # Cleanup koneksi yang mati
        for ws in disconnected:
            await self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: WSMessage) -> None:
        """Kirim pesan ke satu client tertentu."""
        await websocket.send_text(message.model_dump_json())

    @property
    def active_connections(self) -> int:
        """Jumlah koneksi aktif."""
        return len(self._connections)


# Singleton instance
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint untuk dashboard live updates.

    Frontend connect ke ws://host:8000/ws dan akan menerima:
    - status_update setiap kali ada frame baru diproses
    - alert saat fall dikonfirmasi
    - heartbeat setiap 30 detik
    """
    await manager.connect(websocket)

    try:
        while True:
            # Terima pesan dari client (misal: acknowledge, ping)
            data = await websocket.receive_text()
            # Handle client messages jika diperlukan
            if data == "ping":
                await manager.send_personal(
                    websocket,
                    WSMessage(event="heartbeat", data={"status": "pong"}),
                )
    except WebSocketDisconnect:
        await manager.disconnect(websocket)

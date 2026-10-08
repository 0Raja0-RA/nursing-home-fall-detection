"""
models.py
=========
SQLAlchemy declarative models.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase

from app.core.logging import utc_now_naive


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class CameraRecord(Base):
    """Tabel kamera yang terdaftar di sistem.

    Sumber kamera disimpan di database, bukan di environment variable, supaya
    alamat IP bisa diganti lewat dashboard tanpa menyunting kode dan tanpa
    me-restart server. Ini penting karena alamat kamera HP berubah setiap kali
    berpindah jaringan WiFi.

    Rotasi disimpan per kamera, bukan global: satu sistem bisa memakai kamera HP
    yang butuh 90 derajat bersamaan dengan webcam laptop yang tidak perlu diputar.
    """

    __tablename__ = "cameras"

    id = Column(String, primary_key=True)                      # cam-01, cam-02, ...
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)                    # "0" | http://... | rtsp://... | path file
    rotate = Column(Integer, nullable=False, default=0)        # 0, 90, 180, 270 (searah jarum jam)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now_naive)


class AlertRecord(Base):
    """Tabel riwayat alert fall detection."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="critical")
    message = Column(String, nullable=False)
    fall_duration = Column(Float, nullable=False)
    acknowledged = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)  # Baru ditambahkan untuk status Telegram
    created_at = Column(DateTime, default=utc_now_naive)
    acknowledged_at = Column(DateTime, nullable=True)

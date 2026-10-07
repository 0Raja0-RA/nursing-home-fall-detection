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

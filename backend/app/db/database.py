"""
database.py
===========
Setup database menggunakan SQLAlchemy async + aiosqlite.

Menyimpan riwayat alert (fall detection events) dalam SQLite.
Di production bisa diganti ke PostgreSQL dengan mengubah
DATABASE_URL di .env.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


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
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)


# ---- Engine & Session Factory ------------------------------

_engine = None
_async_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
        )
    return _engine


def get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency: beri async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Buat semua tabel jika belum ada."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database initialized")

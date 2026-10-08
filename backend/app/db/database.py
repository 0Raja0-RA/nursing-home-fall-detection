"""
database.py
===========
Setup database menggunakan SQLAlchemy async + aiosqlite.

Menyimpan riwayat alert (fall detection events) dalam SQLite.
Di production bisa diganti ke PostgreSQL dengan mengubah
DATABASE_URL di .env.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.db.models import Base, AlertRecord

from app.core.logging import get_logger
log = get_logger("app.db.database")


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


# Kolom yang ditambahkan setelah tabelnya pernah dibuat di komputer orang lain.
# create_all() hanya membuat tabel yang belum ada; ia TIDAK menambahkan kolom ke
# tabel yang sudah terlanjur ada. Tanpa penambalan ini, satu-satunya cara memakai
# kolom baru adalah menghapus fall_detection.db -- berikut seluruh riwayat alert
# yang sudah terkumpul.
_KOLOM_SUSULAN: dict[str, list[tuple[str, str]]] = {
    "alerts": [
        ("notified", "BOOLEAN DEFAULT 0"),
        ("simulated", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
}


async def _tambal_kolom(conn) -> None:
    """Tambahkan kolom yang belum ada pada database lama."""
    from sqlalchemy import text

    for tabel, kolom in _KOLOM_SUSULAN.items():
        hasil = await conn.execute(text(f"PRAGMA table_info({tabel})"))
        ada = {baris[1] for baris in hasil.fetchall()}
        if not ada:
            continue    # tabelnya memang belum ada; create_all sudah membuatnya lengkap
        for nama, tipe in kolom:
            if nama not in ada:
                await conn.execute(text(f"ALTER TABLE {tabel} ADD COLUMN {nama} {tipe}"))
                log.info(f"🔧 Kolom {tabel}.{nama} ditambahkan ke database yang sudah ada")


async def init_db() -> None:
    """Buat semua tabel jika belum ada, lalu tambal kolom yang menyusul."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _tambal_kolom(conn)
    log.info("✅ Database initialized")

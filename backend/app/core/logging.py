"""
logging.py
==========
Konfigurasi logging terpusat.

Mengganti semua print() di backend. Alasan utamanya: print() dengan emoji
crash di konsol Windows (cp1252) dengan UnicodeEncodeError. Logging dengan
handler UTF-8 tidak punya masalah ini, dan level-nya bisa diatur dari .env.

Pakai:
    from app.core.logging import get_logger
    log = get_logger(__name__)
    log.info("...")
"""

import logging
import sys

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Paksa stdout/stderr ke UTF-8 supaya emoji di pesan log tidak meledak di Windows.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    root = logging.getLogger("app")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)


def utc_now_naive():
    """Waktu UTC tanpa zona (naive), format yang tersimpan di kolom DateTime SQLite.

    datetime.utcnow() sudah deprecated di Python 3.12+, tapi kolom DateTime kita
    menyimpan naive. Helper ini menghasilkan nilai yang SAMA dengan utcnow() tanpa
    memunculkan DeprecationWarning, jadi data lama tetap konsisten.
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)

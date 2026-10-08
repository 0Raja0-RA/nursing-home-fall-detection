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
import re
import sys

_CONFIGURED = False

# Token bot Telegram berbentuk <angka>:<rahasia>.
_POLA_RAHASIA = re.compile(r"\d{6,}:[A-Za-z0-9_\-]{20,}")


class SensorRahasia(logging.Filter):
    """Hapus token dari setiap catatan log, apa pun sumbernya.

    Bukan kehati-hatian berlebihan: URL Bot API memuat token di dalam path-nya,
    dan httpx mencatat URL permintaan secara lengkap di level INFO. Tanpa
    penyaring ini, setiap panggilan ke Telegram meninggalkan token utuh di log
    backend -- log yang rutin ditempel ke chat atau issue saat minta bantuan.

    Dipasang di tingkat handler supaya mencakup library mana pun, bukan hanya
    kode kita sendiri.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            pesan = record.getMessage()
        except Exception:
            return True
        if _POLA_RAHASIA.search(pesan):
            record.msg = _POLA_RAHASIA.sub("<TOKEN-DISENSOR>", pesan)
            record.args = ()
        return True


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
    handler.addFilter(SensorRahasia())

    root = logging.getLogger("app")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False

    # Pasang penyaring yang sama di root logger, supaya catatan dari library lain
    # (httpx, uvicorn, sqlalchemy) ikut tersensor meski tidak lewat logger "app".
    penyaring = SensorRahasia()
    for h in logging.getLogger().handlers:
        h.addFilter(penyaring)
    logging.getLogger().addFilter(penyaring)

    # httpx mencatat URL permintaan secara utuh di level INFO. Untuk panggilan ke
    # Bot API, URL itu memuat token. Penyaring di atas sudah menanganinya, tapi
    # barisnya juga tidak memberi informasi berguna, jadi sekalian diredam.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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

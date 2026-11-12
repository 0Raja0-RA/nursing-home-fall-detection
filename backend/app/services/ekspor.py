"""
ekspor.py
=========
Riwayat insiden sebagai CSV, untuk uji mini dan laporan (docs/uji-mini.md).

- Waktu ditulis dalam zona waktu komputer yang menjalankan backend, karena laptop
  backend dan jam pengamat uji berada di tempat yang sama. Di database waktunya UTC.
- Waktu respons sudah dihitung dalam detik bulat, supaya tidak perlu rumus.
- Diawali BOM UTF-8 supaya Excel membaca huruf non-ASCII dengan benar.
- Sel yang diawali =, +, -, atau @ diberi tanda kutip tunggal di depannya, supaya
  spreadsheet tidak menjalankannya sebagai rumus. Nama penangan dari Telegram
  ditulis oleh pemilik akun Telegram itu, bukan oleh tim.
"""

import csv
import io
from datetime import datetime, timezone
from typing import Iterable, Optional

from app.db.models import AlertRecord
from app.models.schemas import ALASAN_PALSU, LABEL_PUTUSAN

KOLOM = [
    "id", "waktu_alarm", "ruang", "kamera_id", "latihan",
    "mode_deteksi", "ambang_detik", "lama_tergeletak_detik",
    "diklaim_oleh", "waktu_klaim", "ditangani_oleh", "waktu_ditangani",
    # Respons pertama: klaim "Saya ke sana", atau penutupan bila tidak ada yang mengklaim.
    "detik_sampai_respons", "detik_sampai_ditangani",
    "putusan", "alasan_palsu", "dinilai_oleh", "waktu_dinilai",
    "telegram", "catatan",
]

_LABEL_TELEGRAM = {
    "terkirim": "terkirim",
    "gagal": "gagal",
    "mengirim": "sedang dikirim",
    "mati": "belum dikonfigurasi",
    "dilewati": "tidak dikirim (latihan)",
}


def _waktu(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.replace(tzinfo=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _detik(awal: Optional[datetime], akhir: Optional[datetime]) -> str:
    if awal is None or akhir is None:
        return ""
    return str(max(0, round((akhir - awal).total_seconds())))


def _angka(nilai: Optional[float]) -> str:
    return "" if nilai is None else f"{round(nilai, 1):g}"


def _telegram(a: AlertRecord) -> str:
    if a.telegram_status:
        return _LABEL_TELEGRAM.get(a.telegram_status, a.telegram_status)
    return "terkirim" if a.notified else ""     # alert lama, sebelum kolom status ada


def _aman(nilai: str) -> str:
    return "'" + nilai if nilai[:1] in ("=", "+", "-", "@", "\t", "\r") else nilai


def csv_insiden(alerts: Iterable[AlertRecord]) -> str:
    """Satu baris per alert, urut sesuai masukan. Mengembalikan teks CSV berawalan BOM."""
    buf = io.StringIO()
    tulis = csv.writer(buf, lineterminator="\r\n")
    tulis.writerow(KOLOM)
    for a in alerts:
        respons = min((t for t in (a.claimed_at, a.acknowledged_at) if t is not None), default=None)
        baris = [
            str(a.id), _waktu(a.created_at), a.camera_name or a.camera_id, a.camera_id,
            "ya" if a.simulated else "tidak",
            a.detection_mode or "", _angka(a.threshold_sec), _angka(a.fall_duration),
            a.claimed_by or "", _waktu(a.claimed_at),
            a.acknowledged_by or "", _waktu(a.acknowledged_at),
            _detik(a.created_at, respons), _detik(a.created_at, a.acknowledged_at),
            LABEL_PUTUSAN.get(a.verdict, a.verdict or ""),
            ALASAN_PALSU.get(a.verdict_reason, a.verdict_reason or ""),
            a.verdict_by or "", _waktu(a.verdict_at),
            _telegram(a), a.caregiver_note or "",
        ]
        tulis.writerow([_aman(sel) for sel in baris])
    return "﻿" + buf.getvalue()

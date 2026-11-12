"""
shift.py
========
Ringkasan per shift untuk serah terima: alarm selama shift, yang masih perlu
ditindaklanjuti shift berikutnya, catatan perawat, Mode perawatan, dan tanda sudah dibaca.

Batas shift memakai jam setempat komputer backend, karena itulah jam dinding panti.
Database menyimpan UTC, jadi batasnya dikonversi sebelum dipakai di query.
Pola shift diatur di Pengaturan: 3 shift (07, 14, 21) atau 2 shift (07, 19).
"""

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AlertRecord, CameraRecord, JedaKamera, SerahTerima
from app.models.schemas import AlertResponse, Putusan, RingkasanShift

POLA = {"3": [7, 14, 21], "2": [7, 19]}
NAMA = {3: ["Pagi", "Sore", "Malam"], 2: ["Pagi", "Malam"]}


def batas_shift(sekarang_lokal: datetime, jam_mulai: list[int], geser: int = 0) -> tuple[str, datetime, datetime]:
    """Shift ke-`geser` dari shift yang sedang berjalan (0 = sekarang, -1 = sebelumnya).

    Returns: (nama, mulai, selesai), keduanya jam setempat tanpa zona.
    """
    jumlah_hari = abs(geser) // len(jam_mulai) + 2
    hari = sekarang_lokal.date()
    mulai = sorted(datetime.combine(hari + timedelta(days=d), time(j))
                   for d in range(-jumlah_hari, 2) for j in jam_mulai)
    berjalan = max(i for i, m in enumerate(mulai) if m <= sekarang_lokal)
    i = berjalan + geser
    return NAMA[len(jam_mulai)][jam_mulai.index(mulai[i].hour)], mulai[i], mulai[i + 1]


def ke_utc(lokal: datetime) -> datetime:
    """Jam setempat tanpa zona menjadi UTC tanpa zona, seperti kolom waktu di database."""
    return lokal.astimezone().astimezone(timezone.utc).replace(tzinfo=None)


async def ringkasan(db: AsyncSession, jam_mulai: list[int], geser: int,
                    sekarang_lokal: datetime | None = None) -> RingkasanShift:
    from app.services.insiden_service import hitung_metrik

    sekarang_lokal = sekarang_lokal or datetime.now()
    nama, mulai_lokal, selesai_lokal = batas_shift(sekarang_lokal, jam_mulai, geser)
    mulai, selesai = ke_utc(mulai_lokal), ke_utc(selesai_lokal)

    alerts = (await db.execute(
        select(AlertRecord).where(AlertRecord.created_at >= mulai, AlertRecord.created_at < selesai)
        .order_by(AlertRecord.created_at)
    )).scalars().all()
    sungguhan = [a for a in alerts if not a.simulated]
    perlu = [a for a in sungguhan if not a.acknowledged
             or a.verdict in (None, Putusan.BELUM_YAKIN.value)]

    jeda = (await db.execute(
        select(JedaKamera).where(JedaKamera.mulai < selesai,
                                 func.coalesce(JedaKamera.selesai, JedaKamera.sampai) > mulai)
        .order_by(JedaKamera.mulai)
    )).scalars().all()

    terputus: list[str] = []
    if geser == 0:
        from app.runtime.registry import registry
        kamera = (await db.execute(select(CameraRecord).where(CameraRecord.enabled.is_(True)))).scalars().all()
        terputus = [k.name for k in kamera
                    if not (registry.cameras.get(k.id) and registry.cameras[k.id].sedang_mengalir)]

    dibaca = await db.get(SerahTerima, mulai)
    return RingkasanShift(
        nama=nama, geser=geser, mulai=mulai, selesai=selesai, berjalan=geser == 0,
        metrik=hitung_metrik(sungguhan),
        latihan=len(alerts) - len(sungguhan),
        perlu_tindakan=[AlertResponse.model_validate(a) for a in perlu],
        catatan=[AlertResponse.model_validate(a) for a in sungguhan if a.caregiver_note],
        jeda=[{"camera_name": j.camera_name or j.camera_id, "mulai": j.mulai, "sampai": j.selesai or j.sampai,
               "oleh": j.oleh, "dihentikan_oleh": j.diakhiri_oleh} for j in jeda],
        kamera_terputus=terputus,
        dibaca_oleh=dibaca.dibaca_oleh if dibaca else None,
        dibaca_pada=dibaca.dibaca_pada if dibaca else None,
    )


async def tandai_dibaca(db: AsyncSession, jam_mulai: list[int], geser: int, oleh: str,
                        sekarang_lokal: datetime | None = None) -> None:
    """Catat bahwa ringkasan shift yang sudah selesai dibaca shift berikutnya."""
    from app.core.logging import utc_now_naive

    _, mulai_lokal, _ = batas_shift(sekarang_lokal or datetime.now(), jam_mulai, geser)
    mulai = ke_utc(mulai_lokal)
    baris = await db.get(SerahTerima, mulai)
    if baris is None:
        db.add(SerahTerima(shift_mulai=mulai, dibaca_oleh=oleh, dibaca_pada=utc_now_naive()))
        await db.commit()


def pola_dari(nilai: str | None) -> list[int]:
    return POLA.get(nilai or "3", POLA["3"])


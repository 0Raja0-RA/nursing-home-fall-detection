"""
episode.py
==========
Episode berbaring: setiap kali seseorang terbaca berbaring cukup lama sampai hitungan
dimulai, berapa lama paling jauh hitungannya, dan apakah sampai berbunyi.

Gunanya pratinjau ambang di Pengaturan. Alarm saja tidak cukup untuk menilai ambang:
yang berhenti sebelum ambang tidak pernah tercatat, sehingga tidak bisa diketahui
berapa alarm tambahan bila ambang diturunkan. Episode mencatat keduanya.

Episode yang berakhir karena alarmnya ditutup ("Tandai Ditangani" mereset hitungan)
ditandai `dipotong`. Lamanya hanya sampai penutupan, jadi bila ambang dinaikkan
melewati lama itu, belum tentu alarmnya hilang.

Latihan ikut dicatat tetapi tidak dihitung di pratinjau.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, utc_now_naive
from app.db.models import AlertRecord, EpisodeBerbaring
from app.models.schemas import FallState

log = get_logger("app.services.episode")

_HITUNG = (FallState.POSSIBLE_FALL, FallState.CONFIRMED_FALL)


@dataclass
class _Berjalan:
    mulai: datetime
    maks: float = 0.0
    alarm: bool = False
    latihan: bool = False
    dipotong: bool = False


class PencatatEpisode:
    def __init__(self) -> None:
        self._berjalan: dict[str, _Berjalan] = {}
        self._tugas: set[asyncio.Task] = set()

    def amati(self, camera_id: str, state: FallState, durasi: float, latihan: bool) -> Optional[EpisodeBerbaring]:
        """Dipanggil pipeline setiap putaran. Mengembalikan episode yang baru selesai, bila ada."""
        ep = self._berjalan.get(camera_id)
        if state in _HITUNG:
            if ep is None:
                ep = self._berjalan[camera_id] = _Berjalan(mulai=utc_now_naive())
            ep.maks = max(ep.maks, durasi)
            ep.alarm = ep.alarm or state == FallState.CONFIRMED_FALL
            ep.latihan = ep.latihan or latihan
            return None
        if ep is None:
            return None
        del self._berjalan[camera_id]
        selesai = EpisodeBerbaring(camera_id=camera_id, mulai=ep.mulai, selesai=utc_now_naive(),
                                   durasi_maks=round(ep.maks, 2), alarm=ep.alarm, latihan=ep.latihan,
                                   dipotong=ep.dipotong)
        tugas = asyncio.create_task(_simpan(selesai))
        self._tugas.add(tugas)
        tugas.add_done_callback(self._tugas.discard)
        return selesai

    def tandai_dipotong(self, camera_id: str) -> None:
        """Hitungan episode ini direset oleh penutupan alarm, bukan karena orangnya bangun."""
        if camera_id in self._berjalan:
            self._berjalan[camera_id].dipotong = True


pencatat = PencatatEpisode()


async def _simpan(ep: EpisodeBerbaring) -> None:
    from app.db.database import get_session_factory
    try:
        async with get_session_factory()() as db:
            db.add(ep)
            await db.commit()
    except Exception as e:      # catatan statistik tidak boleh mengganggu pipeline
        log.info(f"[{ep.camera_id}] episode berbaring gagal disimpan: {e}")


async def pratinjau(db: AsyncSession, ambang: float, ambang_kini: float, hari: int = 30) -> dict:
    """Apa yang terjadi pada episode `hari` hari terakhir bila ambangnya `ambang` detik.

    Returns:
        episode: jumlah episode sungguhan (bukan latihan) yang tercatat;
        berbunyi: berapa yang akan memicu alarm pada ambang ini;
        hilang: alarm yang dulu berbunyi tetapi tidak lagi, per putusan;
        belum_tentu: alarm yang ditutup sebelum mencapai ambang ini, jadi tidak bisa dipastikan;
        tambahan: episode yang dulu tidak berbunyi tetapi akan berbunyi (belum pernah dinilai).
    """
    batas = utc_now_naive() - timedelta(days=hari)
    episode = (await db.execute(
        select(EpisodeBerbaring).where(EpisodeBerbaring.mulai >= batas, EpisodeBerbaring.latihan.is_(False))
    )).scalars().all()
    alerts = (await db.execute(
        select(AlertRecord).where(AlertRecord.created_at >= batas - timedelta(minutes=10),
                                  AlertRecord.simulated.is_(False))
    )).scalars().all()

    def putusan_episode(ep: EpisodeBerbaring) -> str:
        for a in alerts:
            if a.camera_id == ep.camera_id and ep.mulai <= a.created_at <= ep.selesai + timedelta(seconds=2):
                return a.verdict or "belum_dinilai"
        return "belum_dinilai"

    hilang, belum_tentu, tambahan, berbunyi = Counter(), 0, 0, 0
    for ep in episode:
        if ep.alarm:
            if ep.durasi_maks >= ambang:
                berbunyi += 1
            elif ep.dipotong:
                belum_tentu += 1
                berbunyi += 1       # dianggap tetap berbunyi; lamanya tidak diketahui
            else:
                hilang[putusan_episode(ep)] += 1
        elif ep.durasi_maks >= ambang:
            tambahan += 1
            berbunyi += 1
    return {
        "ambang": ambang,
        "ambang_kini": ambang_kini,
        "hari": hari,
        "episode": len(episode),
        "berbunyi": berbunyi,
        "hilang": dict(hilang),
        "belum_tentu": belum_tentu,
        "tambahan": tambahan,
    }

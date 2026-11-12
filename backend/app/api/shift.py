"""
shift.py
========
Ringkasan per shift untuk serah terima.

Endpoints:
    GET  /api/ringkasan-shift/?geser=0        — Shift berjalan (0), sebelumnya (-1), dan seterusnya
    POST /api/ringkasan-shift/dibaca?geser=-1 — Tandai ringkasan shift yang sudah selesai sudah dibaca
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import wajib_login
from app.db.database import get_db
from app.db.repository import KUNCI_POLA_SHIFT, SettingRepository
from app.models.schemas import RingkasanShift
from app.services import shift

router = APIRouter()


async def _pola(db: AsyncSession) -> list[int]:
    return shift.pola_dari(await SettingRepository(db).ambil(KUNCI_POLA_SHIFT))


@router.get("/", response_model=RingkasanShift)
async def ringkasan_shift(geser: int = Query(0, ge=-90, le=0), db: AsyncSession = Depends(get_db)):
    """Alarm, yang perlu ditindaklanjuti, catatan, dan Mode perawatan selama satu shift."""
    return await shift.ringkasan(db, await _pola(db), geser)


@router.post("/dibaca", response_model=RingkasanShift)
async def tandai_dibaca(geser: int = Query(..., ge=-90, le=-1), user=Depends(wajib_login),
                        db: AsyncSession = Depends(get_db)):
    """Tanda serah terima: ringkasan shift yang sudah selesai dibaca shift berikutnya."""
    if geser >= 0:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift ini masih berjalan.")
    pola = await _pola(db)
    await shift.tandai_dibaca(db, pola, geser, user.display_name)
    return await shift.ringkasan(db, pola, geser)

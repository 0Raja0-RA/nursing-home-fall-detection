"""
auth.py
=======
Login tim, akses lihat-saja untuk pengunjung pameran, dan perlindungan API.

Endpoints (publik, tanpa login):
    GET  /api/auth/status      — Petunjuk untuk halaman Login
    POST /api/auth/login       — Masuk; sesi disimpan di cookie HttpOnly
    POST /api/auth/pengunjung  — Tukar token dari QR stand dengan sesi lihat-saja
    POST /api/auth/logout      — Keluar dari perangkat ini

Endpoints (wajib login):
    GET  /api/auth/me          — Akun yang sedang masuk (atau "Pengunjung")
    PUT  /api/auth/password    — Ganti kata sandi sendiri (bukan untuk pengunjung)

Endpoints (khusus pengelola, belum dipakai dashboard):
    GET   /api/users/          — Daftar akun
    POST  /api/users/          — Tambah akun
    PATCH /api/users/{id}      — Ubah nama, peran, aktif, atau atur ulang sandi

Akun tim: satu akun demo dibuat otomatis setiap backend menyala, dari DEMO_USERNAME
dan DEMO_PASSWORD di backend/.env (siapkan_akun_demo). Tidak ada akun atau kata sandi
di kode, karena dashboard pameran bisa dibuka dari internet lewat tunnel, dan tidak ada
formulir "buat akun pertama" yang bisa didahului orang asing.

Pengunjung: QR di stand membawa VISITOR_TOKEN, yang dibuat baru setiap launcher pameran
dijalankan. Token itu ditukar dengan cookie lihat-saja yang ditandatangani HMAC dan
berlaku 12 jam. Tanpa tabel: menjalankan ulang dengan token baru membatalkan semua
cookie pengunjung lama. Pengunjung boleh membaca, tetapi semua permintaan yang
mengubah data ditolak (tolak_perubahan_pengunjung).

Kenapa cookie, bukan token di header: video kamera dimuat lewat <img> dan siaran
langsung lewat WebSocket, dan keduanya tidak bisa membawa header Authorization.
Cookie HttpOnly ikut terkirim ke keduanya dan tidak bisa dibaca JavaScript.
SameSite=Lax membuat cookie itu tidak terkirim dari situs lain.
"""

import asyncio
import hashlib
import hmac
import math
import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.keamanan import cocokkan_sandi, hash_sandi, hash_token, token_baru
from app.core.logging import get_logger, utc_now_naive
from app.db.database import get_db, get_session_factory
from app.db.models import SessionRecord, UserRecord
from app.models.schemas import (
    AkunBaru,
    AkunResponse,
    AkunUbah,
    GantiSandi,
    LoginRequest,
    StatusAuth,
    TokenPengunjung,
)

log = get_logger("app.api.auth")

router = APIRouter()
router_akun = APIRouter()

NAMA_COOKIE = "falldetect_sesi"
NAMA_COOKIE_PENGUNJUNG = "falldetect_pengunjung"
# Layar jaga tidak boleh keluar sendiri di tengah shift, jadi sesinya panjang.
UMUR_SESI = timedelta(days=30)
# Cukup untuk satu hari pameran.
UMUR_PENGUNJUNG = timedelta(hours=12)

# Pembatas tebakan: setelah 5 kali gagal dalam 5 menit untuk pasangan alamat dan
# nama pengguna (atau token pengunjung) yang sama, percobaan berikutnya ditolak 1 menit.
BATAS_GAGAL = 5
JENDELA_GAGAL = 300.0
JEDA_KUNCI = 60.0
_gagal: dict[str, list[float]] = {}

# Hash pembanding untuk nama pengguna yang tidak ada, supaya lama jawabannya sama
# dengan nama yang ada dan tidak bisa dipakai menebak daftar akun.
_HASH_TIRUAN = hash_sandi("bukan-kata-sandi-siapa-pun")

# Bukan akun: tidak ada barisnya di tabel users. Perannya membuat semua permintaan
# yang mengubah data ditolak, dan menu tim disembunyikan di dashboard.
PENGUNJUNG = SimpleNamespace(
    id=0, username="pengunjung", display_name="Pengunjung", role="pengunjung", active=True, created_at=None,
)

_METODE_BACA = {"GET", "HEAD", "OPTIONS"}


# ---- Akun demo ------------------------------------------------------------

async def siapkan_akun_demo(db: AsyncSession) -> Optional[UserRecord]:
    """Buat atau samakan akun demo dari backend/.env. Dipanggil sekali saat startup.

    backend/.env yang menang: kata sandi, nama, dan peran akun itu disamakan dengan
    isinya setiap backend menyala, jadi mengganti sandi cukup di satu tempat.

    Akun aktif lainnya dinonaktifkan dan sesinya dihapus, karena keputusannya satu
    akun demo. Tanpa ini, akun demo lama tetap bisa dipakai masuk setelah
    DEMO_USERNAME diganti. Kalau DEMO_* kosong, tidak ada akun yang disentuh.
    """
    s = get_settings()
    username = s.DEMO_USERNAME.strip().lower()
    if not username or not s.DEMO_PASSWORD:
        log.info("👤 Akun demo belum diatur: isi DEMO_USERNAME dan DEMO_PASSWORD di backend/.env "
                 "supaya ada yang bisa masuk ke dashboard.")
        return None

    nama = s.DEMO_NAME.strip() or "Tim FallDetect"
    user = (await db.execute(select(UserRecord).where(UserRecord.username == username))).scalar_one_or_none()
    if user is None:
        user = UserRecord(username=username, display_name=nama, role="pengelola",
                          password_hash=await asyncio.to_thread(hash_sandi, s.DEMO_PASSWORD))
        db.add(user)
        log.info(f"👤 Akun demo {username} dibuat")
    else:
        if not await asyncio.to_thread(cocokkan_sandi, s.DEMO_PASSWORD, user.password_hash):
            user.password_hash = await asyncio.to_thread(hash_sandi, s.DEMO_PASSWORD)
            await _hapus_sesi_akun(db, user.id)
            log.info(f"👤 Sandi akun demo {username} disamakan dengan backend/.env")
        user.display_name = nama
        user.role = "pengelola"
        user.active = True
    await db.flush()        # akun baru butuh id sebelum akun lain dibandingkan dengannya

    lain = (await db.execute(
        select(UserRecord).where(UserRecord.id != user.id, UserRecord.active.is_(True))
    )).scalars().all()
    for akun in lain:
        akun.active = False
        await _hapus_sesi_akun(db, akun.id)
    if lain:
        log.info(f"👤 {len(lain)} akun lain dinonaktifkan supaya hanya akun demo yang aktif: "
                 + ", ".join(a.username for a in lain))
    await db.commit()
    await db.refresh(user)
    return user


# ---- Sesi tim -------------------------------------------------------------

async def pengguna_dari_token(token: Optional[str], db: AsyncSession) -> Optional[UserRecord]:
    """Akun pemilik token sesi, atau None kalau token kosong, kedaluwarsa, atau akunnya nonaktif."""
    if not token:
        return None
    sesi = await db.get(SessionRecord, hash_token(token))
    if sesi is None or sesi.expires_at < utc_now_naive():
        return None
    user = await db.get(UserRecord, sesi.user_id)
    if user is None or not user.active:
        return None
    return user


async def _mulai_sesi(user: UserRecord, response: Response, db: AsyncSession) -> None:
    sekarang = utc_now_naive()
    token = token_baru()
    # Sekalian buang sesi yang sudah kedaluwarsa, supaya tabelnya tidak tumbuh terus.
    await db.execute(delete(SessionRecord).where(SessionRecord.expires_at < sekarang))
    db.add(SessionRecord(token_hash=hash_token(token), user_id=user.id, expires_at=sekarang + UMUR_SESI))
    await db.commit()
    response.set_cookie(
        NAMA_COOKIE, token,
        max_age=int(UMUR_SESI.total_seconds()),
        httponly=True, samesite="lax", path="/",
    )


async def _hapus_sesi_akun(db: AsyncSession, user_id: int, kecuali: Optional[str] = None) -> None:
    """Keluarkan akun dari semua perangkat (kecuali satu token, bila diberikan)."""
    stmt = delete(SessionRecord).where(SessionRecord.user_id == user_id)
    if kecuali:
        stmt = stmt.where(SessionRecord.token_hash != hash_token(kecuali))
    await db.execute(stmt)


# ---- Sesi pengunjung ------------------------------------------------------

def _tanda(berlaku_sampai: int, kunci: str) -> str:
    return hmac.new(kunci.encode(), f"pengunjung.{berlaku_sampai}".encode(), hashlib.sha256).hexdigest()


def kuki_pengunjung(berlaku_sampai: Optional[int] = None) -> str:
    """Isi cookie pengunjung: <detik epoch kedaluwarsa>.<HMAC dengan VISITOR_TOKEN>."""
    if berlaku_sampai is None:
        berlaku_sampai = int(time.time() + UMUR_PENGUNJUNG.total_seconds())
    return f"{berlaku_sampai}.{_tanda(berlaku_sampai, get_settings().VISITOR_TOKEN)}"


def pengunjung_dari_kuki(nilai: Optional[str]) -> Optional[SimpleNamespace]:
    """PENGUNJUNG kalau cookie-nya sah, belum kedaluwarsa, dan dibuat dengan token yang berlaku."""
    kunci = get_settings().VISITOR_TOKEN
    if not nilai or not kunci:
        return None
    try:
        sampai_teks, tanda = nilai.split(".", 1)
        sampai = int(sampai_teks)
    except ValueError:
        return None
    if sampai < time.time() or not hmac.compare_digest(tanda, _tanda(sampai, kunci)):
        return None
    return PENGUNJUNG


# ---- Dependency ------------------------------------------------------------

async def pengguna_dari_kuki(kuki: Mapping[str, str]) -> Optional[object]:
    """Akun tim dari cookie sesi, atau PENGUNJUNG dari cookie pengunjung.

    Dengan sesi database sendiri, untuk WebSocket yang tidak memakai Depends.
    """
    async with get_session_factory()() as db:
        user = await pengguna_dari_token(kuki.get(NAMA_COOKIE), db)
    return user or pengunjung_dari_kuki(kuki.get(NAMA_COOKIE_PENGUNJUNG))


async def wajib_login(request: Request, db: AsyncSession = Depends(get_db)):
    """Dependency: tolak permintaan tanpa sesi tim atau sesi pengunjung yang sah."""
    user = await pengguna_dari_token(request.cookies.get(NAMA_COOKIE), db)
    user = user or pengunjung_dari_kuki(request.cookies.get(NAMA_COOKIE_PENGUNJUNG))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Belum masuk, atau sesi sudah berakhir. Silakan masuk lagi.",
        )
    return user


async def tolak_perubahan_pengunjung(request: Request, user=Depends(wajib_login)):
    """Dependency: pengunjung hanya boleh membaca. Dijaga di sini, bukan di dashboard,
    karena tombol yang disembunyikan tidak mencegah orang memanggil API langsung."""
    if user.role == "pengunjung" and request.method not in _METODE_BACA:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pengunjung hanya bisa melihat.")
    return user


async def wajib_tim(user=Depends(wajib_login)):
    """Dependency: akun tim saja. Pengunjung tidak boleh, mis. mengunduh data insiden."""
    if user.role == "pengunjung":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pengunjung hanya bisa melihat.")
    return user


async def wajib_pengelola(user=Depends(wajib_login)):
    """Dependency: hanya pengelola."""
    if user.role != "pengelola":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Hanya pengelola yang bisa melakukan ini.")
    return user


# ---- Pembatas percobaan --------------------------------------------------------

def _kunci_percobaan(request: Request, nama: str) -> str:
    alamat = request.client.host if request.client else "-"
    return f"{alamat}|{nama}"


def _sisa_kunci(kunci: str) -> float:
    """Detik tersisa sebelum boleh mencoba lagi; 0 kalau tidak terkunci."""
    sekarang = time.monotonic()
    daftar = [t for t in _gagal.get(kunci, []) if sekarang - t < JENDELA_GAGAL]
    if daftar:
        _gagal[kunci] = daftar
    else:
        _gagal.pop(kunci, None)
    if len(daftar) >= BATAS_GAGAL:
        return max(0.0, JEDA_KUNCI - (sekarang - daftar[-1]))
    return 0.0


def _cek_terkunci(kunci: str) -> None:
    sisa = _sisa_kunci(kunci)
    if sisa:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Terlalu banyak percobaan yang gagal. Coba lagi dalam {math.ceil(sisa)} detik.",
        )


# ---- /api/auth ----------------------------------------------------------------

@router.get("/status", response_model=StatusAuth)
async def status_auth(db: AsyncSession = Depends(get_db)):
    """Halaman Login memakai ini untuk memberi petunjuk sebelum ada yang masuk."""
    ada = await db.scalar(select(func.count(UserRecord.id)).where(UserRecord.active.is_(True))) or 0
    return StatusAuth(ada_akun=ada > 0, pengunjung_aktif=bool(get_settings().VISITOR_TOKEN))


@router.post("/login", response_model=AkunResponse)
async def masuk(payload: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db)):
    username = payload.username.strip().lower()
    kunci = _kunci_percobaan(request, username)
    _cek_terkunci(kunci)

    user = (await db.execute(
        select(UserRecord).where(UserRecord.username == username)
    )).scalar_one_or_none()
    # scrypt sengaja lambat; dijalankan di thread supaya pipeline kamera, yang
    # berbagi event loop yang sama, tidak ikut tertahan.
    cocok = await asyncio.to_thread(
        cocokkan_sandi, payload.password, user.password_hash if user else _HASH_TIRUAN
    )
    if user is None or not cocok:
        _gagal.setdefault(kunci, []).append(time.monotonic())
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Email atau password salah.")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Akun ini dinonaktifkan. Hubungi pengelola.")

    _gagal.pop(kunci, None)
    await _mulai_sesi(user, response, db)
    log.info(f"👤 {user.username} masuk")
    return user


@router.post("/pengunjung", response_model=AkunResponse)
async def masuk_pengunjung(payload: TokenPengunjung, request: Request, response: Response):
    """Tukar token dari QR stand dengan cookie lihat-saja yang berlaku 12 jam."""
    kunci_token = get_settings().VISITOR_TOKEN
    if not kunci_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Akses pengunjung tidak aktif.")
    kunci = _kunci_percobaan(request, "pengunjung")
    _cek_terkunci(kunci)
    if not hmac.compare_digest(payload.token.strip(), kunci_token):
        _gagal.setdefault(kunci, []).append(time.monotonic())
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tautan pengunjung tidak berlaku. Pindai ulang QR di stand.")
    _gagal.pop(kunci, None)
    response.set_cookie(
        NAMA_COOKIE_PENGUNJUNG, kuki_pengunjung(),
        max_age=int(UMUR_PENGUNJUNG.total_seconds()),
        httponly=True, samesite="lax", path="/",
    )
    return PENGUNJUNG


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def keluar(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Keluar dari perangkat ini, sebagai tim maupun pengunjung. Tetap berhasil walau
    sesinya sudah tidak berlaku."""
    token = request.cookies.get(NAMA_COOKIE)
    if token:
        await db.execute(delete(SessionRecord).where(SessionRecord.token_hash == hash_token(token)))
        await db.commit()
    response.delete_cookie(NAMA_COOKIE, path="/")
    response.delete_cookie(NAMA_COOKIE_PENGUNJUNG, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AkunResponse)
async def akun_saya(user=Depends(wajib_login)):
    return user


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def ganti_sandi(payload: GantiSandi, request: Request,
                      user=Depends(wajib_login),
                      db: AsyncSession = Depends(get_db)):
    """Ganti kata sandi sendiri. Perangkat lain yang masih masuk ikut dikeluarkan.

    Untuk akun demo, backend/.env tetap yang menang saat backend menyala lagi.
    """
    if user.role == "pengunjung":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Pengunjung hanya bisa melihat.")
    if not await asyncio.to_thread(cocokkan_sandi, payload.password_lama, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kata sandi lama salah.")
    user.password_hash = await asyncio.to_thread(hash_sandi, payload.password_baru)
    await _hapus_sesi_akun(db, user.id, kecuali=request.cookies.get(NAMA_COOKIE))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- /api/users (khusus pengelola) ---------------------------------------------

@router_akun.get("/", response_model=list[AkunResponse])
async def daftar_akun(_=Depends(wajib_pengelola), db: AsyncSession = Depends(get_db)):
    hasil = await db.execute(select(UserRecord).order_by(UserRecord.created_at, UserRecord.id))
    return hasil.scalars().all()


@router_akun.post("/", response_model=AkunResponse, status_code=status.HTTP_201_CREATED)
async def tambah_akun(payload: AkunBaru, pengelola=Depends(wajib_pengelola),
                      db: AsyncSession = Depends(get_db)):
    ada = (await db.execute(
        select(UserRecord.id).where(UserRecord.username == payload.username)
    )).scalar_one_or_none()
    if ada is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"Nama pengguna '{payload.username}' sudah dipakai.")
    user = UserRecord(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=await asyncio.to_thread(hash_sandi, payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    log.info(f"👤 {pengelola.username} menambah akun {user.username} ({user.role})")
    return user


@router_akun.patch("/{user_id}", response_model=AkunResponse)
async def ubah_akun(user_id: int, payload: AkunUbah,
                    pengelola=Depends(wajib_pengelola),
                    db: AsyncSession = Depends(get_db)):
    user = await db.get(UserRecord, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")

    # Sistem tanpa pengelola aktif tidak bisa lagi menambah akun atau memulihkan sandi.
    berhenti_mengelola = user.role == "pengelola" and user.active and (
        payload.active is False or (payload.role is not None and payload.role != "pengelola")
    )
    if berhenti_mengelola:
        pengelola_aktif = await db.scalar(select(func.count(UserRecord.id)).where(
            UserRecord.role == "pengelola", UserRecord.active.is_(True)))
        if pengelola_aktif <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Harus ada minimal satu pengelola aktif.")

    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.role is not None:
        user.role = payload.role
    keluarkan = False
    if payload.active is not None:
        user.active = payload.active
        keluarkan = not payload.active
    if payload.password is not None:
        user.password_hash = await asyncio.to_thread(hash_sandi, payload.password)
        keluarkan = True
    if keluarkan:
        await _hapus_sesi_akun(db, user.id)
    await db.commit()
    await db.refresh(user)
    log.info(f"👤 {pengelola.username} mengubah akun {user.username}")
    return user

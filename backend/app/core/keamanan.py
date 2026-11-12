"""
keamanan.py
===========
Hash kata sandi dan token sesi, memakai pustaka standar Python saja.

- Kata sandi di-hash dengan scrypt (hashlib), lengkap dengan garam acak per akun.
  Formatnya menyimpan parameternya sendiri, jadi parameter bisa dinaikkan kelak
  tanpa membuat hash lama tidak terbaca.
- Token sesi berupa angka acak 32 byte. Yang disimpan di database hanya hash
  SHA-256-nya, jadi salinan database yang bocor tidak bisa dipakai untuk masuk.
"""

import base64
import hashlib
import hmac
import secrets

# Parameter scrypt: memori 128 * r * n = 16 MB, sekitar 50 ms per percobaan.
_N, _R, _P = 2 ** 14, 8, 1
_PANJANG_KUNCI = 32


def hash_sandi(sandi: str) -> str:
    """Hash kata sandi baru: scrypt$n$r$p$garam$turunan (base64)."""
    garam = secrets.token_bytes(16)
    turunan = hashlib.scrypt(sandi.encode(), salt=garam, n=_N, r=_R, p=_P, dklen=_PANJANG_KUNCI)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b64(garam)}${b64(turunan)}"


def cocokkan_sandi(sandi: str, tersimpan: str) -> bool:
    """True kalau kata sandi cocok dengan hash tersimpan. Hash rusak dianggap tidak cocok."""
    try:
        nama, n, r, p, garam, turunan = tersimpan.split("$")
        if nama != "scrypt":
            return False
        garam_b = base64.b64decode(garam)
        turunan_b = base64.b64decode(turunan)
        hasil = hashlib.scrypt(
            sandi.encode(), salt=garam_b, n=int(n), r=int(r), p=int(p), dklen=len(turunan_b)
        )
    except (ValueError, TypeError):
        return False
    # Perbandingan waktu-konstan, supaya lama jawaban tidak membocorkan isi hash.
    return hmac.compare_digest(hasil, turunan_b)


def token_baru() -> str:
    """Token sesi acak untuk cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Bentuk token yang disimpan di database."""
    return hashlib.sha256(token.encode()).hexdigest()

"""
test_auth.py
============
Login tim lewat akun demo, akses lihat-saja untuk pengunjung pameran, dan
perlindungan API.

Diuji lewat aplikasi yang sama dengan yang dijalankan run-backend.bat
(app.main.app), supaya yang terbukti adalah router yang benar-benar terpasang,
bukan salinannya. Lifespan diganti agar kamera dan model tidak dinyalakan, dan
database-nya SQLite sementara.
"""

import time
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

from app.api import auth
from app.core.config import get_settings
from app.core.keamanan import cocokkan_sandi, hash_sandi
from app.db.database import get_db
from app.db.models import Base

DEMO = "demo@panti.local"
SANDI_DEMO = "sandi-demo-uji-1"
TOKEN_QR = "token-qr-uji-123"


def _klien(monkeypatch, tmp_path, demo=True, token=True):
    """TestClient untuk app.main.app, dengan akun demo dan token pengunjung uji."""
    from app.main import app

    s = get_settings()
    monkeypatch.setattr(s, "DEMO_USERNAME", "  Demo@Panti.local " if demo else "")
    monkeypatch.setattr(s, "DEMO_PASSWORD", SANDI_DEMO if demo else "")
    monkeypatch.setattr(s, "DEMO_NAME", "Tim Uji")
    monkeypatch.setattr(s, "VISITOR_TOKEN", TOKEN_QR if token else "")

    # Berkas sementara dengan NullPool, bukan :memory:, karena satu uji memakai dua
    # TestClient (dua perangkat) yang masing-masing punya event loop sendiri. Tiap
    # permintaan membuka koneksinya sendiri, jadi tidak ada koneksi yang berpindah loop.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'uji.db'}", poolclass=NullPool)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def db_uji():
        async with factory() as sesi:
            yield sesi

    @asynccontextmanager
    async def tanpa_kamera(_app):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as sesi:
            await auth.siapkan_akun_demo(sesi)
        yield

    monkeypatch.setattr(app.router, "lifespan_context", tanpa_kamera)
    monkeypatch.setattr(auth, "get_session_factory", lambda: factory)
    app.dependency_overrides[get_db] = db_uji
    auth._gagal.clear()
    try:
        with TestClient(app) as c:
            c.factory = factory
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        auth._gagal.clear()


@pytest.fixture
def klien(monkeypatch, tmp_path):
    yield from _klien(monkeypatch, tmp_path)


@pytest.fixture
def klien_tanpa_demo(monkeypatch, tmp_path):
    yield from _klien(monkeypatch, tmp_path, demo=False, token=False)


def _masuk(klien, username=DEMO, password=SANDI_DEMO):
    return klien.post("/api/auth/login", json={"username": username, "password": password})


def _masuk_pengunjung(klien, token=TOKEN_QR):
    return klien.post("/api/auth/pengunjung", json={"token": token})


# ---- Kata sandi --------------------------------------------

def test_hash_sandi_tidak_menyimpan_teks_asli_dan_bisa_dicocokkan():
    h = hash_sandi("rahasia-panti")
    assert "rahasia-panti" not in h
    assert h != hash_sandi("rahasia-panti"), "garam acak per hash"
    assert cocokkan_sandi("rahasia-panti", h)
    assert not cocokkan_sandi("rahasia-lain", h)


def test_hash_rusak_dianggap_tidak_cocok():
    for rusak in ("", "abc", "scrypt$1$2$3$!!$!!", "bcrypt$x$y$z$a$b"):
        assert cocokkan_sandi("apa saja", rusak) is False


# ---- Akun demo ---------------------------------------------

def test_akun_demo_dibuat_dari_env(klien):
    assert klien.get("/api/auth/status").json() == {"ada_akun": True, "pengunjung_aktif": True}
    r = _masuk(klien, "DEMO@panti.local")
    assert r.status_code == 200, "nama pengguna tidak peka huruf besar"
    akun = klien.get("/api/auth/me").json()
    assert akun["username"] == DEMO and akun["display_name"] == "Tim Uji" and akun["role"] == "pengelola"
    assert "password" not in akun and "password_hash" not in akun


def test_sandi_demo_disamakan_dengan_env_saat_menyala(klien, monkeypatch):
    assert _masuk(klien).status_code == 200
    monkeypatch.setattr(get_settings(), "DEMO_PASSWORD", "sandi-demo-baru-2")
    _nyala_ulang(klien)
    assert klien.get("/api/auth/me").status_code == 401, "sesi dengan sandi lama ikut berakhir"
    assert _masuk(klien).status_code == 401
    assert _masuk(klien, password="sandi-demo-baru-2").status_code == 200


def _nyala_ulang(klien):
    """Jalankan lagi pembuatan akun demo, seperti saat backend dinyalakan ulang."""
    async def jalan():
        async with klien.factory() as sesi:
            await auth.siapkan_akun_demo(sesi)

    klien.portal.call(jalan)


def test_akun_demo_lama_nonaktif_saat_namanya_diganti(klien, monkeypatch):
    """Kejadian nyata: DEMO_USERNAME diganti, tetapi akun demo lama masih bisa dipakai masuk."""
    assert _masuk(klien).status_code == 200
    monkeypatch.setattr(get_settings(), "DEMO_USERNAME", "caregiver@panti.local")
    _nyala_ulang(klien)

    assert klien.get("/api/auth/me").status_code == 401, "sesi akun demo lama ikut berakhir"
    lama = _masuk(klien)
    assert lama.status_code == 403 and "dinonaktifkan" in lama.json()["detail"]
    assert _masuk(klien, "caregiver@panti.local").status_code == 200


def test_akun_lain_nonaktif_saat_backend_menyala(klien):
    _masuk(klien)
    _tambah_perawat(klien)
    assert _masuk(klien, "siti", "sandi-siti-1").status_code == 200
    _nyala_ulang(klien)
    assert _masuk(klien, "siti", "sandi-siti-1").status_code == 403
    assert _masuk(klien).status_code == 200, "akun demo sendiri tetap aktif"


def test_tanpa_akun_demo_akun_yang_ada_tidak_disentuh(klien_tanpa_demo):
    """Database lama yang punya akun, dijalankan tanpa DEMO_*: tidak ada yang dinonaktifkan."""
    from app.db.models import UserRecord

    async def isi_dan_nyala_ulang():
        async with klien_tanpa_demo.factory() as sesi:
            sesi.add(UserRecord(username="lama", display_name="Lama", role="pengelola",
                                password_hash=hash_sandi("sandi-lama-123")))
            await sesi.commit()
            assert await auth.siapkan_akun_demo(sesi) is None

    klien_tanpa_demo.portal.call(isi_dan_nyala_ulang)
    assert _masuk(klien_tanpa_demo, "lama", "sandi-lama-123").status_code == 200


def test_tanpa_akun_demo_tidak_ada_yang_bisa_masuk(klien_tanpa_demo):
    assert klien_tanpa_demo.get("/api/auth/status").json() == {"ada_akun": False, "pengunjung_aktif": False}
    assert _masuk(klien_tanpa_demo).status_code == 401


def test_tidak_ada_lagi_formulir_akun_pertama(klien_tanpa_demo):
    """Lewat tunnel pameran, siapa pun bisa membuka alamatnya. Endpoint pembuat akun
    pertama akan membiarkan orang asing menjadi pengelola saat database kosong."""
    r = klien_tanpa_demo.post("/api/auth/setup", json={
        "display_name": "Penyusup", "username": "penyusup", "password": "sandi-penyusup-1"})
    assert r.status_code in (404, 405)
    assert klien_tanpa_demo.get("/api/auth/status").json()["ada_akun"] is False


# ---- API dan video wajib login -----------------------------

@pytest.mark.parametrize("jalur", [
    "/api/alerts/", "/api/alerts/ringkasan", "/api/cameras/", "/api/settings/",
    "/api/cameras/cam-01/stream", "/api/users/", "/api/auth/me",
])
def test_api_menolak_tanpa_login(klien, jalur):
    assert klien.get(jalur).status_code == 401


def test_health_check_tetap_terbuka(klien):
    assert klien.get("/").status_code == 200


def test_masuk_dan_keluar(klien):
    salah = _masuk(klien, password="bukan-ini")
    assert salah.status_code == 401
    assert salah.json()["detail"] == "Email atau password salah."

    r = _masuk(klien)
    assert r.status_code == 200
    kuki = r.headers["set-cookie"].lower()
    assert "httponly" in kuki and "samesite=lax" in kuki
    assert klien.get("/api/alerts/").status_code == 200

    klien.post("/api/auth/logout")
    assert klien.get("/api/alerts/").status_code == 401


def test_nama_pengguna_tidak_dikenal_dijawab_sama(klien):
    """Jawaban yang sama untuk nama salah dan sandi salah, supaya daftar akun tidak bisa ditebak."""
    a = _masuk(klien, "tidak-ada@panti.local", "apa-saja-12")
    b = _masuk(klien, DEMO, "apa-saja-12")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_tebakan_beruntun_dikunci_sementara(klien):
    for _ in range(auth.BATAS_GAGAL):
        assert _masuk(klien, password="tebakan-salah").status_code == 401
    r = _masuk(klien)
    assert r.status_code == 429, "sandi yang benar pun ditolak selama terkunci"
    assert "detik" in r.json()["detail"]


# ---- Pengunjung --------------------------------------------

def test_pengunjung_dari_qr_hanya_bisa_melihat(klien):
    r = _masuk_pengunjung(klien)
    assert r.status_code == 200
    assert r.json()["role"] == "pengunjung"
    assert klien.get("/api/auth/me").json()["display_name"] == "Pengunjung"

    for jalur in ("/api/alerts/", "/api/alerts/ringkasan", "/api/cameras/", "/api/settings/"):
        assert klien.get(jalur).status_code == 200, jalur

    ditolak = [
        klien.put("/api/alerts/1/claim"),
        klien.put("/api/alerts/1/ack", json={"verdict": "jatuh"}),
        klien.post("/api/cameras/scan"),
        klien.post("/api/cameras/cam-01/simulate-fall"),
        klien.delete("/api/cameras/cam-01"),
        klien.put("/api/settings/telegram", json={"send_drills": True}),
        klien.put("/api/auth/password", json={"password_lama": "x", "password_baru": "sandi-baru-99"}),
        klien.get("/api/users/"),
    ]
    assert [r.status_code for r in ditolak] == [403] * len(ditolak)
    assert ditolak[0].json()["detail"] == "Pengunjung hanya bisa melihat."


def test_token_qr_salah_ditolak_dan_tebakannya_dibatasi(klien):
    for _ in range(auth.BATAS_GAGAL):
        r = _masuk_pengunjung(klien, "tebakan")
        assert r.status_code == 403
    assert "Pindai ulang QR" in r.json()["detail"]
    assert _masuk_pengunjung(klien).status_code == 429
    assert klien.get("/api/alerts/").status_code == 401


def test_akses_pengunjung_mati_tanpa_token(klien_tanpa_demo):
    assert _masuk_pengunjung(klien_tanpa_demo, "apa-saja").status_code == 404


def test_token_baru_membatalkan_kuki_pengunjung_lama(klien, monkeypatch):
    """Launcher membuat token baru setiap dijalankan: QR dan cookie kemarin tidak berlaku lagi."""
    assert _masuk_pengunjung(klien).status_code == 200
    monkeypatch.setattr(get_settings(), "VISITOR_TOKEN", "token-hari-berikutnya")
    assert klien.get("/api/alerts/").status_code == 401


def test_kuki_pengunjung_kedaluwarsa_atau_dipalsukan(monkeypatch):
    monkeypatch.setattr(get_settings(), "VISITOR_TOKEN", TOKEN_QR)
    sah = auth.kuki_pengunjung()
    assert auth.pengunjung_dari_kuki(sah) is auth.PENGUNJUNG
    assert auth.pengunjung_dari_kuki(auth.kuki_pengunjung(int(time.time()) - 1)) is None
    sampai, _ = sah.split(".")
    assert auth.pengunjung_dari_kuki(f"{int(sampai) + 99999}.{sah.split('.')[1]}") is None
    for rusak in ("", "abc", "123.", ".abc"):
        assert auth.pengunjung_dari_kuki(rusak) is None


def test_keluar_menghapus_akses_pengunjung(klien):
    _masuk_pengunjung(klien)
    klien.post("/api/auth/logout")
    assert klien.get("/api/alerts/").status_code == 401


def test_sesi_tim_didahulukan_dari_pengunjung(klien):
    _masuk_pengunjung(klien)
    _masuk(klien)
    assert klien.get("/api/auth/me").json()["role"] == "pengelola"
    assert klien.put("/api/settings/telegram", json={"send_drills": False}).status_code == 200


# ---- WebSocket ---------------------------------------------

def test_websocket_menolak_tanpa_login(klien):
    with pytest.raises(WebSocketDisconnect):
        with klien.websocket_connect("/ws"):
            pass


@pytest.mark.parametrize("masuk", [_masuk, _masuk_pengunjung])
def test_websocket_menerima_tim_dan_pengunjung(klien, masuk):
    assert masuk(klien).status_code == 200
    with klien.websocket_connect("/ws") as ws:
        ws.send_text("ping")
        assert ws.receive_json()["event"] == "heartbeat"


# ---- Kelola akun lewat API (belum dipakai dashboard) -------

def _tambah_perawat(klien, username="siti", password="sandi-siti-1"):
    r = klien.post("/api/users/", json={"display_name": "Siti Aminah", "username": username,
                                        "password": password, "role": "perawat"})
    assert r.status_code == 201, r.text
    return r.json()


def test_perawat_tidak_bisa_mengelola_akun(klien):
    _masuk(klien)
    _tambah_perawat(klien)
    assert klien.post("/api/users/", json={"display_name": "Siti 2", "username": "siti",
                                           "password": "sandi-lain-1"}).status_code == 409
    klien.post("/api/auth/logout")
    assert _masuk(klien, "siti", "sandi-siti-1").status_code == 200
    assert klien.get("/api/users/").status_code == 403
    assert klien.get("/api/alerts/").status_code == 200, "perawat tetap bisa memantau"


def test_akun_nonaktif_langsung_keluar_dan_tidak_bisa_masuk(klien):
    _masuk(klien)
    siti = _tambah_perawat(klien)

    # Siti masuk di perangkat lain. Tanpa `with`, supaya perangkat kedua tidak
    # menjalankan ulang startup, yang menonaktifkan semua akun selain akun demo.
    from app.main import app
    perangkat_siti = TestClient(app)
    try:
        assert _masuk(perangkat_siti, "siti", "sandi-siti-1").status_code == 200
        assert perangkat_siti.get("/api/auth/me").status_code == 200

        assert klien.patch(f"/api/users/{siti['id']}", json={"active": False}).status_code == 200
        assert perangkat_siti.get("/api/auth/me").status_code == 401
    finally:
        perangkat_siti.close()

    r = _masuk(klien, "siti", "sandi-siti-1")
    assert r.status_code == 403
    assert "dinonaktifkan" in r.json()["detail"]


def test_harus_tersisa_satu_pengelola_aktif(klien):
    akun = _masuk(klien).json()
    assert klien.patch(f"/api/users/{akun['id']}", json={"active": False}).status_code == 409
    assert klien.patch(f"/api/users/{akun['id']}", json={"role": "perawat"}).status_code == 409


def test_ganti_sandi_sendiri(klien):
    _masuk(klien)
    salah = klien.put("/api/auth/password", json={"password_lama": "keliru-sekali",
                                                  "password_baru": "sandi-baru-99"})
    assert salah.status_code == 400

    r = klien.put("/api/auth/password", json={"password_lama": SANDI_DEMO, "password_baru": "sandi-baru-99"})
    assert r.status_code == 204
    assert klien.get("/api/auth/me").status_code == 200, "perangkat yang dipakai tetap masuk"
    klien.post("/api/auth/logout")
    assert _masuk(klien).status_code == 401
    assert _masuk(klien, password="sandi-baru-99").status_code == 200

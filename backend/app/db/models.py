"""
models.py
=========
SQLAlchemy declarative models.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, LargeBinary, String
from sqlalchemy.orm import DeclarativeBase

from app.core.logging import utc_now_naive


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class CameraRecord(Base):
    """Tabel kamera yang terdaftar di sistem.

    Sumber kamera disimpan di database, bukan di environment variable, supaya
    alamat IP bisa diganti lewat dashboard tanpa menyunting kode dan tanpa
    me-restart server. Ini penting karena alamat kamera HP berubah setiap kali
    berpindah jaringan WiFi.

    Rotasi disimpan per kamera, bukan global: satu sistem bisa memakai kamera HP
    yang butuh 90 derajat bersamaan dengan webcam laptop yang tidak perlu diputar.
    """

    __tablename__ = "cameras"

    id = Column(String, primary_key=True)                      # cam-01, cam-02, ...
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)                    # "0" | http://... | rtsp://... | path file
    rotate = Column(Integer, nullable=False, default=0)        # 0, 90, 180, 270 (searah jarum jam)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now_naive)


class AppSetting(Base):
    """Pengaturan yang bisa diubah dari dashboard dan harus bertahan setelah restart.

    Disimpan sebagai pasangan kunci-nilai, bukan satu kolom per pengaturan, supaya
    menambah pengaturan baru tidak menuntut ALTER TABLE pada database yang sudah
    berisi data orang lain.

    Alasan ini ada sama dengan alasan daftar kamera tinggal di database: kalau
    pilihannya cuma hidup di memori, satu kali restart backend mengembalikannya ke
    bawaan tanpa pemberitahuan -- dan saat demo, yang tampil bukan model yang
    dikira sedang dipakai.
    """

    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class AlertRecord(Base):
    """Tabel riwayat alert fall detection."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, default="critical")
    message = Column(String, nullable=False)
    fall_duration = Column(Float, nullable=False)
    acknowledged = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)  # Status pengiriman Telegram
    # Alert ini dipicu tombol simulasi, bukan deteksi sungguhan.
    #
    # Dicatat supaya riwayat insiden tetap bisa dipercaya: sistem deteksi jatuh
    # yang bisa memunculkan alarm tanpa meninggalkan jejak membuat seluruh
    # riwayatnya kehilangan nilai sebagai bukti. Penanda ini juga muncul sebagai
    # teks di pesan Telegram dan di dashboard, supaya tidak ada yang salah baca.
    simulated = Column(Boolean, default=False, nullable=False, server_default="0")
    # Catatan perawat tentang tindakan yang diambil. Diisi saat menandai alert
    # ditangani, atau belakangan dari halaman Riwayat Insiden -- dalam keadaan
    # darurat perawat menolong dulu, baru menulis.
    caregiver_note = Column(String, nullable=True)
    # Nama ruang saat kejadian. Disalin, bukan dirujuk, karena kamera bisa diganti
    # namanya atau dihapus, sedangkan riwayat harus tetap menyebut tempat kejadiannya.
    # NULL pada alert yang dibuat sebelum kolom ini ada; pakai camera_id sebagai cadangan.
    camera_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    acknowledged_at = Column(DateTime, nullable=True)

    # ---- Penanganan oleh manusia --------------------------------------
    # Nama disalin, bukan dirujuk ke tabel users, karena riwayat harus tetap
    # menyebut siapa yang menangani walau akunnya dinonaktifkan atau diganti nama.
    # Lewat Telegram, namanya nama Telegram orang itu dengan akhiran "(Telegram)".
    #
    # Klaim ("Saya ke sana") memberi tahu perawat lain bahwa sudah ada yang menuju
    # lokasi, dan menghentikan bunyi alarm di semua dashboard.
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    # Siapa yang menandai ditangani; waktunya ada di acknowledged_at.
    acknowledged_by = Column(String, nullable=True)
    # Putusan manusia: jatuh | palsu | belum_yakin. NULL = belum dinilai.
    # Dipisah dari status penanganan: alarm bisa sudah ditangani tapi belum dinilai,
    # misalnya ditutup dari Telegram tanpa memilih putusan.
    verdict = Column(String, nullable=True)
    verdict_reason = Column(String, nullable=True)     # kode alasan, hanya untuk palsu
    verdict_by = Column(String, nullable=True)
    verdict_at = Column(DateTime, nullable=True)

    # ---- Keadaan sistem saat kejadian ----------------------------------
    # Tanpa ambang dan mode saat itu, angka alarm palsu tidak bisa ditafsirkan:
    # alarm palsu pada ambang 3 detik dan pada ambang 10 detik bukan hal yang sama.
    threshold_sec = Column(Float, nullable=True)
    detection_mode = Column(String, nullable=True)

    # ---- Telegram -------------------------------------------------------
    # mengirim | terkirim | gagal | mati (belum dikonfigurasi) | dilewati (latihan).
    # NULL pada alert lama; untuk itu kolom notified yang berlaku.
    telegram_status = Column(String, nullable=True)
    # Dipakai untuk menyunting pesan yang sama saat ada yang menekan tombol, supaya
    # satu insiden tetap satu pesan.
    telegram_message_id = Column(Integer, nullable=True)
    telegram_foto = Column(Boolean, nullable=True)     # pesan berupa foto (caption) atau teks


class AlertSnapshot(Base):
    """Foto kejadian, satu per alert.

    Tabel terpisah supaya daftar riwayat tidak ikut memuat puluhan kilobyte gambar
    per baris. Fotonya frame yang sama dengan yang dikirim ke Telegram, lengkap dengan
    kotak deteksi, dan hanya bisa dibuka lewat API yang wajib login.
    """

    __tablename__ = "alert_snapshots"

    alert_id = Column(Integer, primary_key=True)
    jpeg = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime, default=utc_now_naive)


class UserRecord(Base):
    """Akun perawat dan pengelola.

    Akun per orang, bukan satu akun bersama, karena tombol "Saya ke sana" harus
    menyebut siapa yang menuju lokasi. Kata sandi disimpan sebagai hash scrypt.
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)   # huruf kecil
    display_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="perawat")             # pengelola | perawat
    # Akun dinonaktifkan, bukan dihapus, supaya nama di riwayat tetap bermakna.
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now_naive)


class SessionRecord(Base):
    """Sesi masuk. Yang disimpan hanya hash token; tokennya sendiri ada di cookie."""

    __tablename__ = "sessions"

    token_hash = Column(String, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=utc_now_naive)
    expires_at = Column(DateTime, nullable=False)

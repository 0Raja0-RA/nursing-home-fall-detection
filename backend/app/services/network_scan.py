"""
network_scan.py
===============
Pemindai jaringan lokal untuk menemukan kamera tanpa perlu mengetik alamat IP.

Alasannya praktis: alamat IP kamera HP berubah setiap kali berpindah jaringan
WiFi (kos, kampus, hotspot). Mengisi alamat lewat dashboard sudah menghilangkan
keharusan menyunting kode, tapi pengguna masih harus membuka aplikasi kamera di
HP untuk membaca alamatnya. Pemindaian ini menghapus langkah terakhir itu.

Cara kerjanya sederhana: untuk setiap alamat di subnet /24 milik laptop, coba
buka koneksi TCP ke beberapa port yang lazim dipakai aplikasi kamera. Port yang
menerima koneksi dianggap kandidat.

Batasan yang disengaja:
    - Hanya memindai rentang IP privat (RFC 1918). Kalau laptop kebetulan
      memegang alamat publik, pemindaian dilewati.
    - Hanya /24 (254 alamat) per antarmuka, bukan seluruh /16 atau /8.
    - Hanya membuka lalu menutup koneksi TCP; tidak mengirim payload apa pun.
"""

import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.logging import get_logger
from app.models.schemas import ScanCandidate

log = get_logger("app.services.network_scan")


# Port -> (label perangkat, pola URL sumber yang siap dipakai)
PORT_PROFIL: dict[int, tuple[str, str]] = {
    8080: ("IP Webcam (Android)", "http://{ip}:8080/video"),
    4747: ("DroidCam", "http://{ip}:4747/video"),
    8081: ("IP Webcam (port alternatif)", "http://{ip}:8081/video"),
    554: ("RTSP / CCTV", "rtsp://{ip}:554/"),
}

# Jumlah koneksi paralel. 254 alamat x 4 port = 1016 percobaan; dengan 256 thread
# dan timeout 0.3 detik, satu subnet selesai dalam hitungan detik.
MAX_WORKERS = 256
TIMEOUT_PORT = 0.3


def alamat_lokal() -> list[str]:
    """Daftar alamat IPv4 milik mesin ini, tanpa loopback."""
    hasil: set[str] = set()

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            hasil.add(info[4][0])
    except OSError:
        pass

    # Cadangan: cari alamat antarmuka yang dipakai untuk keluar jaringan.
    # connect() pada UDP tidak mengirim paket apa pun, hanya memilih rute.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            hasil.add(s.getsockname()[0])
    except OSError:
        pass

    return sorted(a for a in hasil if not a.startswith("127."))


def subnet_yang_dipindai() -> list[ipaddress.IPv4Network]:
    """Subnet /24 privat yang akan dipindai, satu per antarmuka."""
    jaringan: list[ipaddress.IPv4Network] = []
    terlihat: set[str] = set()

    for alamat in alamat_lokal():
        try:
            ip = ipaddress.IPv4Address(alamat)
        except ipaddress.AddressValueError:
            continue
        if not ip.is_private or ip.is_link_local:
            continue
        net = ipaddress.IPv4Network(f"{alamat}/24", strict=False)
        if str(net) not in terlihat:
            terlihat.add(str(net))
            jaringan.append(net)

    return jaringan


def _port_terbuka(ip: str, port: int, timeout: float) -> bool:
    """True kalau ada yang menerima koneksi TCP di ip:port."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def pindai(
    ports: tuple[int, ...] | None = None,
    timeout: float = TIMEOUT_PORT,
) -> tuple[list[str], list[ScanCandidate], float]:
    """Pindai subnet lokal untuk menemukan kamera.

    Returns:
        (daftar subnet yang dipindai, kandidat yang ditemukan, durasi detik)
    """
    ports = ports or tuple(PORT_PROFIL)
    mulai = time.monotonic()

    jaringan = subnet_yang_dipindai()
    if not jaringan:
        log.info("Pemindaian dilewati: tidak ada antarmuka dengan alamat IPv4 privat.")
        return [], [], 0.0

    milik_sendiri = set(alamat_lokal())
    tugas: list[tuple[str, int]] = [
        (str(ip), port)
        for net in jaringan
        for ip in net.hosts()
        if str(ip) not in milik_sendiri
        for port in ports
    ]

    log.info(f"Memindai {len(jaringan)} subnet ({len(tugas)} percobaan koneksi)...")

    kandidat: list[ScanCandidate] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        hasil = pool.map(lambda t: _port_terbuka(t[0], t[1], timeout), tugas)
        for (ip, port), terbuka in zip(tugas, hasil):
            if not terbuka:
                continue
            label, pola = PORT_PROFIL[port]
            kandidat.append(
                ScanCandidate(ip=ip, port=port, source=pola.format(ip=ip), label=label)
            )

    # Urutkan supaya kamera HP (port 8080/4747) muncul lebih dulu daripada RTSP generik.
    prioritas = {8080: 0, 4747: 1, 8081: 2, 554: 3}
    kandidat.sort(key=lambda c: (prioritas.get(c.port, 99), socket.inet_aton(c.ip)))

    durasi = time.monotonic() - mulai
    log.info(f"Pemindaian selesai dalam {durasi:.1f}s, {len(kandidat)} kandidat ditemukan.")
    return [str(n) for n in jaringan], kandidat, durasi

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

Prefiks subnet dibaca dari antarmuka yang sebenarnya, bukan diasumsikan /24.
Jaringan kampus sering memakai subnet lebih lebar: di eepiswlan maskernya
255.255.248.0 (/21), sehingga laptop di 10.252.144.87 dan HP di 10.252.151.81
berada di satu subnet yang sama meski oktet ketiganya berbeda. Pemindai yang
mengasumsikan /24 tidak akan pernah menemukan HP itu.

Batasan yang disengaja:
    - Hanya memindai rentang IP privat (RFC 1918). Kalau laptop kebetulan
      memegang alamat publik, pemindaian dilewati.
    - Subnet yang lebih besar dari MAX_ALAMAT host dipersempit ke /24 di sekitar
      alamat sendiri, supaya pemindaian tidak berubah jadi menyapu puluhan ribu
      alamat.
    - Hanya membuka lalu menutup koneksi TCP; tidak mengirim payload apa pun.
"""

import ipaddress
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from app.core.logging import get_logger
from app.models.schemas import ScanCandidate

log = get_logger("app.services.network_scan")


# Port -> (label, pola URL sumber yang siap dipakai)
#
# Labelnya hanya tebakan dari nomor port, bukan hasil identifikasi perangkat.
# Port 8080 di jaringan kampus sering dipakai proxy atau perangkat lain, jadi
# kata-katanya sengaja tidak memastikan.
PORT_PROFIL: dict[int, tuple[str, str]] = {
    8080: ("Port 8080 — biasanya IP Webcam (Android)", "http://{ip}:8080/video"),
    4747: ("Port 4747 — biasanya DroidCam", "http://{ip}:4747/video"),
    8081: ("Port 8081 — kamera di port alternatif", "http://{ip}:8081/video"),
    554: ("Port 554 — biasanya RTSP / CCTV", "rtsp://{ip}:554/"),
}

# Jumlah koneksi paralel. Thread yang sedang menunggu connect() hampir tidak memakai
# CPU, jadi angkanya bisa besar. Dengan /21 (2046 host x 4 port = 8184 percobaan),
# 512 thread dan timeout 0.3 detik, satu sapuan selesai sekitar 5 detik.
MAX_WORKERS = 512
TIMEOUT_PORT = 0.3

# Batas jumlah alamat yang disapu per antarmuka. /21 (2046 host) masih masuk;
# subnet yang lebih lebar dipersempit ke /24 supaya pemindaian tidak berkepanjangan.
MAX_ALAMAT = 4096


def antarmuka_lokal() -> list[tuple[str, str]]:
    """Pasangan (alamat IPv4, netmask) milik mesin ini, tanpa loopback.

    Netmask dibaca dari antarmuka lewat psutil supaya prefiks subnet yang
    sebenarnya terpakai. Kalau psutil tidak ada, netmask-nya dikosongkan dan
    pemanggil memakai /24 sebagai asumsi terakhir.
    """
    hasil: dict[str, str] = {}

    try:
        import psutil

        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET and a.address and not a.address.startswith("127."):
                    hasil[a.address] = a.netmask or ""
    except Exception:  # psutil tidak terpasang atau gagal membaca antarmuka
        log.info("psutil tidak tersedia; prefiks subnet diasumsikan /24")

    if not hasil:
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                alamat = info[4][0]
                if not alamat.startswith("127."):
                    hasil.setdefault(alamat, "")
        except OSError:
            pass

        # Cadangan: cari alamat antarmuka yang dipakai untuk keluar jaringan.
        # connect() pada UDP tidak mengirim paket apa pun, hanya memilih rute.
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(0.5)
                s.connect(("8.8.8.8", 80))
                hasil.setdefault(s.getsockname()[0], "")
        except OSError:
            pass

    return sorted(hasil.items())


def alamat_lokal() -> list[str]:
    """Daftar alamat IPv4 milik mesin ini, tanpa loopback."""
    return [a for a, _ in antarmuka_lokal()]


def subnet_yang_dipindai() -> list[ipaddress.IPv4Network]:
    """Subnet privat yang akan dipindai, satu per antarmuka.

    Memakai prefiks sesungguhnya dari antarmuka. Subnet yang lebih lebar dari
    MAX_ALAMAT host dipersempit ke /24 di sekitar alamat sendiri.
    """
    jaringan: list[ipaddress.IPv4Network] = []
    terlihat: set[str] = set()

    for alamat, netmask in antarmuka_lokal():
        try:
            ip = ipaddress.IPv4Address(alamat)
        except ipaddress.AddressValueError:
            continue
        if not ip.is_private or ip.is_link_local:
            continue

        try:
            net = ipaddress.IPv4Network(f"{alamat}/{netmask}" if netmask else f"{alamat}/24",
                                        strict=False)
        except (ValueError, ipaddress.NetmaskValueError):
            net = ipaddress.IPv4Network(f"{alamat}/24", strict=False)

        if net.num_addresses > MAX_ALAMAT:
            log.info(
                f"Subnet {net} terlalu lebar ({net.num_addresses} alamat); "
                f"dipersempit ke /24 di sekitar {alamat}."
            )
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

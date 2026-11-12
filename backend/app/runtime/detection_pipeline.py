"""
detection_pipeline.py
=====================
Loop utama untuk satu kamera: mengambil frame, menjalankan inference,
mengonversi ke observasi, dan menyuapkannya ke state machine.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import DetectionResult, Observation, CameraStatus, WSMessage
from app.services.camera_service import CameraService
from app.runtime.registry import registry
from app.services.inference_service import run_inference
from app.services import klip, mode_perawatan
from app.services.episode import pencatat as pencatat_episode
from app.services.overlay import anotasi, dasar_privasi, ke_jpeg
from app.services.state_machine import FallStateMachine
from app.websocket.ws_manager import manager

log = get_logger("app.runtime.detection_pipeline")

# Makin kecil makin diutamakan. Satu orang tergeletak harus menang atas orang
# lain yang berdiri di frame yang sama; kalau tidak, yang berdiri terus mereset
# timer yang jatuh. UNCERTAIN di atas NON_TRIGGER karena orang yang
# posturnya samar bisa jadi sedang tergeletak: timer ditahan, bukan direset.
_PRIORITAS = {
    Observation.TRIGGER_POSTURE: 0,
    Observation.UNCERTAIN: 1,
    Observation.NON_TRIGGER_POSTURE: 2,
}


@dataclass
class JejakPemicu:
    """Kapan dan di mana orang yang memicu timer terakhir terlihat tergeletak.

    Hanya hidup selama timer berjalan. Dipakai supaya, di frame berisi banyak
    orang, keputusan tentang timer itu diambil dari orang yang memicunya --
    bukan dari siapa saja yang kebetulan terlihat.
    """
    waktu: float                      # time.monotonic()
    bbox: Optional[list[float]]       # None = lokasinya tidak diketahui (mis. simulasi)


# Dua kotak dianggap orang yang sama kalau irisannya mencakup setidaknya
# sekian dari kotak yang lebih kecil. Sengaja longgar: orang yang bangun dari
# lantai berkotak tegak dan hanya bagian bawahnya yang beririsan dengan kotak
# rebahnya. Kalau pencocokan ini meleset, akibatnya PERSON_LOST -- timer ditahan
# selama grace period lalu direset -- bukan alarm palsu.
_AMBANG_TUMPANG = 0.2


def _tumpang(a: list[float], b: list[float]) -> bool:
    lebar = min(a[2], b[2]) - max(a[0], b[0])
    tinggi = min(a[3], b[3]) - max(a[1], b[1])
    if lebar <= 0 or tinggi <= 0:
        return False
    terkecil = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return terkecil > 0 and (lebar * tinggi) / terkecil >= _AMBANG_TUMPANG


def pilih_observasi(
    results: list[DetectionResult],
    settings,
    jejak: Optional[JejakPemicu] = None,
    sekarang: Optional[float] = None,
) -> tuple[Observation, Optional[DetectionResult]]:
    """Gabungkan deteksi semua orang di satu frame jadi satu observasi kamera.

    Args:
        jejak: pemicu terakhir selama timer berjalan; None kalau timer nol.
        sekarang: time.monotonic() frame ini, untuk menilai umur jejak.

    Returns:
        (observasi, deteksi yang mewakilinya -- yang paling yakin di antara
        orang yang menentukan observasi itu; None kalau tidak ada siapa pun)

    Selama timer berjalan, hanya orang di lokasi pemicu yang menentukan nasib
    timer itu. Tanpa aturan ini ada dua kegagalan:
      - orang yang tergeletak tertutup selimut sementara orang lain berdiri di
        pojok: berdirinya orang lain terbaca NON_TRIGGER dan mereset timer,
        melewati grace period yang dibuat justru untuk kasus tertutup;
      - orang lain yang duduk (terbaca transitional) menahan timer selamanya.
    """
    if not results:
        return Observation.PERSON_LOST, None

    # Postur pemicu di mana pun selalu menang -- bisa jadi orang kedua yang jatuh.
    # Ambangnya dilonggarkan: orang yang tergeletak justru yang keyakinannya
    # paling rendah.
    pemicu = [r for r in results
              if r.posture.value in settings.TRIGGER_CLASSES
              and r.confidence >= settings.TRIGGER_MIN_CONF]
    if pemicu:
        return Observation.TRIGGER_POSTURE, max(pemicu, key=lambda r: r.confidence)

    relevan = results
    if jejak is not None and jejak.bbox is not None:
        relevan = [r for r in results if r.bbox and _tumpang(r.bbox, jejak.bbox)]
        if not relevan:
            # Orang yang tergeletak tidak terlihat lagi di tempatnya. Biarkan grace
            # period yang memutuskan, apa pun yang dilakukan orang lain di frame.
            return Observation.PERSON_LOST, None

    # transitional menahan timer hanya sebagai "kedipan" orang yang sama, sesaat
    # setelah ia terbaca tergeletak. Tanpa timer berjalan, ia tetap UNCERTAIN
    # seperti sebelumnya -- toh tidak ada timer yang bisa ditahan atau direset.
    berkedip = jejak is None or (
        sekarang is not None and sekarang - jejak.waktu <= settings.PAUSE_WINDOW_SEC
    )

    def observasi_satu(r: DetectionResult) -> Observation:
        if r.posture.value in settings.PAUSE_CLASSES and berkedip:
            return Observation.UNCERTAIN
        if r.confidence < settings.CONFIDENCE_THRESHOLD:
            return Observation.UNCERTAIN
        return Observation.NON_TRIGGER_POSTURE

    berpasangan = [(observasi_satu(r), r) for r in relevan]
    menang = min((o for o, _ in berpasangan), key=_PRIORITAS.get)
    wakil = max((r for o, r in berpasangan if o == menang), key=lambda r: r.confidence)
    return menang, wakil


def _catat_diagnostik(camera_id: str, detik_inferensi: float, waktu: float) -> None:
    """Rata-rata bergerak waktu inferensi dan laju analisis, untuk panel diagnostik."""
    d = registry.diagnostik.setdefault(camera_id, {"inferensi_ms": 0.0, "fps_analisis": 0.0, "terakhir": 0.0})
    d["inferensi_ms"] = round(0.8 * d["inferensi_ms"] + 0.2 * detik_inferensi * 1000, 1) if d["inferensi_ms"] \
        else round(detik_inferensi * 1000, 1)
    if d["terakhir"]:
        laju = 1.0 / max(1e-3, waktu - d["terakhir"])
        d["fps_analisis"] = round(0.8 * d["fps_analisis"] + 0.2 * laju, 1) if d["fps_analisis"] else round(laju, 1)
    d["terakhir"] = waktu


def _jpeg_dan_klip(frame, results, settings, untuk_klip: bool, privasi: str = "utuh",
                   minta_asli: bool = False) -> tuple[Optional[bytes], Optional[bytes], Optional[bytes]]:
    """JPEG beranotasi untuk stream, versi kecilnya untuk klip bila diminta, dan versi dari
    gambar asli bila video asli sedang dibuka sementara.

    Stream, foto kejadian, klip, dan Telegram memakai tampilan privasi kamera. Kotak
    deteksi digambar sekali untuk stream dan klip.
    """
    args = (results, settings.CONFIDENCE_THRESHOLD, settings.SHOW_UNCERTAIN_BOXES,
            settings.TRIGGER_MIN_CONF, tuple(settings.TRIGGER_CLASSES))
    gambar = anotasi(dasar_privasi(frame, privasi), *args)
    kecil = ke_jpeg(gambar, klip.LEBAR, klip.MUTU) if untuk_klip else None
    asli = ke_jpeg(anotasi(frame, *args)) if minta_asli and privasi != "utuh" else None
    return ke_jpeg(gambar), kecil, asli


async def camera_pipeline(camera: CameraService, fsm: FallStateMachine):
    """Detection loop untuk satu kamera."""
    settings = get_settings()
    
    # Throttle interval minimal (10 fps maksimal untuk inference)
    loop_interval = 1.0 / settings.CAMERA_FPS
    
    terakhir_log = 0.0
    jejak: Optional[JejakPemicu] = None

    while camera.is_active:
        loop_start = time.time()

        # Mode perawatan yang waktunya habis: pemantauan berjalan lagi dari nol.
        if mode_perawatan.kedaluwarsa(camera.camera_id):
            fsm.reset()
            jejak = None
            mode_perawatan.kabari_habis(camera.camera_id)
        jeda = mode_perawatan.aktif(camera.camera_id)
        tanda_jeda = {"dijeda_sampai": jeda.sampai, "dijeda_oleh": jeda.oleh} if jeda else {}

        frame = camera.get_latest_frame()
        if frame is None:
            # Frame tidak tersedia atau kamera offline
            fsm.update(Observation.OFFLINE)
            jejak = None
            pencatat_episode.amati(camera.camera_id, fsm.state, fsm.fall_duration, False)

            # Broadcast offline status
            status = CameraStatus(
                camera_id=camera.camera_id,
                is_active=False,
                fall_state=fsm.state,
                fall_duration=0.0,
                # Jam frame terakhir yang benar-benar diterima, bukan jam sekarang,
                # supaya dashboard bisa menulis sejak kapan kamera terputus.
                last_frame_at=camera.waktu_frame_terakhir,
                **tanda_jeda,
            )
            registry.latest_detection[camera.camera_id] = []
            registry.latest_status[camera.camera_id] = status
            registry.latest_jpeg[camera.camera_id] = None
            await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))

            await asyncio.sleep(0.1)
            continue

        # Mode perawatan: model tidak dijalankan, video tidak ditayangkan, dan tidak ada
        # gambar yang masuk ke penyangga klip. Kameranya tetap menyala supaya pemantauan
        # bisa langsung berjalan lagi.
        if jeda is not None:
            pencatat_episode.amati(camera.camera_id, fsm.state, fsm.fall_duration, False)
            status = CameraStatus(
                camera_id=camera.camera_id,
                is_active=True,
                fall_state=fsm.state,
                fps=camera.fps,
                last_frame_at=camera.waktu_frame_terakhir,
                **tanda_jeda,
            )
            registry.latest_detection[camera.camera_id] = []
            registry.latest_status[camera.camera_id] = status
            registry.latest_jpeg[camera.camera_id] = None
            await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))
            await asyncio.sleep(0.5)
            continue

        # Inference (dieksekusi di thread pool agar tidak memblokir event loop async)
        awal_inferensi = time.perf_counter()
        results = await asyncio.to_thread(run_inference, frame)
        _catat_diagnostik(camera.camera_id, time.perf_counter() - awal_inferensi, loop_start)
        
        # Terjemahkan semua deteksi ke satu Observation untuk FSM
        sekarang = time.monotonic()
        observation, result = pilih_observasi(results, settings, jejak, sekarang)

        # Simulasi jatuh: timpa observasi, jangan timpa apa pun yang lain.
        #
        # Hanya baris inilah yang berpura-pura. State machine di bawah tetap
        # menghitung durasi, menerapkan debounce, menghormati cooldown, dan
        # memicu alert lewat jalur yang sama persis dengan deteksi sungguhan.
        if registry.sedang_disimulasikan(camera.camera_id):
            observation = Observation.TRIGGER_POSTURE

                
        # Update FSM dengan observasi terbaru
        new_state = fsm.update(observation)
        # Catat lama tiap episode berbaring, untuk pratinjau ambang di Pengaturan.
        pencatat_episode.amati(camera.camera_id, new_state, fsm.fall_duration,
                               registry.sedang_disimulasikan(camera.camera_id))

        # Perbarui jejak orang yang memicu timer. Lokasinya hanya dicatat kalau
        # memang ada orang yang terbaca tergeletak; saat simulasi tanpa orang
        # tergeletak, lokasinya tidak diketahui dan semua orang di frame ikut dinilai.
        if observation == Observation.TRIGGER_POSTURE:
            nyata = result is not None and result.posture.value in settings.TRIGGER_CLASSES
            jejak = JejakPemicu(waktu=sekarang, bbox=result.bbox if nyata else None)
        elif fsm.fall_duration == 0:
            jejak = None

        # Log diagnosa, sekali per detik: apa yang dilihat model, diterjemahkan
        # jadi apa, dan seberapa jauh timernya. Untuk menjawab "kenapa alarm tidak
        # berbunyi" tanpa menebak.
        if time.time() - terakhir_log >= 1.0:
            terakhir_log = time.time()
            ringkas = ", ".join(f"{r.posture.value}:{r.confidence:.2f}" for r in results) or "tidak ada"
            log.info(f"[{camera.camera_id}] lihat=[{ringkas}] -> {observation.value} | "
                     f"state={new_state.value} timer={fsm.fall_duration:.1f}/"
                     f"{fsm.fall_duration_threshold:.0f}s")
        
        # Broadcast status terkini ke WebSocket
        status = CameraStatus(
            camera_id=camera.camera_id,
            is_active=camera.is_active,
            current_posture=result.posture if result else None,
            fall_state=new_state,
            fall_duration=fsm.fall_duration,
            confidence=result.confidence if result else 0.0,
            fps=camera.fps,
            last_frame_at=camera.waktu_frame_terakhir,
            simulated=registry.sedang_disimulasikan(camera.camera_id) or registry.sedang_diuji(camera.camera_id),
        )
        # Simpan untuk dipakai endpoint stream (menggambar kotak) dan GET /api/cameras/.
        registry.latest_detection[camera.camera_id] = results
        registry.latest_status[camera.camera_id] = status

        # Gambar kotak dan encode JPEG sekali di sini, bukan sekali per penonton di
        # endpoint stream. cv2.imencode itu kerja CPU yang memblokir, jadi dijalankan
        # di thread supaya event loop tetap bisa melayani REST dan WebSocket.
        # Beberapa kali per detik, versi kecilnya dititipkan ke penyangga klip.
        untuk_klip = klip.penyangga.perlu_frame(camera.camera_id, loop_start)
        privasi = getattr(camera, "privasi", "utuh")
        minta_asli = registry.asli_sampai.get(camera.camera_id, 0.0) > time.monotonic()
        jpeg, kecil, asli = await asyncio.to_thread(
            _jpeg_dan_klip, frame, results, settings, untuk_klip, privasi, minta_asli
        )
        registry.latest_jpeg_asli[camera.camera_id] = asli
        if kecil:
            klip.penyangga.tambah(camera.camera_id, loop_start, kecil)
        registry.latest_jpeg[camera.camera_id] = jpeg
        registry.frame_seq[camera.camera_id] = registry.frame_seq.get(camera.camera_id, 0) + 1
        await manager.broadcast(WSMessage(event="status_update", data=status.model_dump()))
        
        # Pastikan tidak melahap 100% CPU, tidur sisa waktunya
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, loop_interval - elapsed)
        await asyncio.sleep(sleep_time)

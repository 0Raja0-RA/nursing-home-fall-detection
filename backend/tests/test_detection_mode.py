"""
test_detection_mode.py
======================
Uji untuk pemilihan model detektor (bbox / pose) dari halaman Pengaturan:
kinematika pose, arti confidence di mode pose, penyimpanan pilihan ke database,
dan efek pergantian mode terhadap state machine yang sedang berjalan.

Tidak memuat model YOLO sungguhan dan tidak membuka kamera, jadi bisa dijalankan
di mana saja.
"""

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api import settings as api_settings
from app.db.models import Base
from app.db.repository import SettingRepository
from app.models.schemas import ModeUpdate, PostureClass, ThresholdUpdate
from app.services import inference_service
from app.services.inference_service import (
    MODE_BBOX,
    MODE_POSE,
    _postur_dari_pose,
    calculate_spine_angle,
)
from app.services.state_machine import FallState, FallStateMachine, Observation


def kpts(bahu_xy, pinggul_xy, conf=0.9) -> np.ndarray:
    """Rangka 17 keypoint COCO, hanya bahu (5,6) dan pinggul (11,12) yang diisi."""
    a = np.zeros((17, 3), dtype=float)
    for i in (5, 6):
        a[i] = [bahu_xy[0], bahu_xy[1], conf]
    for i in (11, 12):
        a[i] = [pinggul_xy[0], pinggul_xy[1], conf]
    return a


# ---- Kinematika --------------------------------------------

def test_sudut_tulang_belakang_tegak_dan_rebah():
    # Bahu tepat di atas pinggul -> 90 derajat (tegak).
    tegak = calculate_spine_angle(kpts((100, 100), (100, 200)))
    assert tegak == pytest.approx(90.0)

    # Bahu dan pinggul sejajar mendatar -> 0 derajat (rebah).
    rebah = calculate_spine_angle(kpts((100, 150), (200, 150)))
    assert rebah == pytest.approx(0.0)


def test_orang_berdiri_terbaca_normal():
    # Kotak lebih tinggi daripada lebar, skeleton tegak.
    postur, mutu = _postur_dari_pose(kpts((100, 100), (100, 200)), aspect_ratio=0.5)
    assert postur == PostureClass.NORMAL
    assert mutu == pytest.approx(0.9)


def test_orang_tergeletak_terbaca_lying():
    postur, mutu = _postur_dari_pose(kpts((100, 150), (200, 150)), aspect_ratio=1.8)
    assert postur == PostureClass.LYING_ON_GROUND
    assert mutu == pytest.approx(0.9)


def test_pose_setengah_bangkit_terbaca_transitional():
    # Kemiringan 45 derajat: di bawah ambang transisi (60), di atas ambang rebah.
    postur, _ = _postur_dari_pose(kpts((100, 100), (200, 200)), aspect_ratio=0.9)
    assert postur == PostureClass.TRANSITIONAL


# ---- Arti confidence di mode pose --------------------------

def test_sendi_tak_terbaca_dilaporkan_tidak_yakin():
    """Tebakan dari bentuk kotak tidak boleh menyamar sebagai pembacaan pasti.

    Di mode pose, confidence kotak berarti "ini memang orang" dan hampir selalu
    tinggi -- termasuk untuk orang yang berdiri jelas. Kalau angka itu yang
    dilaporkan, cabang UNCERTAIN di pipeline tidak akan pernah menyala, dan
    sistem memperlakukan tebakan kasar seolah-olah pembacaan yang meyakinkan.
    """
    from app.core.config import get_settings

    _, mutu = _postur_dari_pose(
        kpts((100, 150), (200, 150), conf=0.05), aspect_ratio=1.8
    )
    assert mutu < get_settings().CONFIDENCE_THRESHOLD, (
        "sendi yang tidak terbaca harus jatuh ke UNCERTAIN, bukan dianggap pasti"
    )


def test_mutu_diambil_dari_sendi_terlemah():
    """Pinggul yang kabur membuat sudut tulang belakang tidak bisa dipercaya,
    sekalipun bahunya terbaca jelas."""
    a = kpts((100, 150), (200, 150), conf=0.95)
    a[11][2] = a[12][2] = 0.30          # pinggul remang-remang
    _, mutu = _postur_dari_pose(a, aspect_ratio=1.8)
    assert mutu == pytest.approx(0.30)


# ---- Pemilihan mode ----------------------------------------

def test_mode_tidak_dikenal_ditolak():
    with pytest.raises(ValueError):
        inference_service.set_mode("segmentation")


def test_ganti_mode_tidak_memuat_model_apa_pun():
    """set_mode hanya menandai pilihan; modelnya dimuat malas saat frame pertama,
    supaya permintaan dari dashboard tidak menggantung menunggu berkas .pt."""
    inference_service.unload_model()
    try:
        inference_service.set_mode(MODE_BBOX)
        assert inference_service.mode_aktif() == MODE_BBOX
        inference_service.set_mode(MODE_POSE)
        assert inference_service.mode_aktif() == MODE_POSE
        assert inference_service._models == {}, "tidak ada model yang boleh dimuat"
    finally:
        inference_service.unload_model()


# ---- Penyimpanan ke database -------------------------------

@pytest_asyncio.fixture
async def sesi() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_pengaturan_tersimpan_dan_terbaca_ulang(sesi: AsyncSession):
    repo = SettingRepository(sesi)
    assert await repo.ambil("detection_mode") is None

    await repo.simpan("detection_mode", MODE_BBOX)
    assert await repo.ambil("detection_mode") == MODE_BBOX

    # Menyimpan ulang kunci yang sama menimpa, bukan menambah baris.
    await repo.simpan("detection_mode", MODE_POSE)
    assert await repo.ambil("detection_mode") == MODE_POSE
    assert await repo.semua() == {"detection_mode": MODE_POSE}


@pytest.mark.asyncio
async def test_mode_bertahan_setelah_restart(sesi: AsyncSession):
    """Inilah alasan pilihannya disimpan di database, bukan hanya di memori:
    tanpa ini, satu kali restart mengembalikannya ke bawaan tanpa pemberitahuan."""
    await SettingRepository(sesi).simpan("detection_mode", MODE_BBOX)

    inference_service.unload_model()        # tiru proses yang baru mulai
    try:
        await api_settings.muat_dari_db(sesi)
        assert inference_service.mode_aktif() == MODE_BBOX
    finally:
        inference_service.unload_model()


@pytest.mark.asyncio
async def test_threshold_bertahan_setelah_restart(sesi: AsyncSession):
    from app.core.config import get_settings

    semula = get_settings().FALL_DURATION_THRESHOLD
    try:
        await SettingRepository(sesi).simpan("fall_duration_threshold", "7.5")
        await api_settings.muat_dari_db(sesi)
        assert get_settings().FALL_DURATION_THRESHOLD == pytest.approx(7.5)
    finally:
        get_settings().FALL_DURATION_THRESHOLD = semula


# ---- Efek ke state machine yang sedang berjalan ------------

@pytest.mark.asyncio
async def test_ganti_mode_mereset_timer_yang_sedang_berjalan(sesi: AsyncSession):
    """Timer yang separuh terkumpul di bawah satu model lalu dinilai model lain
    tidak bermakna -- dan alarm yang lahir darinya tidak bisa dipertanggung-
    jawabkan ke model mana pun."""
    from app.runtime.registry import registry

    fsm = FallStateMachine(camera_id="cam-uji", fall_duration_threshold=10.0,
                           possible_fall_threshold=0.0)
    fsm.update(Observation.TRIGGER_POSTURE)
    fsm.update(Observation.TRIGGER_POSTURE)
    assert fsm.state == FallState.POSSIBLE_FALL

    registry.state_machines["cam-uji"] = fsm
    try:
        await api_settings.update_mode(ModeUpdate(detection_mode=MODE_BBOX), sesi)
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0
    finally:
        registry.state_machines.pop("cam-uji", None)
        inference_service.unload_model()


@pytest.mark.asyncio
async def test_threshold_baru_diteruskan_ke_kamera_yang_menyala(sesi: AsyncSession):
    """Tanpa penerusan ini, kamera yang sudah berjalan tetap memakai angka lama
    sampai di-restart: pengaturannya terlihat tersimpan padahal tidak berefek."""
    from app.core.config import get_settings
    from app.runtime.registry import registry

    semula = get_settings().FALL_DURATION_THRESHOLD
    fsm = FallStateMachine(camera_id="cam-uji", fall_duration_threshold=10.0)
    registry.state_machines["cam-uji"] = fsm
    try:
        await api_settings.update_threshold(
            ThresholdUpdate(fall_duration_threshold=4.0), sesi
        )
        assert fsm.fall_duration_threshold == pytest.approx(4.0)
        assert await SettingRepository(sesi).ambil("fall_duration_threshold") == "4.0"
    finally:
        registry.state_machines.pop("cam-uji", None)
        get_settings().FALL_DURATION_THRESHOLD = semula


# ---- Skeleton di stream ------------------------------------

def test_skeleton_tergambar_di_mode_pose_dan_sendi_samar_dilewati():
    """Mode pose harus menampilkan skeleton, bukan hanya kotak -- tapi sendi
    yang tidak terbaca tidak boleh digambar, karena koordinatnya tebakan dan
    membuat skeleton mencuat ke tempat yang tidak masuk akal."""
    from app.models.schemas import DetectionResult
    from app.services.overlay import gambar_deteksi

    k = kpts((100, 100), (100, 200), conf=0.9).tolist()
    k[15] = [40.0, 280.0, 0.05]      # pergelangan kaki kiri: tidak terbaca

    hasil = DetectionResult(posture=PostureClass.NORMAL, confidence=0.9,
                            bbox=[60, 60, 160, 300], keypoints=k)
    frame = gambar_deteksi(np.zeros((320, 320, 3), np.uint8), hasil, ambang=0.5)

    assert frame[150, 100].any(), "garis bahu-pinggul harus tergambar"
    assert not frame[280, 40].any(), "sendi berkeyakinan rendah tidak boleh digambar"


def test_mode_bbox_tetap_hanya_kotak():
    from app.models.schemas import DetectionResult
    from app.services.overlay import gambar_deteksi

    hasil = DetectionResult(posture=PostureClass.NORMAL, confidence=0.9,
                            bbox=[60, 60, 160, 300])
    frame = gambar_deteksi(np.zeros((320, 320, 3), np.uint8), hasil, ambang=0.5)
    assert not frame[150, 110].any(), "tanpa keypoint, bagian dalam kotak harus kosong"


# ---- Saringan benda yang bukan orang -----------------------

def test_kotak_sampah_dibuang_sebelum_menentukan_keputusan(monkeypatch):
    """Colokan (kecil) dan kursi (yakinnya rendah) tidak boleh lolos sebagai orang.

    Kalau lolos, mereka dibaca UNCERTAIN dan menahan timer terus-menerus.
    """
    import types

    class Tensor:
        def __init__(self, v): self.v = v
        def item(self): return self.v
        def tolist(self): return self.v

    # (conf, kelas, kotak): orang jelas, kursi yakin rendah, colokan kecil
    data = [
        (0.90, 0, [100, 50, 300, 450]),
        (0.12, 0, [350, 200, 500, 450]),
        (0.80, 0, [10, 10, 30, 30]),
    ]

    class Boxes:
        conf = [Tensor(c) for c, _, _ in data]
        cls = [Tensor(k) for _, k, _ in data]
        xyxy = [Tensor(b) for _, _, b in data]
        def __len__(self): return len(data)

    class Model:
        def __call__(self, *a, **k):
            return [types.SimpleNamespace(boxes=Boxes())]

    inference_service.unload_model()
    inference_service._models[MODE_BBOX] = Model()
    inference_service.set_mode(MODE_BBOX)
    try:
        hasil = inference_service.run_inference(np.zeros((480, 640, 3), np.uint8))
        assert len(hasil) == 1
        assert hasil[0].confidence == pytest.approx(0.90)
    finally:
        inference_service.unload_model()


def test_mode_pose_membuang_kotak_tanpa_sendi_terbaca():
    """Kursi bisa lolos sebagai kotak 'orang', tapi sendinya tidak terbaca."""
    import types
    import torch

    class Tensor:
        def __init__(self, v): self.v = v
        def item(self): return self.v
        def tolist(self): return self.v

    orang = np.zeros((17, 3)); orang[:, 2] = 0.9           # 17 sendi jelas
    kursi = np.zeros((17, 3)); kursi[:, 2] = 0.05          # tak satu pun terbaca
    kursi[0, 2] = 0.9                                      # satu saja kebetulan yakin

    class Kp:
        data = [torch.tensor(orang), torch.tensor(kursi)]

    class Boxes:
        conf = [Tensor(0.9), Tensor(0.8)]
        cls = [Tensor(0), Tensor(0)]
        xyxy = [Tensor([100, 50, 300, 450]), Tensor([350, 200, 550, 450])]
        def __len__(self): return 2

    class Model:
        def __call__(self, *a, **k):
            return [types.SimpleNamespace(boxes=Boxes(), keypoints=Kp())]

    inference_service.unload_model()
    inference_service._models[MODE_POSE] = Model()
    inference_service.set_mode(MODE_POSE)
    try:
        hasil = inference_service.run_inference(np.zeros((480, 640, 3), np.uint8))
        assert len(hasil) == 1
        assert hasil[0].bbox[0] == 100
    finally:
        inference_service.unload_model()


def test_kotak_ragu_bisa_disembunyikan_dari_stream():
    from app.models.schemas import DetectionResult
    from app.services.overlay import gambar_deteksi

    ragu = DetectionResult(posture=PostureClass.NORMAL, confidence=0.2, bbox=[60, 60, 160, 300])
    kosong = gambar_deteksi(np.zeros((320, 320, 3), np.uint8), ragu, 0.5, tampilkan_ragu=False)
    assert not kosong.any(), "kotak ragu tidak boleh tergambar"

    ada = gambar_deteksi(np.zeros((320, 320, 3), np.uint8), ragu, 0.5, tampilkan_ragu=True)
    assert ada.any()


def test_berbaring_dengan_sendi_kabur_tetap_dilaporkan_yakin():
    """Bahu dan pinggul orang tergeletak sulit terbaca, tapi kotaknya jelas.

    Kalau yang dilaporkan keyakinan sendi (~0), postur pemicu selalu UNCERTAIN
    dan alarm tidak pernah bisa berbunyi.
    """
    import types
    import torch

    class Tensor:
        def __init__(self, v): self.v = v
        def item(self): return self.v
        def tolist(self): return self.v

    k = np.zeros((17, 3))
    k[[0, 1, 2, 3], 2] = 0.5        # kepala terbaca (cukup untuk lolos saringan)
    k[[5, 6, 11, 12], 2] = 0.03     # bahu dan pinggul kabur

    class Kp:
        data = [torch.tensor(k)]

    class Boxes:
        conf = [Tensor(0.6)]
        cls = [Tensor(0)]
        xyxy = [Tensor([50, 300, 550, 400])]    # melebar: rasio 5
        def __len__(self): return 1

    class Model:
        def __call__(self, *a, **kw):
            return [types.SimpleNamespace(boxes=Boxes(), keypoints=Kp())]

    inference_service.unload_model()
    inference_service._models[MODE_POSE] = Model()
    inference_service.set_mode(MODE_POSE)
    try:
        (hasil,) = inference_service.run_inference(np.zeros((480, 640, 3), np.uint8))
        assert hasil.posture == PostureClass.LYING_ON_GROUND
        assert hasil.confidence == pytest.approx(0.6)
    finally:
        inference_service.unload_model()


# ---- Orang duduk tidak boleh terbaca berbaring --------------

def test_duduk_kaki_lurus_dengan_sendi_kabur_bukan_berbaring():
    """Kotak melebar (kaki lurus ke depan) dan bahu/pinggul tak terbaca.

    Dulu rasio > 1,3 saja sudah dibaca berbaring, sehingga orang duduk memicu timer.
    """
    a = np.zeros((17, 3))
    a[0] = [100, 100, 0.8]       # hidung, jelas
    a[11] = a[12] = [100, 200, 0.2]   # pinggul remang-remang (di bawah ambang mutu)
    a[5] = a[6] = [100, 140, 0.2]
    # Kepala tegak 100 piksel di atas pinggul -> bukan berbaring.
    postur, _ = _postur_dari_pose(a, aspect_ratio=1.5)
    assert postur != PostureClass.LYING_ON_GROUND


def test_hanya_kotak_rasio_sedang_tidak_cukup_untuk_berbaring():
    a = np.zeros((17, 3))
    postur, _ = _postur_dari_pose(a, aspect_ratio=1.5)
    assert postur != PostureClass.LYING_ON_GROUND


def test_kotak_sangat_pipih_tanpa_sendi_tetap_dibaca_berbaring():
    a = np.zeros((17, 3))
    postur, _ = _postur_dari_pose(a, aspect_ratio=2.5)
    assert postur == PostureClass.LYING_ON_GROUND


def test_kepala_sejajar_pinggul_dibaca_berbaring():
    a = np.zeros((17, 3))
    a[0] = [300, 200, 0.8]            # kepala di samping
    a[11] = a[12] = [100, 205, 0.5]   # pinggul, hampir sejajar
    a[5] = a[6] = [100, 205, 0.1]     # bahu tak terbaca
    postur, _ = _postur_dari_pose(a, aspect_ratio=2.0)
    assert postur == PostureClass.LYING_ON_GROUND

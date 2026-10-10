"""
test_detection_pipeline.py
==========================
Unit tests untuk detection pipeline.
"""

import asyncio

import numpy as np
from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import FallState, PostureClass, DetectionResult
from app.runtime.detection_pipeline import camera_pipeline
from app.services.state_machine import FallStateMachine
from app.services.camera_service import CameraService


def _make_camera(camera_id: str = "cam-test") -> MagicMock:
    """Buat mock kamera.

    MagicMock(spec=CameraService) hanya mengenali atribut KELAS. camera_id dan is_active
    ditetapkan di __init__, jadi harus di-set eksplisit supaya tersedia untuk pipeline.
    """
    cam = MagicMock(spec=CameraService)
    cam.camera_id = camera_id
    cam.is_active = True
    cam.fps = 0.0
    return cam


@pytest.mark.asyncio
async def test_camera_pipeline_offline():
    """Test saat frame = None, observasi harus OFFLINE."""
    # Mock camera yang me-return None dan aktif sebentar saja
    mock_camera = _make_camera()
    mock_camera.get_latest_frame.return_value = None
    
    fsm = FallStateMachine(camera_id="cam-test")
    
    # Fungsi pembantu untuk mematikan loop
    async def stop_camera():
        await asyncio.sleep(0.15)
        mock_camera.is_active = False

    # Jalankan pipeline dan stop_camera bersamaan
    await asyncio.gather(
        camera_pipeline(mock_camera, fsm),
        stop_camera()
    )
    
    assert fsm.state == FallState.UNKNOWN


@pytest.mark.asyncio
@patch("app.runtime.detection_pipeline.run_inference")
async def test_camera_pipeline_trigger(mock_run_inference):
    """Test saat mendeteksi postur pemicu."""
    mock_camera = _make_camera()
    # Frame harus array sungguhan: pipeline menggambar kotak lalu meng-encode JPEG
    # dari frame ini, jadi string dummy tidak lagi cukup.
    mock_camera.get_latest_frame.return_value = np.zeros((48, 64, 3), dtype=np.uint8)
    
    # Mock inference result
    mock_run_inference.return_value = [DetectionResult(
        posture=PostureClass.LYING_ON_GROUND,
        confidence=0.9
    )]
    
    fsm = FallStateMachine(
        camera_id="cam-test", 
        possible_fall_threshold=0.01  # Langsung pemicu
    )
    
    async def stop_camera():
        await asyncio.sleep(0.2)
        mock_camera.is_active = False

    await asyncio.gather(
        camera_pipeline(mock_camera, fsm),
        stop_camera()
    )
    
    assert fsm.state == FallState.POSSIBLE_FALL


# ---- Beberapa orang dalam satu frame -----------------------

def _settings():
    from app.core.config import get_settings
    return get_settings()


def test_orang_berbaring_menang_atas_orang_berdiri():
    """Satu orang tergeletak harus memicu timer walau orang lain berdiri lebih jelas.

    Dulu hanya kotak ber-confidence tertinggi yang dipakai, jadi orang berdiri
    menutupi orang yang jatuh.
    """
    from app.models.schemas import Observation
    from app.runtime.detection_pipeline import pilih_observasi

    berdiri = DetectionResult(posture=PostureClass.NORMAL, confidence=0.95)
    jatuh = DetectionResult(posture=PostureClass.LYING_ON_GROUND, confidence=0.6)

    obs, wakil = pilih_observasi([berdiri, jatuh], _settings())
    assert obs == Observation.TRIGGER_POSTURE
    assert wakil is jatuh


def test_orang_samar_menahan_timer_bukan_mereset():
    from app.models.schemas import Observation
    from app.runtime.detection_pipeline import pilih_observasi

    berdiri = DetectionResult(posture=PostureClass.NORMAL, confidence=0.95)
    samar = DetectionResult(posture=PostureClass.LYING_ON_GROUND, confidence=0.1)

    obs, _ = pilih_observasi([berdiri, samar], _settings())
    assert obs == Observation.UNCERTAIN


def test_semua_berdiri_dan_tanpa_siapa_pun():
    from app.models.schemas import Observation
    from app.runtime.detection_pipeline import pilih_observasi

    a = DetectionResult(posture=PostureClass.NORMAL, confidence=0.9)
    assert pilih_observasi([a], _settings())[0] == Observation.NON_TRIGGER_POSTURE
    assert pilih_observasi([], _settings()) == (Observation.PERSON_LOST, None)


def test_berbaring_berkeyakinan_rendah_tetap_memicu():
    """Orang tergeletak justru yang keyakinannya paling rendah.

    Di bawah CONFIDENCE_THRESHOLD tapi di atas TRIGGER_MIN_CONF, ia harus
    menjalankan timer, bukan ditahan sebagai UNCERTAIN.
    """
    from app.models.schemas import Observation
    from app.runtime.detection_pipeline import pilih_observasi

    s = _settings()
    conf = (s.TRIGGER_MIN_CONF + s.CONFIDENCE_THRESHOLD) / 2
    berbaring = DetectionResult(posture=PostureClass.LYING_ON_GROUND, confidence=conf)
    berdiri = DetectionResult(posture=PostureClass.NORMAL, confidence=conf)

    assert pilih_observasi([berbaring], s)[0] == Observation.TRIGGER_POSTURE
    # Postur lain dengan keyakinan sama tetap dianggap ragu.
    assert pilih_observasi([berdiri], s)[0] == Observation.UNCERTAIN


def test_transitional_menahan_timer_bukan_mereset():
    """Orang tergeletak sering terbaca transitional di sela lying_on_ground."""
    from app.models.schemas import Observation
    from app.runtime.detection_pipeline import pilih_observasi

    trans = DetectionResult(posture=PostureClass.TRANSITIONAL, confidence=0.9)
    berdiri = DetectionResult(posture=PostureClass.NORMAL, confidence=0.9)
    assert pilih_observasi([trans], _settings())[0] == Observation.UNCERTAIN
    assert pilih_observasi([berdiri], _settings())[0] == Observation.NON_TRIGGER_POSTURE


# ---- Jalur lengkap: berbaring cukup lama -> alarm ----------

async def _jalankan(deteksi_per_frame, durasi_uji, ambang_detik=1.0, **kw_fsm):
    """Jalankan pipeline dengan deteksi tiruan, kembalikan (alarm_berbunyi, fsm)."""
    from itertools import cycle

    alarm = []
    cam = _make_camera()
    cam.get_latest_frame.return_value = np.zeros((48, 64, 3), dtype=np.uint8)
    urutan = cycle(deteksi_per_frame)

    fsm = FallStateMachine(
        camera_id="cam-test", fall_duration_threshold=ambang_detik,
        possible_fall_threshold=0.1, on_confirmed_fall=lambda c, d: alarm.append(d),
        **kw_fsm,
    )

    async def stop():
        await asyncio.sleep(durasi_uji)
        cam.is_active = False

    with patch("app.runtime.detection_pipeline.run_inference",
               side_effect=lambda f: next(urutan)):
        await asyncio.gather(camera_pipeline(cam, fsm), stop())
    return alarm, fsm


def _lying(conf):
    return [DetectionResult(posture=PostureClass.LYING_ON_GROUND, confidence=conf,
                            bbox=[5, 30, 60, 46])]


@pytest.mark.asyncio
@pytest.mark.parametrize("conf", [0.9, 0.4, 0.3])
async def test_berbaring_terus_menerus_memicu_alarm(conf):
    """Berapa pun keyakinannya (di atas TRIGGER_MIN_CONF), berbaring cukup lama = alarm."""
    alarm, fsm = await _jalankan([_lying(conf)], durasi_uji=2.0)
    assert len(alarm) == 1, f"alarm tidak berbunyi (state={fsm.state}, durasi={fsm.fall_duration:.1f})"


@pytest.mark.asyncio
async def test_berbaring_dengan_dua_orang_berdiri_memicu_alarm():
    berdiri = DetectionResult(posture=PostureClass.NORMAL, confidence=0.95, bbox=[1, 1, 20, 46])
    alarm, _ = await _jalankan([_lying(0.3) + [berdiri]], durasi_uji=2.0)
    assert len(alarm) == 1


@pytest.mark.asyncio
async def test_postur_berkedip_tidak_membatalkan_alarm():
    """Model sering menukar lying dan transitional dari frame ke frame."""
    trans = [DetectionResult(posture=PostureClass.TRANSITIONAL, confidence=0.8, bbox=[5, 30, 60, 46])]
    # Enam frame transitional berturut-turut, lebih panjang dari debounce (5).
    alarm, _ = await _jalankan([_lying(0.8)] * 2 + [trans] * 6, durasi_uji=3.0, ambang_detik=0.4)
    assert len(alarm) == 1

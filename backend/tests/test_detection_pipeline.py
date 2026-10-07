"""
test_detection_pipeline.py
==========================
Unit tests untuk detection pipeline.
"""

import asyncio
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
    mock_camera.get_latest_frame.return_value = "dummy_frame"
    
    # Mock inference result
    mock_run_inference.return_value = DetectionResult(
        posture=PostureClass.LYING_ON_GROUND,
        confidence=0.9
    )
    
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

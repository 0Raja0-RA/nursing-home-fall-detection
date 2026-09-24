"""
test_state_machine.py
=====================
Unit tests untuk FallStateMachine.
"""

import time
from unittest.mock import MagicMock

import pytest

from app.models.schemas import FallState, PostureClass
from app.services.state_machine import FallStateMachine


class TestFallStateMachine:
    """Test suite untuk state machine fall detection."""

    def test_initial_state_is_monitoring(self):
        """State awal harus MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0

    def test_normal_stays_monitoring(self):
        """Postur normal tidak mengubah state dari MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(PostureClass.NORMAL)
        assert fsm.state == FallState.MONITORING

    def test_transitional_stays_monitoring(self):
        """Postur transitional tidak mengubah state dari MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(PostureClass.TRANSITIONAL)
        assert fsm.state == FallState.MONITORING

    def test_lying_triggers_possible_fall(self):
        """Postur lying_on_ground pertama kali harus pindah ke POSSIBLE_FALL."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(PostureClass.LYING_ON_GROUND)
        assert fsm.state == FallState.POSSIBLE_FALL

    def test_lying_then_normal_resets(self):
        """Jika postur berubah dari lying ke normal, reset ke MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(PostureClass.LYING_ON_GROUND)
        assert fsm.state == FallState.POSSIBLE_FALL
        fsm.update(PostureClass.NORMAL)
        assert fsm.state == FallState.MONITORING

    def test_confirmed_fall_with_short_threshold(self):
        """Fall di-confirm jika durasi melebihi threshold."""
        callback = MagicMock()
        fsm = FallStateMachine(
            camera_id="cam-1",
            fall_duration_threshold=0.1,  # 100ms untuk test cepat
            on_confirmed_fall=callback,
        )

        fsm.update(PostureClass.LYING_ON_GROUND)
        assert fsm.state == FallState.POSSIBLE_FALL

        time.sleep(0.15)  # Tunggu melebihi threshold
        fsm.update(PostureClass.LYING_ON_GROUND)
        assert fsm.state == FallState.CONFIRMED_FALL
        callback.assert_called_once()

    def test_reset_from_confirmed(self):
        """Reset dari CONFIRMED_FALL kembali ke MONITORING."""
        fsm = FallStateMachine(
            camera_id="cam-1",
            fall_duration_threshold=0.05,
        )
        fsm.update(PostureClass.LYING_ON_GROUND)
        time.sleep(0.1)
        fsm.update(PostureClass.LYING_ON_GROUND)
        assert fsm.state == FallState.CONFIRMED_FALL

        fsm.reset()
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0

    def test_update_thresholds(self):
        """Threshold bisa diupdate tanpa reset state."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update_thresholds(fall_duration=20.0, possible_fall=5.0)
        assert fsm.fall_duration_threshold == 20.0
        assert fsm.possible_fall_threshold == 5.0

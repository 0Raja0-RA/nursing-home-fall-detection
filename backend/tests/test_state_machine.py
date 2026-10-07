"""
test_state_machine.py
=====================
Unit tests untuk FallStateMachine.
"""

import time
from unittest.mock import MagicMock

import pytest

from app.models.schemas import FallState, Observation
from app.services.state_machine import FallStateMachine


class TestFallStateMachine:
    """Test suite untuk state machine fall detection."""

    def test_initial_state_is_monitoring(self):
        """State awal harus MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0

    def test_offline_sets_unknown(self):
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(Observation.OFFLINE)
        assert fsm.state == FallState.UNKNOWN

    def test_normal_stays_monitoring(self):
        """Postur normal tidak mengubah state dari MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(Observation.NON_TRIGGER_POSTURE)
        assert fsm.state == FallState.MONITORING

    def test_uncertain_stays_monitoring(self):
        """Postur uncertain tidak mengubah state dari MONITORING."""
        fsm = FallStateMachine(camera_id="cam-1")
        fsm.update(Observation.UNCERTAIN)
        assert fsm.state == FallState.MONITORING

    def test_lying_triggers_possible_fall_after_threshold(self):
        """Postur pemicu transisi ke POSSIBLE_FALL setelah melebihi possible_fall_threshold."""
        fsm = FallStateMachine(camera_id="cam-1", possible_fall_threshold=0.1)
        fsm.update(Observation.TRIGGER_POSTURE)
        # Kurang dari threshold, masih MONITORING
        assert fsm.state == FallState.MONITORING
        
        time.sleep(0.15)
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL

    def test_anti_flicker_debounce(self):
        """Satu-dua frame meleset tidak langsung mereset timer."""
        fsm = FallStateMachine(camera_id="cam-1", possible_fall_threshold=0.01, debounce_frames=3)
        fsm.update(Observation.TRIGGER_POSTURE)
        time.sleep(0.05)
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        # Frame meleset 1
        fsm.update(Observation.NON_TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        # Frame meleset 2
        fsm.update(Observation.NON_TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        # Frame meleset 3 -> Reset!
        fsm.update(Observation.NON_TRIGGER_POSTURE)
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0

    def test_uncertain_pauses_timer(self):
        """Uncertain menghentikan timer tapi tidak mereset."""
        fsm = FallStateMachine(camera_id="cam-1", possible_fall_threshold=0.05, debounce_frames=3)
        fsm.update(Observation.TRIGGER_POSTURE)
        time.sleep(0.1)
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        fsm.update(Observation.UNCERTAIN)
        
        duration_paused = fsm.fall_duration
        time.sleep(0.1)
        fsm.update(Observation.UNCERTAIN)
        # Durasi tidak bertambah
        assert fsm.fall_duration == duration_paused
        assert fsm.state == FallState.POSSIBLE_FALL

    def test_person_lost_grace_period(self):
        """Orang hilang ditunggu selama grace period."""
        fsm = FallStateMachine(camera_id="cam-1", possible_fall_threshold=0.01, grace_period_sec=0.2)
        fsm.update(Observation.TRIGGER_POSTURE)
        time.sleep(0.05)
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        fsm.update(Observation.PERSON_LOST)
        assert fsm.state == FallState.POSSIBLE_FALL
        
        time.sleep(0.1)
        fsm.update(Observation.PERSON_LOST)
        # Masih di bawah grace period
        assert fsm.state == FallState.POSSIBLE_FALL
        
        time.sleep(0.15)
        fsm.update(Observation.PERSON_LOST)
        # Melewati grace period -> Reset!
        assert fsm.state == FallState.MONITORING
        assert fsm.fall_duration == 0.0

    def test_confirmed_fall_with_short_threshold(self):
        """Fall di-confirm jika durasi melebihi threshold."""
        callback = MagicMock()
        fsm = FallStateMachine(
            camera_id="cam-1",
            possible_fall_threshold=0.01,
            fall_duration_threshold=0.1,  # 100ms untuk test cepat
            on_confirmed_fall=callback,
        )

        fsm.update(Observation.TRIGGER_POSTURE)
        time.sleep(0.05)
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.POSSIBLE_FALL

        time.sleep(0.1)  # Tunggu melebihi threshold
        fsm.update(Observation.TRIGGER_POSTURE)
        assert fsm.state == FallState.CONFIRMED_FALL
        callback.assert_called_once()
        
        # Panggil lagi tidak mentrigger callback dua kali
        fsm.update(Observation.TRIGGER_POSTURE)
        assert callback.call_count == 1

    def test_reset_from_confirmed(self):
        """Reset dari CONFIRMED_FALL kembali ke MONITORING."""
        fsm = FallStateMachine(
            camera_id="cam-1",
            possible_fall_threshold=0.01,
            fall_duration_threshold=0.05,
        )
        fsm.update(Observation.TRIGGER_POSTURE)
        time.sleep(0.1)
        fsm.update(Observation.TRIGGER_POSTURE)
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

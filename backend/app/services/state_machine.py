"""
state_machine.py
================
Finite State Machine (FSM) untuk fall detection.

States:
    MONITORING     → Kondisi normal, tidak ada indikasi jatuh.
    POSSIBLE_FALL  → Postur "lying_on_ground" terdeteksi, mulai hitung durasi.
    CONFIRMED_FALL → Durasi melebihi threshold, trigger alert.

Transisi:
    MONITORING     --[lying_on_ground detected]--> POSSIBLE_FALL
    POSSIBLE_FALL  --[still lying, duration >= threshold]--> CONFIRMED_FALL
    POSSIBLE_FALL  --[postur berubah (normal/transitional)]--> MONITORING (reset)
    CONFIRMED_FALL --[acknowledged / timeout]--> MONITORING (reset)

Note: "transitional" (sedang jatuh) TIDAK trigger timer.
      Hanya "lying_on_ground" (sudah terbaring) yang dihitung.
      Ini mengurangi false positive dari gerakan membungkuk/transisi.

Setiap kamera memiliki instance FallStateMachine tersendiri.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.models.schemas import FallState, PostureClass


@dataclass
class FallStateMachine:
    """State machine untuk mendeteksi fall berdasarkan durasi.

    Attributes:
        camera_id: ID kamera yang dipantau.
        fall_duration_threshold: Detik postur falling sebelum CONFIRMED.
        possible_fall_threshold: Detik sebelum transisi ke POSSIBLE_FALL.
        on_confirmed_fall: Callback yang dipanggil saat fall dikonfirmasi.
    """

    camera_id: str
    fall_duration_threshold: float = 10.0
    possible_fall_threshold: float = 2.0
    on_confirmed_fall: Optional[Callable] = None

    # Internal state
    state: FallState = field(default=FallState.MONITORING, init=False)
    _fall_start_time: Optional[float] = field(default=None, init=False)
    _last_posture: Optional[PostureClass] = field(default=None, init=False)

    @property
    def fall_duration(self) -> float:
        """Durasi postur falling saat ini (detik)."""
        if self._fall_start_time is None:
            return 0.0
        return time.time() - self._fall_start_time

    def update(self, posture: PostureClass) -> FallState:
        """Update state berdasarkan postur terdeteksi.

        Args:
            posture: Postur yang terdeteksi pada frame saat ini.

        Returns:
            State terbaru setelah update.
        """
        self._last_posture = posture

        if posture == PostureClass.LYING_ON_GROUND:
            self._handle_lying()
        else:
            self._handle_not_lying()

        return self.state

    def _handle_lying(self) -> None:
        """Logic saat postur = LYING_ON_GROUND (terbaring di lantai)."""
        if self.state == FallState.MONITORING:
            # Mulai catat waktu falling
            self._fall_start_time = time.time()
            self.state = FallState.POSSIBLE_FALL
            print(f"[{self.camera_id}] ⚠️  POSSIBLE_FALL detected")

        elif self.state == FallState.POSSIBLE_FALL:
            duration = self.fall_duration
            if duration >= self.fall_duration_threshold:
                self.state = FallState.CONFIRMED_FALL
                print(
                    f"[{self.camera_id}] 🚨 CONFIRMED_FALL! "
                    f"Duration: {duration:.1f}s"
                )
                if self.on_confirmed_fall:
                    self.on_confirmed_fall(self.camera_id, duration)

        # Jika sudah CONFIRMED, tetap di state itu sampai di-reset

    def _handle_not_lying(self) -> None:
        """Logic saat postur bukan LYING_ON_GROUND — reset ke MONITORING."""
        if self.state in (FallState.POSSIBLE_FALL, FallState.CONFIRMED_FALL):
            prev_state = self.state
            self.reset()
            if prev_state == FallState.POSSIBLE_FALL:
                print(f"[{self.camera_id}] ✅ Orang bangkit/bergerak, reset to MONITORING")

    def reset(self) -> None:
        """Reset state machine ke MONITORING."""
        self.state = FallState.MONITORING
        self._fall_start_time = None

    def update_thresholds(
        self,
        fall_duration: Optional[float] = None,
        possible_fall: Optional[float] = None,
    ) -> None:
        """Update threshold tanpa reset state.

        Args:
            fall_duration: Threshold baru untuk confirmed fall (detik).
            possible_fall: Threshold baru untuk possible fall (detik).
        """
        if fall_duration is not None:
            self.fall_duration_threshold = fall_duration
        if possible_fall is not None:
            self.possible_fall_threshold = possible_fall

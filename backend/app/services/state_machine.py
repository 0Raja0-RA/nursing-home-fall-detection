"""
state_machine.py
================
Finite State Machine (FSM) untuk fall detection dengan time-tracking berbasis akumulasi.

States:
    MONITORING     → Kondisi normal, tidak ada indikasi jatuh.
    POSSIBLE_FALL  → Postur pemicu terdeteksi, mulai hitung durasi.
    CONFIRMED_FALL → Durasi melebihi threshold, trigger alert.
    UNKNOWN        → Kamera offline.

Transisi baru mengakomodasi:
- Anti-flicker: frame non-pemicu tidak langsung mereset (debounce).
- Uncertain: waktu dihentikan sementara (pause).
- Person lost: waktu dihentikan, reset jika melebihi grace period.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.models.schemas import FallState, Observation

from app.core.logging import get_logger
log = get_logger("app.services.state_machine")


@dataclass
class FallStateMachine:
    """State machine untuk mendeteksi fall berdasarkan durasi.

    Attributes:
        camera_id: ID kamera yang dipantau.
        fall_duration_threshold: Detik postur falling sebelum CONFIRMED.
        possible_fall_threshold: Detik sebelum transisi ke POSSIBLE_FALL.
        debounce_frames: Jumlah frame non-pemicu sebelum mereset hitungan.
        grace_period_sec: Detik batas person lost sebelum mereset hitungan.
        max_dt_sec: Batas atas waktu yang boleh dihitung dari satu observasi.
        on_confirmed_fall: Callback yang dipanggil saat fall dikonfirmasi.
    """

    camera_id: str
    fall_duration_threshold: float = 10.0
    possible_fall_threshold: float = 2.0
    debounce_frames: int = 5
    grace_period_sec: float = 3.0
    # Satu observasi hanya boleh menambah waktu sebanyak-banyaknya sekian detik.
    #
    # Timer dihitung dari selisih waktu antar pemanggilan update(), yang
    # mengandaikan pipeline tidak pernah berhenti. Kenyataannya ia berhenti:
    # memuat model YOLO pertama kali memakan 8-10 detik, inference di CPU bisa
    # tersendat, dan kamera yang terputus menyambung ulang. Tanpa batas ini,
    # observasi pemicu PERTAMA setelah jeda panjang langsung menyumbang seluruh
    # jeda itu -- terukur: jeda 5 detik lalu satu observasi pemicu menghasilkan
    # akumulasi 5,0 detik dan CONFIRMED_FALL seketika, padahal tidak ada bukti
    # apa pun tentang apa yang terjadi selama jeda.
    #
    # Dibatasi, bukan dibuang: jeda panjang tidak boleh mengarang waktu, tapi
    # juga tidak boleh menghapus hitungan yang sudah sah terkumpul.
    max_dt_sec: float = 1.0
    on_confirmed_fall: Optional[Callable] = None

    # Internal state
    state: FallState = field(default=FallState.MONITORING, init=False)
    
    _accumulated_fall_time: float = field(default=0.0, init=False)
    _last_update_time: float = field(default_factory=time.time, init=False)
    
    _debounce_counter: int = field(default=0, init=False)
    _person_lost_start: Optional[float] = field(default=None, init=False)
    _has_triggered_alert: bool = field(default=False, init=False)

    @property
    def fall_duration(self) -> float:
        """Durasi akumulatif postur falling (detik)."""
        return self._accumulated_fall_time

    def update(self, observation: Observation) -> FallState:
        """Update state berdasarkan observasi terbaru.

        Args:
            observation: Hasil agregasi deteksi dari inference.

        Returns:
            State terbaru setelah update.
        """
        now = time.time()
        # Dibatasi: lihat penjelasan pada max_dt_sec. Jeda yang tidak terpantau
        # tidak boleh dihitung sebagai waktu tergeletak.
        dt = min(now - self._last_update_time, self.max_dt_sec)
        self._last_update_time = now

        if observation == Observation.OFFLINE:
            self._reset_internal(FallState.UNKNOWN)
            return self.state

        if self.state == FallState.UNKNOWN:
            self.state = FallState.MONITORING

        if observation == Observation.TRIGGER_POSTURE:
            self._debounce_counter = 0
            self._person_lost_start = None
            self._accumulated_fall_time += dt
            self._check_thresholds()

        elif observation == Observation.NON_TRIGGER_POSTURE:
            self._person_lost_start = None
            if self._accumulated_fall_time > 0:
                self._debounce_counter += 1
                if self._debounce_counter >= self.debounce_frames:
                    self._reset_internal(FallState.MONITORING)

        elif observation == Observation.UNCERTAIN:
            # Pause perhitungan, debounce dan grace period batal
            self._person_lost_start = None

        elif observation == Observation.PERSON_LOST:
            if self._accumulated_fall_time > 0:
                if self._person_lost_start is None:
                    self._person_lost_start = now
                elif now - self._person_lost_start >= self.grace_period_sec:
                    self._reset_internal(FallState.MONITORING)

        return self.state

    def _check_thresholds(self) -> None:
        if self.state == FallState.CONFIRMED_FALL:
            return

        if self._accumulated_fall_time >= self.fall_duration_threshold:
            self.state = FallState.CONFIRMED_FALL
            log.info(f"[{self.camera_id}] 🚨 CONFIRMED_FALL! Duration: {self._accumulated_fall_time:.1f}s")
            if not self._has_triggered_alert and self.on_confirmed_fall:
                self._has_triggered_alert = True
                self.on_confirmed_fall(self.camera_id, self._accumulated_fall_time)
                
        elif self._accumulated_fall_time >= self.possible_fall_threshold:
            if self.state != FallState.POSSIBLE_FALL:
                self.state = FallState.POSSIBLE_FALL
                log.info(f"[{self.camera_id}] ⚠️  POSSIBLE_FALL detected")

    def _reset_internal(self, new_state: FallState) -> None:
        if self.state in (FallState.POSSIBLE_FALL, FallState.CONFIRMED_FALL):
            log.info(f"[{self.camera_id}] ✅ Reset to {new_state.value}")
        self.state = new_state
        self._accumulated_fall_time = 0.0
        self._debounce_counter = 0
        self._person_lost_start = None
        self._has_triggered_alert = False

    def reset(self) -> None:
        """Reset state machine ke MONITORING."""
        self._reset_internal(FallState.MONITORING)

    def update_thresholds(
        self,
        fall_duration: Optional[float] = None,
        possible_fall: Optional[float] = None,
    ) -> None:
        """Update threshold tanpa reset state."""
        if fall_duration is not None:
            self.fall_duration_threshold = fall_duration
        if possible_fall is not None:
            self.possible_fall_threshold = possible_fall

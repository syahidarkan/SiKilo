from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from typing import Optional
import numpy as np


@dataclass
class TelemetrySample:
    timestamp: datetime
    p_active: float
    q_reactive: float
    v_rms: float
    i_rms: float
    frequency: float


@dataclass
class TransientEvent:
    timestamp: datetime
    delta_p: float
    delta_q: float
    p_before: float
    q_before: float
    p_after: float
    q_after: float
    v_rms: float
    i_rms: float
    inrush_peak_ratio: float
    event_type: str  # "ON" | "OFF"


class EventDetector:
    """
    CUSUM-style transient event detector.
    Fires when |ΔP| >= threshold within a 3-second rolling window.
    """

    def __init__(
        self,
        threshold_w: float = 50.0,
        window_seconds: int = 3,
        sample_rate_hz: float = 1.0,
    ) -> None:
        self.threshold_w = threshold_w
        self.window_size = int(window_seconds * sample_rate_hz)
        self._buffer: deque[TelemetrySample] = deque(maxlen=self.window_size * 2)
        self._last_stable_p: Optional[float] = None
        self._last_stable_q: Optional[float] = None
        self._cooldown_ticks: int = 0
        self._cooldown_duration: int = max(3, self.window_size)

    def push(self, sample: TelemetrySample) -> Optional[TransientEvent]:
        self._buffer.append(sample)

        if self._cooldown_ticks > 0:
            self._cooldown_ticks -= 1
            return None

        if len(self._buffer) < 2:
            self._last_stable_p = sample.p_active
            self._last_stable_q = sample.q_reactive
            return None

        prev = list(self._buffer)[-2]
        delta_p = sample.p_active - prev.p_active
        delta_q = sample.q_reactive - prev.q_reactive

        if abs(delta_p) < self.threshold_w:
            # Update stable baseline with exponential moving average
            alpha = 0.1
            if self._last_stable_p is None:
                self._last_stable_p = sample.p_active
                self._last_stable_q = sample.q_reactive
            else:
                self._last_stable_p = (1 - alpha) * self._last_stable_p + alpha * sample.p_active
                self._last_stable_q = (1 - alpha) * self._last_stable_q + alpha * sample.q_reactive
            return None

        # Confirm event using window average to filter noise
        window = list(self._buffer)
        recent_window = window[-self.window_size :]
        p_values = [s.p_active for s in recent_window]
        window_delta = max(p_values) - min(p_values)

        if window_delta < self.threshold_w:
            return None

        inrush_peak = max(p_values)
        mean_p = np.mean(p_values)
        inrush_ratio = inrush_peak / mean_p if mean_p > 1.0 else 1.0

        p_before = self._last_stable_p if self._last_stable_p is not None else prev.p_active
        q_before = self._last_stable_q if self._last_stable_q is not None else prev.q_reactive

        event = TransientEvent(
            timestamp=sample.timestamp,
            delta_p=delta_p,
            delta_q=delta_q,
            p_before=p_before,
            q_before=q_before,
            p_after=sample.p_active,
            q_after=sample.q_reactive,
            v_rms=sample.v_rms,
            i_rms=sample.i_rms,
            inrush_peak_ratio=float(inrush_ratio),
            event_type="ON" if delta_p > 0 else "OFF",
        )

        self._cooldown_ticks = self._cooldown_duration
        self._last_stable_p = sample.p_active
        self._last_stable_q = sample.q_reactive

        return event

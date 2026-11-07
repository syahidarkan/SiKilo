"""
Detektor event transien (ON/OFF) dari telemetri panel.

Cara kerja (mesin keadaan dua status):

1. STABIL   – menyimpan W sampel terakhir (W = window_s × sample_rate). Baseline
              = median P/Q jendela itu. Bila sampel baru menyimpang ≥ threshold
              dari baseline, baseline "sebelum" dibekukan dan masuk TRANSIEN.
2. TRANSIEN – mengumpulkan sampel (termasuk lonjakan inrush) sampai W sampel
              terakhir kembali stabil. ΔP = median(sesudah) − baseline(sebelum).
              Satu event dikeluarkan bila |ΔP| ≥ threshold. Lonjakan sesaat yang
              kembali ke level semula tidak menghasilkan event.

Dengan begitu ΔP diukur dari baseline stabil sebelum vs sesudah (bukan beda
sampel berturut-turut), ramp 2–3 sampel tetap terukur penuh, dan inrush motor
tidak menghasilkan event ganda.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from app.core.config import settings


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
    timestamp: datetime          # awal transien (onset)
    delta_p: float
    delta_q: float
    p_before: float
    q_before: float
    p_after: float
    q_after: float
    v_rms: float
    i_rms: float
    inrush_peak_ratio: float     # (P puncak − P sebelum) / ΔP, ≥ 1; = 1 untuk OFF
    event_type: str              # "ON" | "OFF"
    transient_duration_s: float = 0.0  # lama dari onset sampai sinyal stabil lagi


class EventDetector:
    def __init__(
        self,
        threshold_w: float | None = None,
        window_seconds: int | None = None,
        sample_rate_hz: float = 1.0,
        max_transient_s: int | None = None,
        rel_stable_tol: float = 0.015,
    ) -> None:
        self.threshold_w = float(threshold_w if threshold_w is not None else settings.nilm_event_threshold_w)
        window_s = window_seconds if window_seconds is not None else settings.nilm_event_window_s
        max_tr_s = max_transient_s if max_transient_s is not None else settings.nilm_event_max_transient_s
        self.sample_rate_hz = sample_rate_hz
        self.window_size = max(2, int(round(window_s * sample_rate_hz)))
        self.max_transient_samples = max(self.window_size + 1, int(round(max_tr_s * sample_rate_hz)))
        self.rel_stable_tol = rel_stable_tol

        self._steady: deque[TelemetrySample] = deque(maxlen=self.window_size)
        self._transient: list[TelemetrySample] = []
        self._p_before: float = 0.0
        self._q_before: float = 0.0

    # ── util ────────────────────────────────────────────────────────────────
    def _stable_tol(self, level: float) -> float:
        return max(self.threshold_w, self.rel_stable_tol * abs(level))

    def _is_stable(self, samples: list[TelemetrySample]) -> bool:
        p = np.fromiter((s.p_active for s in samples), dtype=np.float64, count=len(samples))
        med = float(np.median(p))
        return bool(np.max(np.abs(p - med)) <= self._stable_tol(med))

    @staticmethod
    def _median(samples, attr: str) -> float:
        return float(np.median([getattr(s, attr) for s in samples]))

    @property
    def in_transient(self) -> bool:
        return bool(self._transient)

    def reset(self) -> None:
        self._steady.clear()
        self._transient = []

    # ── API ─────────────────────────────────────────────────────────────────
    def push(self, sample: TelemetrySample) -> Optional[TransientEvent]:
        if not self._transient:
            if len(self._steady) < self.window_size:
                self._steady.append(sample)
                return None
            base_p = self._median(self._steady, "p_active")
            if abs(sample.p_active - base_p) < self.threshold_w:
                self._steady.append(sample)
                return None
            # Mulai transien: bekukan baseline sebelum.
            self._p_before = base_p
            self._q_before = self._median(self._steady, "q_reactive")
            self._transient = [sample]
            return None

        self._transient.append(sample)
        tail = self._transient[-self.window_size:]
        stable = len(self._transient) >= self.window_size and self._is_stable(tail)
        forced = len(self._transient) >= self.max_transient_samples
        if not (stable or forced):
            return None
        return self._close_transient(tail)

    def _close_transient(self, tail: list[TelemetrySample]) -> Optional[TransientEvent]:
        samples = self._transient
        self._transient = []
        self._steady.clear()
        self._steady.extend(tail)

        p_after = self._median(tail, "p_active")
        q_after = self._median(tail, "q_reactive")
        delta_p = p_after - self._p_before
        delta_q = q_after - self._q_before
        if abs(delta_p) < self.threshold_w:
            return None  # lonjakan sesaat / noise, level kembali ke semula

        event_type = "ON" if delta_p > 0 else "OFF"
        if event_type == "ON":
            peak = max(s.p_active for s in samples)
            inrush = max(1.0, (peak - self._p_before) / delta_p)
        else:
            inrush = 1.0

        n_settle = max(0, len(samples) - len(tail))
        last = samples[-1]
        return TransientEvent(
            timestamp=samples[0].timestamp,
            delta_p=float(delta_p),
            delta_q=float(delta_q),
            p_before=float(self._p_before),
            q_before=float(self._q_before),
            p_after=float(p_after),
            q_after=float(q_after),
            v_rms=float(last.v_rms),
            i_rms=float(last.i_rms),
            inrush_peak_ratio=float(inrush),
            event_type=event_type,
            transient_duration_s=float(n_settle / self.sample_rate_hz),
        )

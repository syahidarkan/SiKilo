"""
Utilitas data latih/uji NILM: baca CSV panel & smart plug, ambil transisi
ON/OFF dari smart plug, cocokkan ke event panel, dan hitung energi per jam
dari smart plug. Format CSV dijelaskan di docs/NILM.md.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Iterator, Optional

import numpy as np
import pandas as pd

from app.core.config import settings
from app.nilm.event_detector import EventDetector, TelemetrySample, TransientEvent
from app.nilm.profiles import BASELOAD_LABEL

PANEL_COLUMNS = ["timestamp", "v_rms", "i_rms", "p_active", "q_reactive", "frequency"]
PLUG_REQUIRED = ["timestamp", "appliance_label", "p_active"]
DEFAULT_PLUG_ON_THRESHOLD_W = 15.0
# Celah antar baris smart plug yang lebih panjang dari ini dianggap data hilang.
PLUG_MAX_GAP_S = 900.0


def _to_local_naive(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, utc=False, format="ISO8601")
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert(settings.site_timezone).dt.tz_localize(None)
    return ts


def _pydatetimes(series: pd.Series) -> list[datetime]:
    return list(np.asarray(series.dt.to_pydatetime(), dtype=object))


def load_panel_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in PANEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV panel {path} kekurangan kolom: {missing}")
    df["timestamp"] = _to_local_naive(df["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def iter_panel_samples(df: pd.DataFrame) -> Iterator[TelemetrySample]:
    ts = _pydatetimes(df["timestamp"])
    cols = [df[c].to_numpy(dtype=float) for c in ("p_active", "q_reactive", "v_rms", "i_rms", "frequency")]
    for i in range(len(df)):
        yield TelemetrySample(
            timestamp=ts[i],
            p_active=cols[0][i],
            q_reactive=cols[1][i],
            v_rms=cols[2][i],
            i_rms=cols[3][i],
            frequency=cols[4][i],
        )


def load_plug_csv(path: str, on_threshold_w: float = DEFAULT_PLUG_ON_THRESHOLD_W) -> pd.DataFrame:
    """
    Baca CSV smart plug (format panjang: satu baris per pembacaan per mesin).
    Kolom wajib: timestamp, appliance_label, p_active. Kolom `status`
    (ON/OFF, 1/0, true/false) opsional; bila tidak ada, status = p_active > ambang.
    """
    df = pd.read_csv(path)
    missing = [c for c in PLUG_REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"CSV smart plug {path} kekurangan kolom: {missing}")
    df["timestamp"] = _to_local_naive(df["timestamp"])
    df["appliance_label"] = df["appliance_label"].astype(str).str.strip()
    df["p_active"] = pd.to_numeric(df["p_active"], errors="coerce").fillna(0.0)
    if "status" in df.columns:
        s = df["status"].astype(str).str.strip().str.upper()
        df["is_on"] = s.isin(["ON", "1", "TRUE", "1.0"])
    else:
        df["is_on"] = df["p_active"] > on_threshold_w
    return df.sort_values(["appliance_label", "timestamp"]).reset_index(drop=True)


@dataclass
class PlugTransition:
    appliance_label: str
    event_type: str          # "ON" | "OFF"
    window_start: datetime   # transisi terjadi di antara window_start…window_end
    window_end: datetime
    step_w: float            # daya tipikal (median) selama periode ON terkait


def extract_plug_transitions(plugs: pd.DataFrame) -> list[PlugTransition]:
    out: list[PlugTransition] = []
    for label, g in plugs.groupby("appliance_label", sort=True):
        ts = _pydatetimes(g["timestamp"])
        on = g["is_on"].to_numpy(dtype=bool)
        p = g["p_active"].to_numpy(dtype=float)
        i = 1
        n = len(g)
        while i < n:
            if on[i] and not on[i - 1]:
                j = i
                while j < n and on[j]:
                    j += 1
                step = float(np.median(p[i:j]))
                out.append(PlugTransition(label, "ON", ts[i - 1], ts[i], step))
                if j < n:
                    out.append(PlugTransition(label, "OFF", ts[j - 1], ts[j], step))
                i = j + 1
            else:
                i += 1
    out.sort(key=lambda t: t.window_end)
    return out


def detect_events(samples: Iterable[TelemetrySample], detector: Optional[EventDetector] = None) -> list[TransientEvent]:
    detector = detector or EventDetector()
    events = []
    for s in samples:
        ev = detector.push(s)
        if ev is not None:
            events.append(ev)
    return events


def _time_distance_s(ts: datetime, tr: PlugTransition) -> float:
    if tr.window_start <= ts <= tr.window_end:
        return 0.0
    if ts < tr.window_start:
        return (tr.window_start - ts).total_seconds()
    return (ts - tr.window_end).total_seconds()


def match_events_to_transitions(
    events: list[TransientEvent],
    transitions: list[PlugTransition],
    tolerance_s: Optional[float] = None,
    max_power_rel_diff: float = 0.6,
) -> list[Optional[int]]:
    """
    Pasangkan tiap event panel ke paling banyak satu transisi smart plug
    (arah sama, |Δt| ≤ toleransi, |ΔP| mirip). Greedy berdasarkan biaya
    Δt/toleransi + selisih relatif daya. Kembalikan indeks transisi per event
    (None bila tidak ada pasangan → event latar/beban tak terukur).
    """
    tol = float(tolerance_s if tolerance_s is not None else settings.nilm_label_tolerance_s)
    if not events or not transitions:
        return [None] * len(events)
    ends = np.array([t.window_end.timestamp() for t in transitions])
    max_window = max((t.window_end - t.window_start).total_seconds() for t in transitions)
    candidates: list[tuple[float, int, int]] = []
    for ei, ev in enumerate(events):
        t0 = ev.timestamp.timestamp()
        lo = np.searchsorted(ends, t0 - tol, side="left")
        hi = np.searchsorted(ends, t0 + tol + max_window, side="right")
        step = abs(ev.delta_p)
        for ti in range(lo, hi):
            tr = transitions[ti]
            if tr.event_type != ev.event_type:
                continue
            dt = _time_distance_s(ev.timestamp, tr)
            if dt > tol:
                continue
            rel = abs(step - tr.step_w) / max(tr.step_w, settings.nilm_event_threshold_w)
            if rel > max_power_rel_diff:
                continue
            candidates.append((dt / max(tol, 1e-6) + rel, ei, ti))
    candidates.sort()
    assigned: list[Optional[int]] = [None] * len(events)
    used: set[int] = set()
    for _, ei, ti in candidates:
        if assigned[ei] is None and ti not in used:
            assigned[ei] = ti
            used.add(ti)
    return assigned


def plug_hourly_energy_kwh(plugs: pd.DataFrame, max_gap_s: float = PLUG_MAX_GAP_S) -> dict[tuple[date, int, str], float]:
    """Energi per (hari, jam, label) dari smart plug, integrasi zero-order hold."""
    out: dict[tuple[date, int, str], float] = defaultdict(float)
    for label, g in plugs.groupby("appliance_label", sort=True):
        ts = g["timestamp"].to_numpy(dtype="datetime64[ns]")
        p = g["p_active"].to_numpy(dtype=float)
        if len(ts) < 2:
            continue
        dt = (ts[1:] - ts[:-1]).astype("timedelta64[ns]").astype(np.float64) / 1e9
        valid = (dt > 0) & (dt <= max_gap_s)
        kwh = np.where(valid, p[:-1] * dt / 3.6e6, 0.0)
        hours = pd.DatetimeIndex(ts[:-1]).floor("h")
        sums = pd.Series(kwh).groupby(hours).sum()
        for h, v in sums.items():
            out[(h.date(), h.hour, str(label))] += float(v)
    return dict(out)


def panel_hourly_energy_kwh(panel: pd.DataFrame, max_gap_s: float = 10.0) -> dict[tuple[date, int], float]:
    """Energi total terukur per (hari, jam) dengan konvensi yang sama dengan LoadDisaggregator."""
    ts = panel["timestamp"].to_numpy(dtype="datetime64[ns]")
    p = np.clip(panel["p_active"].to_numpy(dtype=float), 0.0, None)
    dt = (ts[1:] - ts[:-1]).astype("timedelta64[ns]").astype(np.float64) / 1e9
    dt = np.where(dt > 0, np.minimum(dt, max_gap_s), 0.0)
    kwh = p[1:] * dt / 3.6e6
    hours = pd.DatetimeIndex(ts[1:]).floor("h")
    sums = pd.Series(kwh).groupby(hours).sum()
    return {(h.date(), h.hour): float(v) for h, v in sums.items()}


def label_events(
    events: list[TransientEvent],
    transitions: list[PlugTransition],
    tolerance_s: Optional[float] = None,
    background_label: str = BASELOAD_LABEL,
) -> list[str]:
    """Label tiap event dari transisi smart plug terdekat; tanpa pasangan → background_label."""
    assigned = match_events_to_transitions(events, transitions, tolerance_s)
    return [transitions[a].appliance_label if a is not None else background_label for a in assigned]


def iso_now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


__all__ = [
    "PANEL_COLUMNS",
    "PlugTransition",
    "load_panel_csv",
    "iter_panel_samples",
    "load_plug_csv",
    "extract_plug_transitions",
    "detect_events",
    "match_events_to_transitions",
    "label_events",
    "plug_hourly_energy_kwh",
    "panel_hourly_energy_kwh",
    "iso_now",
]

"""
Disagregasi beban: event ON/OFF terklasifikasi → status & daya tiap mesin →
energi per jam per mesin (kontrak CONTRACTS.md §2).

Aturan:
- Event ON yang diklasifikasi sebagai mesin (bukan baseload) menambah satu
  "instans" mesin dengan daya |ΔP|.
- Event OFF dicocokkan ke instans aktif dengan |ΔP| terdekat (ΔQ juga harus
  mirip; diutamakan bila labelnya sama dengan hasil klasifikasi OFF). OFF yang
  tidak punya pasangan wajar diabaikan (masuk residu).
- Energi tiap sampel = P_terukur × Δt dibagi ke mesin aktif. Bila jumlah
  estimasi > P_terukur, semua estimasi diskalakan proporsional; sisanya
  (residu) masuk "Baseload / Background". Jadi Σ energi semua label per jam =
  energi terukur total (konservasi energi).
- Penjaga untuk OFF yang terlewat: (a) OFF yang diklasifikasi sebagai mesin X
  boleh mematikan instans X dengan toleransi daya longgar; (b) bila P atau Q
  terukur terus-menerus jauh di bawah jumlah estimasi, instans yang paling
  mungkin basi dilepas; (c) opsional `max_instances_per_label` (inventaris
  mesin) — ON baru melebihi jumlah unit mengganti instans terlama.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Union

from app.nilm.classifier import ClassificationResult, NILMClassifier
from app.nilm.event_detector import EventDetector, TelemetrySample, TransientEvent
from app.nilm.profiles import BASELOAD_LABEL


@dataclass
class DisaggregationUpdate:
    event: Optional[TransientEvent]
    classification: Optional[ClassificationResult]
    active: dict[str, float]          # label → watt estimasi (setelah penskalaan)
    p_total_w: float = 0.0
    baseload_w: float = 0.0


@dataclass
class HourlyEnergy:
    day: date
    hour: int
    appliance_label: str
    kwh: float


@dataclass
class _Instance:
    label: str
    appliance_class: int
    power_w: float
    reactive_var: float
    since: datetime


@dataclass
class LoadDisaggregator:
    classifier: Optional[NILMClassifier] = None
    detector: Optional[EventDetector] = None
    max_gap_s: float = 10.0            # Δt maksimum yang diintegrasikan antar sampel
    off_match_rel_tol: float = 0.25    # |ΔP_off − P_instans| ≤ tol × P_instans
    off_match_q_rel_tol: float = 0.12  # |ΔQ_off − Q_instans| ≤ tol × |S_instans| …
    off_match_q_abs_var: float = 50.0  # … minimal sekian VAR
    same_label_bonus: float = 0.7      # pengali biaya bila label OFF = label instans
    off_match_loose_rel_tol: float = 0.6  # tahap 2: OFF berlabel sama, toleransi longgar
    stale_ratio: float = 0.6           # P_terukur < ratio × ΣP estimasi …
    stale_q_margin_var: float = 80.0   # … atau Q_terukur + margin < ΣQ estimasi …
    stale_s: float = 60.0              # … selama ini → lepas instans yang paling mungkin basi
    # Jumlah unit maksimum per label (mis. dari inventaris MachineProfile).
    # None = tak dibatasi. Bila ON baru melebihi batas, instans terlama dianggap
    # OFF-nya terlewat dan diganti.
    max_instances_per_label: Optional[Union[int, dict[str, int]]] = None

    _instances: list[_Instance] = field(default_factory=list, init=False)
    _buckets: dict[tuple[date, int], dict[str, float]] = field(default_factory=dict, init=False)
    _last_ts: Optional[datetime] = field(default=None, init=False)
    _stale_since: Optional[datetime] = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.classifier is None:
            self.classifier = NILMClassifier()
        if self.detector is None:
            self.detector = EventDetector()

    # ── status ──────────────────────────────────────────────────────────────
    def _active_raw(self) -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for inst in self._instances:
            out[inst.label] += inst.power_w
        return dict(out)

    def active_appliances(self) -> dict[str, float]:
        return self._active_raw()

    # ── event handling ──────────────────────────────────────────────────────
    def _label_cap(self, label: str) -> Optional[int]:
        cap = self.max_instances_per_label
        if isinstance(cap, dict):
            return cap.get(label)
        return cap

    def _handle_event(self, event: TransientEvent) -> ClassificationResult:
        result = self.classifier.predict(event)
        step = abs(event.delta_p)
        if event.event_type == "ON":
            if result.appliance_class != 0 and result.label != BASELOAD_LABEL:
                cap = self._label_cap(result.label)
                same = [k for k, i in enumerate(self._instances) if i.label == result.label]
                if cap is not None and len(same) >= cap:
                    # Unit label ini sudah "menyala" semua → OFF sebelumnya terlewat.
                    self._instances.pop(min(same, key=lambda k: self._instances[k].since))
                self._instances.append(
                    _Instance(result.label, result.appliance_class, step, abs(event.delta_q), event.timestamp)
                )
            return result

        # OFF → instans aktif dengan |ΔP| terdekat (ΔQ ikut dicek agar beban
        # resistif tidak "mematikan" motor berdaya mirip).
        step_q = abs(event.delta_q)
        best_i, best_cost = None, float("inf")
        for i, inst in enumerate(self._instances):
            p_tol = self.off_match_rel_tol * max(inst.power_w, 1.0)
            q_tol = max(self.off_match_q_rel_tol * math.hypot(inst.power_w, inst.reactive_var), self.off_match_q_abs_var)
            dp = abs(inst.power_w - step)
            dq = abs(inst.reactive_var - step_q)
            if dp > p_tol or dq > q_tol:
                continue
            cost = (dp / p_tol) ** 2 + (dq / q_tol) ** 2
            if inst.label == result.label:
                cost *= self.same_label_bonus
            if cost < best_cost:
                best_i, best_cost = i, cost
        if best_i is None and result.label != BASELOAD_LABEL:
            # Tahap 2: classifier yakin ini OFF mesin X → terima instans X dengan
            # toleransi daya lebih longgar (ΔP saat ON bisa terdistorsi event lain).
            same = [
                k for k, inst in enumerate(self._instances)
                if inst.label == result.label
                and abs(inst.power_w - step) <= self.off_match_loose_rel_tol * max(inst.power_w, step)
            ]
            if same:
                best_i = min(same, key=lambda k: abs(self._instances[k].power_w - step))
        if best_i is None:
            return result
        inst = self._instances.pop(best_i)
        return ClassificationResult(
            appliance_class=inst.appliance_class,
            label=inst.label,
            confidence=result.confidence,
            source=result.source,
        )

    def _prune_stale(self, ts: datetime, p_total: float, q_total: float) -> None:
        """
        Lepas instans yang OFF-nya terlewat. Tanda: P terukur jauh di bawah ΣP
        estimasi, atau Q terukur jauh di bawah ΣQ estimasi (berguna untuk mesin
        kecil yang dayanya "tertutup" baseload), terus-menerus selama stale_s.
        """
        if not self._instances or self.detector.in_transient:
            self._stale_since = None
            return
        est_p = sum(i.power_w for i in self._instances)
        est_q = sum(i.reactive_var for i in self._instances)
        q_margin = max(self.stale_q_margin_var, 0.25 * est_q)
        p_bad = p_total < self.stale_ratio * est_p
        q_bad = q_total + q_margin < est_q
        if not (p_bad or q_bad):
            self._stale_since = None
            return
        if self._stale_since is None:
            self._stale_since = ts
            return
        if (ts - self._stale_since).total_seconds() < self.stale_s:
            return
        while self._instances:
            est_p = sum(i.power_w for i in self._instances)
            est_q = sum(i.reactive_var for i in self._instances)
            if est_p <= p_total and est_q <= q_total + max(self.stale_q_margin_var, 0.25 * est_q):
                break
            self._instances.pop(self._stale_candidate(est_q - q_total if q_bad and not p_bad else None))
        self._stale_since = None

    def _stale_candidate(self, q_deficit: Optional[float] = None) -> int:
        """Instans yang paling mungkin OFF-nya terlewat: instans lama dari label yang
        punya ON lebih baru; lalu (bila defisit Q) instans dengan Q paling dekat ke
        defisit; selain itu instans terbesar."""
        counts: dict[str, int] = defaultdict(int)
        for inst in self._instances:
            counts[inst.label] += 1
        dup = [k for k, inst in enumerate(self._instances) if counts[inst.label] > 1]
        if dup:
            return min(dup, key=lambda k: self._instances[k].since)
        idx = range(len(self._instances))
        if q_deficit is not None:
            return min(idx, key=lambda k: abs(self._instances[k].reactive_var - q_deficit))
        return max(idx, key=lambda k: self._instances[k].power_w)

    # ── energi ──────────────────────────────────────────────────────────────
    def _allocate(self, p_total: float) -> tuple[dict[str, float], float]:
        raw = self._active_raw()
        est = sum(raw.values())
        if est <= 0:
            return {}, p_total
        if est > p_total:
            scale = p_total / est
            return {k: v * scale for k, v in raw.items()}, 0.0
        return raw, p_total - est

    def push(self, sample: TelemetrySample) -> DisaggregationUpdate:
        event = self.detector.push(sample)
        classification = self._handle_event(event) if event is not None else None

        p_total = max(float(sample.p_active), 0.0)
        self._prune_stale(sample.timestamp, p_total, float(sample.q_reactive))
        active, baseload = self._allocate(p_total)

        if self._last_ts is not None:
            dt = (sample.timestamp - self._last_ts).total_seconds()
            if 0 < dt:
                dt = min(dt, self.max_gap_s)
                key = (sample.timestamp.date(), sample.timestamp.hour)
                bucket = self._buckets.setdefault(key, defaultdict(float))
                for label, w in active.items():
                    bucket[label] += w * dt / 3.6e6
                bucket[BASELOAD_LABEL] += baseload * dt / 3.6e6
        if self._last_ts is None or sample.timestamp > self._last_ts:
            self._last_ts = sample.timestamp

        return DisaggregationUpdate(
            event=event,
            classification=classification,
            active=active,
            p_total_w=p_total,
            baseload_w=baseload,
        )

    def _emit(self, keys) -> list[HourlyEnergy]:
        out: list[HourlyEnergy] = []
        for key in sorted(keys):
            day, hour = key
            for label, kwh in sorted(self._buckets.pop(key).items()):
                out.append(HourlyEnergy(day=day, hour=hour, appliance_label=label, kwh=float(kwh)))
        return out

    def pop_hourly_energy(self) -> list[HourlyEnergy]:
        """Bucket jam yang SUDAH selesai (sebelum jam sampel terakhir), lalu dihapus."""
        if self._last_ts is None:
            return []
        current = (self._last_ts.date(), self._last_ts.hour)
        return self._emit([k for k in self._buckets if k < current])

    def flush_hourly_energy(self) -> list[HourlyEnergy]:
        """Semua bucket termasuk jam berjalan (dipakai di akhir data / evaluasi)."""
        return self._emit(list(self._buckets))

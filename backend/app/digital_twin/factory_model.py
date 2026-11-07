"""
Model mesin UMKM untuk agen penjadwal WASKITA.

Satu hari = 96 slot × 15 menit (slot ``t`` ↔ jam ``t // 4``). Setiap mesin
punya jendela kerja ``[earliest_slot, deadline_slot)``, runtime wajib, durasi
nyala minimum, dan jeda (cooldown) setelah dimatikan.

Aturan yang dijaga di sini (dan dipakai bersama oleh env RL, greedy, dan
validasi jadwal OR-Tools):

- Boleh ON hanya di dalam jendela dan selama sisa runtime > 0.
- Setelah OFF, mesin baru boleh ON lagi setelah ``cooldown_slots`` slot.
- Setiap blok nyala minimal ``min_run`` slot (= min(min_continuous, runtime)).
- *Forced-ON*: bila sisa slot sampai deadline tinggal sama dengan sisa
  runtime, atau bila mematikan mesin sekarang membuat sisa runtime tidak lagi
  muat setelah cooldown, atau blok minimal belum terpenuhi → mesin dipaksa ON.
  Akibatnya setiap urutan aksi yang lolos mask PASTI menyelesaikan semua
  pesanan sebelum deadline (asal runtime ≤ panjang jendela, dicek saat
  konstruksi).

Mesin tidak fleksibel (``is_flexible=False``) diperlakukan sebagai mesin
dengan jendela tepat selebar blok kebiasaan lama, sehingga selalu dipaksa
mengikuti jadwal lama.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS
from app.digital_twin.battery import Battery

SLOTS_PER_HOUR = N_SLOTS // 24
_NEVER = 10**6


def slot_label(slot: int) -> str:
    """Label jam 'HH:MM' untuk awal slot (slot 96 → '24:00')."""
    return f"{slot // SLOTS_PER_HOUR:02d}:{(slot % SLOTS_PER_HOUR) * 15:02d}"


def _minutes_to_slots(minutes: float) -> int:
    return int(math.ceil(max(float(minutes), 0.0) / 15.0 - 1e-9))


@dataclass
class FlexibleMachine:
    machine_id: str
    appliance_class: int
    label: str
    power_w: float
    daily_runtime_slots: int  # jumlah slot 15 menit yang wajib dijalankan
    deadline_slot: int = field(default_factory=lambda: settings.work_end_hour * SLOTS_PER_HOUR)
    min_continuous_slots: int = 1
    cooldown_slots: int = 2
    earliest_slot: int = field(default_factory=lambda: settings.work_start_hour * SLOTS_PER_HOUR)
    habit_start_slot: Optional[int] = None  # None → settings.default_habit_start_hour
    is_flexible: bool = True
    idle_slots_habit: int = 0
    idle_power_w: float = 0.0

    # Jendela asli dari pemilik (sebelum dipersempit untuk mesin tidak fleksibel).
    job_earliest_slot: int = field(init=False)
    job_deadline_slot: int = field(init=False)
    # State runtime
    remaining_slots: int = field(init=False)
    current_state: int = field(default=0, init=False)
    consecutive_on: int = field(default=0, init=False)
    consecutive_off: int = field(default=_NEVER, init=False)

    def __post_init__(self) -> None:
        self.daily_runtime_slots = int(self.daily_runtime_slots)
        self.earliest_slot = int(self.earliest_slot)
        self.deadline_slot = int(self.deadline_slot)
        self.min_continuous_slots = max(1, int(self.min_continuous_slots))
        self.cooldown_slots = max(0, int(self.cooldown_slots))
        self.idle_slots_habit = max(0, int(self.idle_slots_habit))
        if self.power_w < 0:
            raise ValueError(f"{self.machine_id}: power_w tidak boleh negatif")
        if not 0 <= self.earliest_slot < self.deadline_slot <= N_SLOTS:
            raise ValueError(
                f"{self.machine_id}: jendela kerja tidak valid "
                f"({self.earliest_slot}..{self.deadline_slot})"
            )
        if not 0 <= self.daily_runtime_slots <= self.deadline_slot - self.earliest_slot:
            raise ValueError(
                f"{self.machine_id}: runtime {self.daily_runtime_slots} slot tidak muat di jendela "
                f"{slot_label(self.earliest_slot)}–{slot_label(self.deadline_slot)}"
            )
        self.job_earliest_slot = self.earliest_slot
        self.job_deadline_slot = self.deadline_slot
        if not self.is_flexible and self.daily_runtime_slots > 0:
            start = self.habit_block_start()
            self.earliest_slot = start
            self.deadline_slot = start + self.daily_runtime_slots
        self.reset()

    # ── parameter turunan ──────────────────────────────────────────────────
    @property
    def min_run(self) -> int:
        """Durasi blok minimum efektif (tidak melebihi runtime harian)."""
        if self.daily_runtime_slots <= 0:
            return 1
        return min(self.min_continuous_slots, self.daily_runtime_slots)

    def habit_block_start(self) -> int:
        """Slot mulai kebiasaan lama, digeser agar seluruh runtime muat di jam kerja."""
        hs = self.habit_start_slot
        if hs is None:
            hs = settings.default_habit_start_hour * SLOTS_PER_HOUR
        lo, hi = self.job_earliest_slot, self.job_deadline_slot - self.daily_runtime_slots
        return int(min(max(int(hs), lo), hi))

    # ── state ──────────────────────────────────────────────────────────────
    def reset(self) -> None:
        self.remaining_slots = self.daily_runtime_slots
        self.current_state = 0
        self.consecutive_on = 0
        self.consecutive_off = _NEVER

    def _ready(self) -> bool:
        return self.current_state == 1 or self.consecutive_off >= self.cooldown_slots

    def in_window(self, t: int) -> bool:
        return self.earliest_slot <= t < self.deadline_slot

    def allowed_on(self, t: int) -> bool:
        """Boleh ON di slot t (sisa runtime > 0, dalam jendela, cooldown selesai)."""
        return self.remaining_slots > 0 and self.in_window(t) and self._ready()

    def forced_on(self, t: int) -> bool:
        """Wajib ON di slot t agar deadline / blok minimum / cooldown tetap terpenuhi."""
        r = self.remaining_slots
        if r <= 0 or not self.in_window(t):
            return False
        avail = self.deadline_slot - t  # slot t..deadline-1
        if self.current_state == 1:
            if self.consecutive_on < self.min_run or r < self.min_run:
                return True
            # Mati sekarang (slot t OFF) → baru bisa ON lagi di t + max(cooldown, 1).
            return r > avail - max(self.cooldown_slots, 1)
        if not self._ready():
            return False
        return r >= avail

    def slack(self, t: int) -> int:
        """Sisa slot cadangan sebelum mesin wajib ON terus sampai deadline."""
        avail = max(self.deadline_slot - max(t, self.earliest_slot), 0)
        return avail - self.remaining_slots

    def step(self, on: int) -> None:
        """Terapkan aksi EFEKTIF (sudah lewat mask) untuk satu slot."""
        if on:
            self.remaining_slots = max(0, self.remaining_slots - 1)
            self.consecutive_on += 1
            self.consecutive_off = 0
            self.current_state = 1
        else:
            self.consecutive_off = 1 if self.current_state == 1 else self.consecutive_off + 1
            self.consecutive_on = 0
            self.current_state = 0

    @property
    def is_deadline_violated(self) -> bool:
        return self.remaining_slots > 0

    def clone(self) -> "FlexibleMachine":
        m = copy.copy(self)
        m.reset()
        return m


def machine_from_job(job: Any) -> FlexibleMachine:
    """Buat ``FlexibleMachine`` dari ``MachineJob`` (atau dict/objek dengan atribut sama)."""
    get = job.get if isinstance(job, dict) else (lambda k, d=None: getattr(job, k, d))
    power = float(get("power_w"))
    cooldown_min = get("cooldown_minutes", None)
    if cooldown_min is None:
        cooldown_min = settings.default_cooldown_minutes
    idle_power = get("idle_power_w", None)
    if idle_power is None:
        idle_power = settings.default_idle_power_frac * power
    habit = get("habit_start_hour", None)
    earliest = get("earliest_hour", None)
    deadline = get("deadline_hour", None)
    return FlexibleMachine(
        machine_id=str(get("machine_id")),
        appliance_class=int(get("appliance_class", 0) or 0),
        label=str(get("label", get("machine_id"))),
        power_w=power,
        daily_runtime_slots=_minutes_to_slots(get("daily_runtime_minutes", 0)),
        earliest_slot=(settings.work_start_hour if earliest is None else int(earliest)) * SLOTS_PER_HOUR,
        deadline_slot=(settings.work_end_hour if deadline is None else int(deadline)) * SLOTS_PER_HOUR,
        min_continuous_slots=max(1, _minutes_to_slots(get("min_continuous_minutes", 15) or 15)),
        cooldown_slots=_minutes_to_slots(cooldown_min),
        habit_start_slot=None if habit is None else int(habit) * SLOTS_PER_HOUR,
        is_flexible=bool(get("is_flexible", True)),
        idle_slots_habit=_minutes_to_slots(get("idle_minutes_habit", 0) or 0),
        idle_power_w=float(idle_power),
    )


class UMKMDigitalTwin:
    """
    Kumpulan mesin + jam simulasi. ``step(action)`` menerapkan forced-ON dan
    mask lalu mengembalikan aksi efektif.
    """

    # Contoh mesin UMKM konveksi/sablon/laundry (ASUMSI, bukan hasil ukur).
    DEFAULT_JOB_TEMPLATES: List[Dict[str, Any]] = [
        {
            "machine_id": "boiler-setrika-01",
            "appliance_class": 3,
            "label": "Setrika Uap (Boiler)",
            "power_w": 1500.0,
            "daily_runtime_minutes": 300,
            "earliest_hour": 7,
            "deadline_hour": 17,
            "habit_start_hour": 8,
            "min_continuous_minutes": 60,
            "idle_minutes_habit": 60,
        },
        {
            "machine_id": "drum-pengering-01",
            "appliance_class": 4,
            "label": "Drum Pengering Laundry",
            "power_w": 1200.0,
            "daily_runtime_minutes": 240,
            "earliest_hour": 7,
            "deadline_hour": 17,
            "habit_start_hour": 8,
            "min_continuous_minutes": 45,
            "idle_minutes_habit": 30,
        },
        {
            "machine_id": "kompresor-sablon-01",
            "appliance_class": 2,
            "label": "Kompresor Sablon",
            "power_w": 1500.0,
            "daily_runtime_minutes": 180,
            "earliest_hour": 7,
            "deadline_hour": 17,
            "habit_start_hour": 9,
            "min_continuous_minutes": 30,
            "idle_minutes_habit": 45,
        },
        {
            "machine_id": "oven-curing-01",
            "appliance_class": 3,
            "label": "Oven Curing Sablon",
            "power_w": 2000.0,
            "daily_runtime_minutes": 120,
            "earliest_hour": 7,
            "deadline_hour": 15,
            "habit_start_hour": 8,
            "min_continuous_minutes": 30,
            "idle_minutes_habit": 30,
        },
    ]

    def __init__(self, machines: Optional[List[FlexibleMachine]] = None) -> None:
        if machines is None:
            machines = [machine_from_job(t) for t in self.DEFAULT_JOB_TEMPLATES]
        self.machines = machines
        self.t = 0

    @property
    def n_machines(self) -> int:
        return len(self.machines)

    def reset(self) -> None:
        self.t = 0
        for m in self.machines:
            m.reset()

    def get_action_mask(self) -> np.ndarray:
        """1 = boleh ON di slot sekarang."""
        return np.array([1 if m.allowed_on(self.t) else 0 for m in self.machines], dtype=np.int8)

    def get_forced_mask(self) -> np.ndarray:
        """1 = wajib ON di slot sekarang."""
        return np.array([1 if m.forced_on(self.t) else 0 for m in self.machines], dtype=np.int8)

    def effective_action(self, action: Sequence[int]) -> np.ndarray:
        a = np.asarray(action, dtype=np.int8).reshape(-1)[: self.n_machines]
        if a.shape[0] < self.n_machines:
            a = np.concatenate([a, np.zeros(self.n_machines - a.shape[0], dtype=np.int8)])
        a = (a > 0).astype(np.int8)
        return np.maximum(self.get_forced_mask(), a & self.get_action_mask()).astype(np.int8)

    def step(self, action: Sequence[int]) -> np.ndarray:
        eff = self.effective_action(action)
        for i, m in enumerate(self.machines):
            m.step(int(eff[i]))
        self.t += 1
        return eff

    def get_total_load_w(self) -> float:
        return float(sum(m.power_w * m.current_state for m in self.machines))

    def get_state_vector(self) -> np.ndarray:
        """Sisa runtime tiap mesin, dinormalisasi ke [0, 1]."""
        return np.array(
            [m.remaining_slots / max(m.daily_runtime_slots, 1) for m in self.machines],
            dtype=np.float32,
        )


# ── Validasi & simulasi jadwal ─────────────────────────────────────────────

def schedule_blocks(column: np.ndarray) -> list[tuple[int, int]]:
    """Blok ON [start, end) dari satu kolom jadwal 0/1."""
    col = np.asarray(column).astype(np.int8).reshape(-1)
    blocks: list[tuple[int, int]] = []
    start: Optional[int] = None
    for t, v in enumerate(col):
        if v and start is None:
            start = t
        elif not v and start is not None:
            blocks.append((start, t))
            start = None
    if start is not None:
        blocks.append((start, len(col)))
    return blocks


def validate_schedule(machines: Sequence[FlexibleMachine], schedule: np.ndarray) -> list[str]:
    """Daftar pelanggaran (kosong = jadwal sah dan semua pesanan tepat waktu)."""
    sched = np.asarray(schedule)
    if sched.shape != (N_SLOTS, len(machines)):
        return [f"bentuk jadwal {sched.shape} ≠ ({N_SLOTS}, {len(machines)})"]
    errors: list[str] = []
    for i, m in enumerate(machines):
        col = sched[:, i]
        if np.any((col != 0) & (col != 1)):
            errors.append(f"{m.machine_id}: nilai jadwal harus 0/1")
            continue
        total = int(col.sum())
        if total != m.daily_runtime_slots:
            errors.append(f"{m.machine_id}: runtime {total} slot ≠ wajib {m.daily_runtime_slots} slot")
        outside = [t for t in np.flatnonzero(col) if not m.in_window(int(t))]
        if outside:
            errors.append(f"{m.machine_id}: menyala di luar jendela (slot {outside[0]})")
        blocks = schedule_blocks(col)
        for s, e in blocks:
            if e - s < m.min_run:
                errors.append(f"{m.machine_id}: blok {slot_label(s)}–{slot_label(e)} < minimal {m.min_run} slot")
        for (_, e1), (s2, _) in zip(blocks, blocks[1:]):
            if s2 - e1 < m.cooldown_slots:
                errors.append(f"{m.machine_id}: jeda {s2 - e1} slot < cooldown {m.cooldown_slots} slot")
    return errors


@dataclass
class DispatchProblem:
    """Satu hari penjadwalan: mesin, kurva PV, beban dasar, tarif, baterai."""

    machines: List[FlexibleMachine]
    pv_w: np.ndarray                 # (96,) W AC
    base_load_w: np.ndarray          # (96,) W beban dasar (tanpa mesin terjadwal)
    tariff_idr_per_wh: np.ndarray    # (96,) Rp/Wh
    battery: Optional[Battery] = None
    target_date: Optional[date] = None
    kwp: float = 0.0
    pv_source: str = "none"

    def __post_init__(self) -> None:
        self.pv_w = np.asarray(self.pv_w, dtype=np.float64).reshape(N_SLOTS)
        self.base_load_w = np.asarray(self.base_load_w, dtype=np.float64).reshape(N_SLOTS)
        self.tariff_idr_per_wh = np.asarray(self.tariff_idr_per_wh, dtype=np.float64).reshape(N_SLOTS)

    @property
    def n_machines(self) -> int:
        return len(self.machines)

    @property
    def machine_ids(self) -> list[str]:
        return [m.machine_id for m in self.machines]

    @property
    def power_w(self) -> np.ndarray:
        return np.array([m.power_w for m in self.machines], dtype=np.float64)

    @property
    def has_battery(self) -> bool:
        return self.battery is not None and self.battery.capacity_wh > 0

    def fresh_machines(self) -> list[FlexibleMachine]:
        return [m.clone() for m in self.machines]

    def fresh_battery(self) -> Optional[Battery]:
        if not self.has_battery:
            return None
        b = copy.deepcopy(self.battery)
        b.reset()
        return b


@dataclass
class SimResult:
    load_w: np.ndarray
    grid_w: np.ndarray
    curtail_w: np.ndarray
    cost_slot_idr: np.ndarray
    cost_idr: float
    soc_wh: Optional[np.ndarray]
    grid_kwh: float
    pv_used_kwh: float
    curtail_kwh: float


def simulate_schedule(
    problem: DispatchProblem,
    schedule: np.ndarray,
    extra_load_w: Optional[np.ndarray] = None,
) -> SimResult:
    """
    Evaluasi biaya satu jadwal dengan PV, beban dasar, tarif, dan baterai
    yang sama. Baterai mulai dari SoC awal yang sama setiap evaluasi.
    """
    sched = np.asarray(schedule, dtype=np.float64).reshape(N_SLOTS, problem.n_machines)
    load = problem.base_load_w + (sched @ problem.power_w if problem.n_machines else 0.0)
    if extra_load_w is not None:
        load = load + np.asarray(extra_load_w, dtype=np.float64)
    net = problem.pv_w - load
    battery = problem.fresh_battery()
    if battery is not None:
        run = battery.run(net, dt_h=SLOT_HOURS, reset=True)
        grid_wh, curtail_wh, soc = run.grid_import_wh, run.curtail_wh, run.soc_wh
    else:
        grid_wh = np.clip(-net, 0.0, None) * SLOT_HOURS
        curtail_wh = np.clip(net, 0.0, None) * SLOT_HOURS
        soc = None
    cost_slot = grid_wh * problem.tariff_idr_per_wh
    pv_wh = problem.pv_w * SLOT_HOURS
    return SimResult(
        load_w=load,
        grid_w=grid_wh / SLOT_HOURS,
        curtail_w=curtail_wh / SLOT_HOURS,
        cost_slot_idr=cost_slot,
        cost_idr=float(cost_slot.sum()),
        soc_wh=soc,
        grid_kwh=float(grid_wh.sum() / 1000.0),
        pv_used_kwh=float((pv_wh - curtail_wh).sum() / 1000.0),
        curtail_kwh=float(curtail_wh.sum() / 1000.0),
    )

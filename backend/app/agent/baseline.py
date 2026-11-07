"""
Jadwal pembanding untuk agen WASKITA.

- ``habit_schedule``: **kebiasaan lama pemilik** — tiap mesin mulai di
  ``habit_start_hour`` (default ``settings.default_habit_start_hour``) lalu
  jalan terus sampai runtime terpenuhi. Bila blok itu keluar dari jam kerja
  mesin, blok digeser masuk ke jam kerja (runtime tetap utuh, sehingga
  baseline dan agen mengerjakan pekerjaan yang sama).
- ``habit_idle_load_w``: beban mesin yang dibiarkan menyala tanpa beban
  (``idle_minutes_habit``) dalam kebiasaan lama — hanya ada di baseline.
- ``greedy_schedule``: heuristik cepat tanpa solver. Tiap mesin mendapat SATU
  blok kontinu di dalam jendela kerjanya yang menyerap surplus PV terbanyak;
  bila tidak ada PV (kWp = 0) blok diletakkan di jam kebiasaan lama.
  Selalu memenuhi deadline, blok minimum, dan cooldown.
"""
from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from app.core.tariff import N_SLOTS
from app.digital_twin.factory_model import DispatchProblem, FlexibleMachine, machine_from_job


def _as_machines(jobs: Sequence[Any]) -> list[FlexibleMachine]:
    return [j if isinstance(j, FlexibleMachine) else machine_from_job(j) for j in jobs]


def habit_schedule(jobs: Sequence[Any], n_slots: int = N_SLOTS) -> np.ndarray:
    """Jadwal kebiasaan lama, shape (n_slots, n_jobs) int8."""
    machines = _as_machines(jobs)
    sched = np.zeros((n_slots, len(machines)), dtype=np.int8)
    for i, m in enumerate(machines):
        r = m.daily_runtime_slots
        if r <= 0:
            continue
        start = m.habit_block_start()
        sched[start:start + r, i] = 1
    return sched


def habit_idle_slots(machine: FlexibleMachine, n_slots: int = N_SLOTS) -> np.ndarray:
    """
    Slot idle kebiasaan lama (bool, n_slots): tepat setelah blok kerja, sisanya
    (bila melewati tengah malam) sebelum blok kerja.
    """
    idle = np.zeros(n_slots, dtype=bool)
    k = min(machine.idle_slots_habit, n_slots - machine.daily_runtime_slots)
    if k <= 0:
        return idle
    if machine.daily_runtime_slots > 0:
        start = machine.habit_block_start()
        end = start + machine.daily_runtime_slots
    else:
        start = end = machine.habit_block_start()
    after = min(k, n_slots - end)
    idle[end:end + after] = True
    before = k - after
    if before > 0:
        idle[max(start - before, 0):start] = True
    return idle


def habit_idle_load_w(jobs: Sequence[Any], n_slots: int = N_SLOTS) -> np.ndarray:
    """Beban idle kebiasaan lama (W, shape (n_slots,))."""
    machines = _as_machines(jobs)
    load = np.zeros(n_slots, dtype=np.float64)
    for m in machines:
        if m.idle_slots_habit > 0 and m.idle_power_w > 0:
            load[habit_idle_slots(m, n_slots)] += m.idle_power_w
    return load


def greedy_schedule(problem: DispatchProblem) -> np.ndarray:
    """Heuristik satu-blok-per-mesin yang mengejar surplus PV (lihat docstring modul)."""
    machines = problem.machines
    sched = np.zeros((N_SLOTS, len(machines)), dtype=np.int8)
    surplus = problem.pv_w - problem.base_load_w
    has_pv = bool(np.any(problem.pv_w > 0))

    # Mesin tetap lebih dulu (jadwalnya tidak bisa diubah), lalu mesin fleksibel dari daya terbesar.
    order = sorted(range(len(machines)), key=lambda i: (machines[i].is_flexible, -machines[i].power_w))
    for i in order:
        m = machines[i]
        r = m.daily_runtime_slots
        if r <= 0:
            continue
        habit = m.habit_block_start()
        lo, hi = m.earliest_slot, m.deadline_slot - r
        best_start, best_key = lo, None
        for s in range(lo, hi + 1):
            absorbed = float(np.minimum(np.clip(surplus[s:s + r], 0.0, None), m.power_w).sum()) if has_pv else 0.0
            key = (round(absorbed, 3), -abs(s - habit))
            if best_key is None or key > best_key:
                best_start, best_key = s, key
        sched[best_start:best_start + r, i] = 1
        surplus[best_start:best_start + r] -= m.power_w
    return sched

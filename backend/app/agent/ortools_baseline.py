"""
Penjadwal optimal (MILP/CP-SAT, Google OR-Tools) untuk satu hari.

Variabel: ``x[i,t] ∈ {0,1}`` mesin i ON di slot t (hanya di jendela kerjanya).

Constraint (sama persis dengan aturan ``factory_model``):
- Σ_t x[i,t] = runtime_i, x = 0 di luar ``[earliest, deadline)``.
- Blok minimum: bila mesin mulai (x[t]=1, x[t-1]=0) maka x[t..t+L-1] = 1;
  mulai yang tidak muat sebelum deadline dilarang.
- Cooldown: bila mesin berhenti (x[t-1]=1, x[t]=0) maka x[t..t+C-1] = 0.
- Neraca daya per slot (W, integer):
  ``pv + grid + discharge = beban + charge + curtail`` (semua ≥ 0).
  Tanpa baterai ini setara ``grid = max(0, beban − pv)``.
- Baterai (opsional, linear): SoC dalam mWh integer,
  ``soc[t] = soc[t-1] + round(250·η_c)·charge − round(250/η_d)·discharge``,
  ``soc_min ≤ soc ≤ kapasitas``, charge hanya dari PV (``charge ≤ pv``),
  batas daya charge/discharge. Koefisien efisiensi dibulatkan ke 0,4 %.

Objective (integer aman, ≤ ~1e11): Σ_t round(tarif_Rp/Wh·0,25·10⁴)·grid[t]
+ penalti kecil jumlah start (Rp 1/start) + bias sangat kecil (Rp 0,05/slot)
untuk slot di luar blok kebiasaan lama. Dua suku terakhir hanya pemecah seri:
bila menggeser jadwal tidak menghemat apa pun (mis. kWp = 0 dengan tarif
flat), solver memilih jadwal yang sama dengan kebiasaan pemilik.

Biaya yang DILAPORKAN ke pengguna selalu berasal dari
``factory_model.simulate_schedule`` (model ``Battery`` yang sama untuk semua
penjadwal), bukan dari objective MILP ini — objective baterai MILP bisa sedikit
lebih optimistis daripada aturan baterai greedy di simulator.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from ortools.sat.python import cp_model

from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS
from app.digital_twin.factory_model import DispatchProblem

COST_SCALE = 10_000          # 1 unit objective = Rp 0,0001
START_PENALTY_IDR = 1.0
HABIT_BIAS_IDR_PER_SLOT = 0.05

_STATUS = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}


@dataclass
class MilpResult:
    schedule: Optional[np.ndarray]   # (96, n) int8, None bila tidak ada solusi
    objective_cost_idr: float        # biaya energi menurut model MILP (tanpa penalti)
    status: str
    solve_time_s: float


def solve_milp_schedule(
    problem: DispatchProblem,
    time_limit_s: Optional[float] = None,
    num_workers: int = 8,
    start_penalty_idr: float = START_PENALTY_IDR,
    habit_bias_idr_per_slot: float = HABIT_BIAS_IDR_PER_SLOT,
) -> MilpResult:
    t0 = time.perf_counter()
    machines = problem.machines
    n = len(machines)
    model = cp_model.CpModel()

    # ── variabel jadwal ───────────────────────────────────────────────────
    x: list[list] = []
    starts = []
    habit_dev_terms = []
    for i, m in enumerate(machines):
        row: list = [0] * N_SLOTS
        r = m.daily_runtime_slots
        if r > 0:
            for t in range(m.earliest_slot, m.deadline_slot):
                row[t] = model.new_bool_var(f"x_{i}_{t}")
        x.append(row)
        if r <= 0:
            continue
        model.add(sum(row[t] for t in range(m.earliest_slot, m.deadline_slot)) == r)

        L, C = m.min_run, m.cooldown_slots
        machine_starts: list = []
        for t in range(m.earliest_slot, m.deadline_slot):
            prev = row[t - 1] if t > 0 else 0
            # Indikator start (dipakai di objective; minimisasi mendorongnya ke nilai pasnya).
            s = model.new_bool_var(f"s_{i}_{t}")
            model.add(s >= row[t] - prev)
            model.add(s <= row[t])
            if not isinstance(prev, int):
                model.add(s <= 1 - prev)
            starts.append(s)
            machine_starts.append(s)
            # Blok minimum.
            for j in range(1, L):
                k = t + j
                if k >= m.deadline_slot:
                    model.add(row[t] - prev <= 0)
                    break
                model.add(row[t] - prev - row[k] <= 0)
        model.add(sum(machine_starts) >= 1)
        # Cooldown setelah berhenti di slot t (x[t-1]=1, x[t]=0).
        if C > 1:
            for t in range(m.earliest_slot + 1, m.deadline_slot):
                for j in range(1, C):
                    k = t + j
                    if k >= m.deadline_slot:
                        break
                    model.add(row[t - 1] - row[t] + row[k] <= 1)

        if habit_bias_idr_per_slot > 0:
            hs = m.habit_block_start()
            for t in range(m.earliest_slot, m.deadline_slot):
                if not (hs <= t < hs + r):
                    habit_dev_terms.append(row[t])

    # ── neraca daya ───────────────────────────────────────────────────────
    power = [int(round(m.power_w)) for m in machines]
    pv = [int(math.floor(max(float(v), 0.0))) for v in problem.pv_w]
    base = [int(math.ceil(max(float(v), 0.0))) for v in problem.base_load_w]
    coef = [int(round(float(c) * SLOT_HOURS * COST_SCALE)) for c in problem.tariff_idr_per_wh]
    max_load = max(base) + sum(power)

    battery = problem.battery if problem.has_battery else None
    has_pv = any(v > 0 for v in pv)
    grid_vars = []
    cost_terms = []
    if not has_pv and battery is None:
        # grid = beban (tanpa PV/baterai): biaya energi tidak bergantung jadwal kecuali tarif berbeda per jam.
        for t in range(N_SLOTS):
            load_t = base[t] + sum(power[i] * x[i][t] for i in range(n))
            cost_terms.append(coef[t] * load_t)
    else:
        if battery is not None:
            eta_c, eta_d = battery.eta_charge, battery.eta_discharge
            k_c = int(round(SLOT_HOURS * 1000 * eta_c))
            k_d = int(round(SLOT_HOURS * 1000 / eta_d))
            soc_min = int(math.ceil(battery.soc_min_wh * 1000))
            soc_max = int(math.floor(battery.soc_max_wh * 1000))
            soc_prev = int(round(battery.capacity_wh * battery.soc_init_frac * 1000))
            max_c = int(math.floor(battery.max_charge_w))
            max_d = int(math.floor(battery.max_discharge_w))
        for t in range(N_SLOTS):
            load_t = base[t] + sum(power[i] * x[i][t] for i in range(n))
            grid = model.new_int_var(0, max_load, f"g_{t}")
            curt = model.new_int_var(0, max(pv[t], 0), f"c_{t}")
            if battery is not None:
                ch = model.new_int_var(0, min(max_c, pv[t]), f"ch_{t}")
                dis = model.new_int_var(0, max_d, f"dis_{t}")
                soc = model.new_int_var(soc_min, max(soc_max, soc_min), f"soc_{t}")
                model.add(soc == soc_prev + k_c * ch - k_d * dis)
                soc_prev = soc
                model.add(pv[t] + grid + dis == load_t + ch + curt)
            else:
                model.add(pv[t] + grid == load_t + curt)
            grid_vars.append(grid)
            cost_terms.append(coef[t] * grid)

    penalty_terms = []
    if start_penalty_idr > 0 and starts:
        penalty_terms.append(int(round(start_penalty_idr * COST_SCALE)) * sum(starts))
    if habit_bias_idr_per_slot > 0 and habit_dev_terms:
        penalty_terms.append(int(round(habit_bias_idr_per_slot * COST_SCALE)) * sum(habit_dev_terms))

    # Leksikografis: (1) biaya energi minimum, (2) dengan biaya itu, jadwal paling
    # sedikit start & paling dekat kebiasaan lama. Fase 2 hanya memperhalus.
    budget = float(time_limit_s if time_limit_s is not None else settings.ortools_time_limit_s)
    energy_expr = sum(cost_terms)
    model.minimize(energy_expr)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(budget * 0.7, 0.05)
    solver.parameters.num_workers = max(1, int(num_workers))
    status = solver.solve(model)
    status_str = _STATUS.get(status, "UNKNOWN")

    def _extract(s: cp_model.CpSolver) -> np.ndarray:
        out = np.zeros((N_SLOTS, n), dtype=np.int8)
        for i in range(n):
            for t in range(N_SLOTS):
                v = x[i][t]
                out[t, i] = 0 if isinstance(v, int) else int(s.value(v))
        return out

    schedule = None
    energy_cost = float("nan")
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        schedule = _extract(solver)
        best_energy = int(round(solver.objective_value))
        energy_cost = best_energy / COST_SCALE
        remaining = budget - (time.perf_counter() - t0)
        if penalty_terms and remaining > 0.05:
            for i in range(n):
                for t in range(N_SLOTS):
                    if not isinstance(x[i][t], int):
                        model.add_hint(x[i][t], int(schedule[t, i]))
            model.add(energy_expr <= best_energy)
            model.minimize(sum(penalty_terms))
            solver2 = cp_model.CpSolver()
            solver2.parameters.max_time_in_seconds = remaining
            solver2.parameters.num_workers = max(1, int(num_workers))
            if solver2.solve(model) in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                schedule = _extract(solver2)
    return MilpResult(
        schedule=schedule,
        objective_cost_idr=energy_cost,
        status=status_str,
        solve_time_s=time.perf_counter() - t0,
    )

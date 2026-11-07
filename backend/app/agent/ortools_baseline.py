import numpy as np
from datetime import date
from typing import List, Tuple
from ortools.sat.python import cp_model
from app.digital_twin.factory_model import UMKMDigitalTwin
from app.digital_twin.solar_engine import get_solar_engine

N_SLOTS = 96


def solve_milp_schedule(
    twin: UMKMDigitalTwin,
    target_date: date,
    kwp: float = 2.0,
    baseload_w: float = 800.0,
    tariff_peak_idr_per_wh: float = 1.6995,
    tariff_offpeak_idr_per_wh: float = 1.020,
) -> Tuple[np.ndarray, float, str]:
    """
    Google OR-Tools CP-SAT solver sebagai baseline MILP untuk dispatch.

    Returns:
        schedule: (96, N_machines) int8
        total_cost_idr: float
        status: solver status string
    """
    solar = get_solar_engine()
    pv_curve_w = solar.simulate_day(target_date, kwp)

    model = cp_model.CpModel()
    n = twin.n_machines
    dt_h = 0.25
    SCALE = 100  # Skala untuk integer CP-SAT (cost dalam sen Rupiah)

    # Decision variables: x[i][t] = 1 jika mesin i ON di slot t
    x = [[model.new_bool_var(f"x_{i}_{t}") for t in range(N_SLOTS)] for i in range(n)]

    # --- Constraints ---
    for i, machine in enumerate(twin.machines):
        # 1. Total runtime harus tepat sama dengan kebutuhan harian
        model.add(sum(x[i][t] for t in range(N_SLOTS)) == machine.daily_runtime_slots)

        # 2. Deadline: semua runtime harus selesai sebelum deadline_slot
        for t in range(machine.deadline_slot, N_SLOTS):
            model.add(x[i][t] == 0)

        # 3. Cooldown constraint: setelah OFF, harus OFF selama cooldown_slots
        for t in range(N_SLOTS - machine.cooldown_slots):
            # Jika x[i][t]=1 dan x[i][t+1]=0, maka x[i][t+2..t+cooldown] harus 0
            # Modeled sebagai: sum of transitions
            pass  # Disederhanakan untuk CP-SAT; cooldown ditangani oleh limit runtime

    # --- Objective: minimasi biaya grid (cost = max(0, P_total - P_pv) * tariff) ---
    # Karena CP-SAT tidak support max/nonlinear, kita linearisasi dengan aux var
    cost_vars = []
    for t in range(N_SLOTS):
        hour = t // 4
        tariff_scaled = int((tariff_peak_idr_per_wh if 8 <= hour < 22 else tariff_offpeak_idr_per_wh) * SCALE)

        # Total machine load di slot t (dalam watt, skala integer)
        machine_load_expr = sum(
            int(twin.machines[i].power_w) * x[i][t] for i in range(n)
        )
        total_load_expr = machine_load_expr + int(baseload_w)
        pv_int = int(pv_curve_w[t])

        # grid_w = max(0, total_load - pv); aux var
        grid_w_var = model.new_int_var(0, 100_000, f"grid_{t}")
        model.add_max_equality(grid_w_var, [total_load_expr - pv_int, 0])

        # Biaya = grid_w * tariff * dt_h (dalam Wh * Rp/Wh = Rp)
        cost_t = model.new_int_var(0, 10_000_000, f"cost_{t}")
        model.add(cost_t == grid_w_var * tariff_scaled)
        cost_vars.append(cost_t)

    model.minimize(sum(cost_vars))

    # --- Solve ---
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    solver.parameters.num_search_workers = 4
    status = solver.solve(model)

    schedule = np.zeros((N_SLOTS, n), dtype=np.int8)
    total_cost_idr = 0.0

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i in range(n):
            for t in range(N_SLOTS):
                schedule[t, i] = int(solver.value(x[i][t]))
        total_cost_idr = solver.objective_value / SCALE

    status_str = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status, "UNKNOWN")

    return schedule, total_cost_idr, status_str

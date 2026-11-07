"""
Perencana harian WASKITA (tahap "Atur") — kontrak CONTRACTS.md §4.

``plan_day`` membangun ``DispatchProblem`` (PV dari tiruan digital, beban
dasar, tarif dari ``app.core.tariff``, baterai opsional), menyusun jadwal
dengan solver yang diminta, lalu membandingkannya dengan **kebiasaan lama**
pemilik pada PV & baterai yang SAMA.

Urutan solver:
- ``auto``  : PPO (bila model terlatih tersedia, jumlah mesin muat, jadwal lolos
  validasi, dan tidak lebih mahal dari kebiasaan lama tanpa idle) → OR-Tools →
  greedy.
- ``ppo``   : PPO → OR-Tools → greedy.
- ``ortools``: OR-Tools → greedy.
- ``greedy``: greedy.

Setiap jadwal divalidasi ulang (``validate_schedule``); ``deadlines_met`` hanya
True bila semua mesin menyelesaikan runtime-nya di jendela kerja.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence

import numpy as np

from app.agent.baseline import greedy_schedule, habit_idle_load_w, habit_schedule
from app.core.config import settings
from app.core.tariff import N_SLOTS, tariff_curve_idr_per_wh
from app.digital_twin.battery import Battery
from app.digital_twin.factory_model import (
    DispatchProblem,
    FlexibleMachine,
    UMKMDigitalTwin,
    machine_from_job,
    simulate_schedule,
    validate_schedule,
)

logger = logging.getLogger(__name__)

SOLVERS = ("auto", "ortools", "ppo", "greedy")
SOLVER_LABELS = {"ppo": "PPO-RL", "greedy": "Greedy-Solar"}

__all__ = ["PlanResult", "plan_day", "habit_schedule", "build_problem", "default_jobs", "SOLVERS"]


@dataclass
class PlanResult:
    schedule: np.ndarray          # (96, n_machines) int8
    machine_ids: list[str]
    load_w: np.ndarray            # (96,) total beban termasuk baseload, W
    pv_w: np.ndarray              # (96,) W
    grid_w: np.ndarray            # (96,) W impor PLN
    curtail_w: np.ndarray         # (96,) W PV tak terpakai (tidak dikreditkan, Permen ESDM 2/2024)
    cost_idr: float
    baseline_load_w: np.ndarray   # (96,) kebiasaan lama
    baseline_cost_idr: float
    savings_idr: float
    savings_pct: float
    solver_used: str
    deadlines_met: bool
    battery_soc_wh: Optional[np.ndarray]
    # ── tambahan (di luar kontrak minimum) ────────────────────────────────
    target_date: Optional[date] = None
    machines: list[FlexibleMachine] = field(default_factory=list)
    baseline_schedule: Optional[np.ndarray] = None
    baseline_grid_w: Optional[np.ndarray] = None
    baseline_no_idle_cost_idr: float = 0.0
    idle_savings_idr: float = 0.0
    shifting_savings_idr: float = 0.0
    tariff_idr_per_wh: Optional[np.ndarray] = None
    pv_source: str = "none"
    kwp: float = 0.0
    violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    grid_kwh: float = 0.0
    pv_used_kwh: float = 0.0
    curtail_kwh: float = 0.0
    baseline_grid_kwh: float = 0.0


def default_jobs() -> list:
    """Contoh mesin UMKM (MachineJob) — ASUMSI untuk demo, bukan hasil ukur."""
    from app.schemas.dispatch import MachineJob

    return [MachineJob(**t) for t in UMKMDigitalTwin.DEFAULT_JOB_TEMPLATES]


def build_problem(
    jobs: Sequence[Any],
    target_date: date,
    kwp: float = 0.0,
    baseload_w: Optional[float] = None,
    battery: Optional[Battery] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    solar: Any = None,
) -> DispatchProblem:
    machines = [j if isinstance(j, FlexibleMachine) else machine_from_job(j) for j in jobs]
    machines = [m.clone() for m in machines]
    pv_source = "none"
    if kwp > 0:
        if solar is None:
            from app.digital_twin.solar_engine import get_solar_engine

            solar = get_solar_engine()
        pv = np.asarray(solar.simulate_day(target_date, kwp, lat=lat, lon=lon), dtype=np.float64)
        pv_source = str(getattr(solar, "last_source", "unknown"))
    else:
        pv = np.zeros(N_SLOTS, dtype=np.float64)
    base = settings.default_baseload_w if baseload_w is None else float(baseload_w)
    return DispatchProblem(
        machines=machines,
        pv_w=np.clip(pv, 0.0, None),
        base_load_w=np.full(N_SLOTS, base, dtype=np.float64),
        tariff_idr_per_wh=tariff_curve_idr_per_wh(N_SLOTS),
        battery=battery,
        target_date=target_date,
        kwp=float(kwp),
        pv_source=pv_source,
    )


def _try_ppo(problem: DispatchProblem, notes: list[str]) -> Optional[np.ndarray]:
    try:
        from app.agent.ppo_scheduler import get_ppo_scheduler

        scheduler = get_ppo_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Agen PPO tidak bisa dimuat: %s", exc)
        notes.append("Agen PPO tidak tersedia; memakai penjadwal cadangan.")
        return None
    if not scheduler.is_ready:
        notes.append(f"Agen PPO belum siap ({scheduler.status}); memakai penjadwal cadangan.")
        return None
    if problem.n_machines > scheduler.n_max_machines:
        notes.append(
            f"Agen PPO dilatih untuk maks. {scheduler.n_max_machines} mesin; "
            f"permintaan berisi {problem.n_machines} mesin → memakai OR-Tools."
        )
        return None
    try:
        return scheduler.schedule(problem)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agen PPO gagal menjadwalkan.")
        notes.append(f"Agen PPO gagal ({exc.__class__.__name__}); memakai penjadwal cadangan.")
        return None


def _try_ortools(problem: DispatchProblem, notes: list[str]) -> tuple[Optional[np.ndarray], str]:
    try:
        from app.agent.ortools_baseline import solve_milp_schedule

        res = solve_milp_schedule(problem)
    except Exception as exc:  # noqa: BLE001
        logger.exception("OR-Tools gagal.")
        notes.append(f"OR-Tools gagal ({exc.__class__.__name__}); memakai greedy.")
        return None, ""
    if res.schedule is None:
        notes.append(f"OR-Tools tidak menemukan jadwal (status {res.status}); memakai greedy.")
        return None, ""
    if res.status == "FEASIBLE":
        notes.append("OR-Tools berhenti di batas waktu; jadwal layak tetapi belum terbukti optimal.")
    return res.schedule, f"OR-Tools-{res.status}"


def _choose_schedule(
    problem: DispatchProblem, solver: str, habit_no_idle_cost: float, notes: list[str]
) -> tuple[np.ndarray, str]:
    machines = problem.machines

    if solver in ("auto", "ppo"):
        sched = _try_ppo(problem, notes)
        if sched is not None:
            errs = validate_schedule(machines, sched)
            if errs:
                notes.append("Jadwal PPO melanggar batasan (" + errs[0] + "); beralih ke OR-Tools.")
            else:
                cost = simulate_schedule(problem, sched).cost_idr
                if solver == "auto" and cost > habit_no_idle_cost + 0.5:
                    notes.append(
                        "Jadwal PPO lebih mahal daripada kebiasaan lama tanpa idle; beralih ke OR-Tools."
                    )
                else:
                    return sched, SOLVER_LABELS["ppo"]

    if solver in ("auto", "ppo", "ortools"):
        sched, label = _try_ortools(problem, notes)
        if sched is not None:
            errs = validate_schedule(machines, sched)
            if not errs:
                return sched, label
            notes.append("Jadwal OR-Tools melanggar batasan (" + errs[0] + "); beralih ke greedy.")

    return greedy_schedule(problem), SOLVER_LABELS["greedy"]


def plan_day(
    jobs: list,
    target_date: date,
    kwp: float = 0.0,
    baseload_w: Optional[float] = None,
    battery: Optional[Battery] = None,
    solver: str = "auto",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> PlanResult:
    if solver not in SOLVERS:
        raise ValueError(f"solver harus salah satu dari {SOLVERS}")
    problem = build_problem(jobs, target_date, kwp, baseload_w, battery, lat, lon)
    machines = problem.machines
    notes: list[str] = []

    habit = habit_schedule(machines)
    idle_w = habit_idle_load_w(machines)
    base_sim = simulate_schedule(problem, habit, extra_load_w=idle_w)
    habit_no_idle = simulate_schedule(problem, habit)

    if machines:
        schedule, solver_used = _choose_schedule(problem, solver, habit_no_idle.cost_idr, notes)
    else:
        schedule, solver_used = np.zeros((N_SLOTS, 0), dtype=np.int8), "none"
    violations = validate_schedule(machines, schedule)
    sim = simulate_schedule(problem, schedule)

    savings = base_sim.cost_idr - sim.cost_idr
    savings_pct = savings / base_sim.cost_idr * 100.0 if base_sim.cost_idr > 0 else 0.0
    idle_savings = base_sim.cost_idr - habit_no_idle.cost_idr
    shifting_savings = habit_no_idle.cost_idr - sim.cost_idr

    # ── catatan jujur untuk pengguna ───────────────────────────────────────
    idle_minutes = sum(m.idle_slots_habit * 15 for m in machines if m.idle_power_w > 0)
    tariff_flat = float(np.ptp(problem.tariff_idr_per_wh)) < 1e-12
    if tariff_flat and kwp <= 0 and not problem.has_battery:
        notes.append(
            f"Tarif PLN {settings.tariff_group} flat dan belum ada PLTS/baterai: menggeser jam mesin "
            "tidak mengubah biaya. Penghematan hanya dari mematikan mesin yang menyala tanpa beban (idle)."
        )
    if idle_minutes > 0:
        notes.append(
            f"Kebiasaan lama dihitung dengan mesin idle total {idle_minutes} menit "
            f"(daya idle default {settings.default_idle_power_frac:.0%} daya nominal bila tidak diisi; asumsi)."
        )
    if savings < 0:
        notes.append("Jadwal agen lebih mahal daripada kebiasaan lama untuk hari ini (penghematan negatif).")
    if problem.pv_source == "clearsky_scaled":
        notes.append("Kurva PLTS memakai model clear-sky × indeks kecerahan (data cuaca NASA tidak tersedia).")
    if violations:
        notes.append("PERINGATAN: jadwal tidak memenuhi semua batasan: " + "; ".join(violations[:3]))

    return PlanResult(
        schedule=schedule.astype(np.int8),
        machine_ids=problem.machine_ids,
        load_w=sim.load_w,
        pv_w=problem.pv_w,
        grid_w=sim.grid_w,
        curtail_w=sim.curtail_w,
        cost_idr=sim.cost_idr,
        baseline_load_w=base_sim.load_w,
        baseline_cost_idr=base_sim.cost_idr,
        savings_idr=savings,
        savings_pct=savings_pct,
        solver_used=solver_used,
        deadlines_met=not violations,
        battery_soc_wh=sim.soc_wh,
        target_date=target_date,
        machines=machines,
        baseline_schedule=habit,
        baseline_grid_w=base_sim.grid_w,
        baseline_no_idle_cost_idr=habit_no_idle.cost_idr,
        idle_savings_idr=idle_savings,
        shifting_savings_idr=shifting_savings,
        tariff_idr_per_wh=problem.tariff_idr_per_wh,
        pv_source=problem.pv_source,
        kwp=float(kwp),
        violations=violations,
        notes=notes,
        grid_kwh=sim.grid_kwh,
        pv_used_kwh=sim.pv_used_kwh,
        curtail_kwh=sim.curtail_kwh,
        baseline_grid_kwh=base_sim.grid_kwh,
    )

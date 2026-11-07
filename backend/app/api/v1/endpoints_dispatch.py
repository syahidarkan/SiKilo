"""
Endpoint penjadwal mesin WASKITA (tahap "Atur").

- ``POST /dispatch/optimize`` (butuh login): jadwal per mesin untuk satu hari
  + perbandingan dengan kebiasaan lama pemilik pada PV & baterai yang sama.
- ``GET  /dispatch/default-jobs``: contoh daftar mesin (asumsi demo).
"""
from __future__ import annotations

from datetime import date

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.agent.planner import PlanResult, default_jobs, plan_day
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.tariff import SLOT_HOURS
from app.digital_twin.battery import Battery
from app.digital_twin.factory_model import schedule_blocks, slot_label
from app.models import User
from app.schemas.dispatch import (
    DefaultJobsResponse,
    DispatchRequest,
    DispatchResponse,
    MachinePlan,
    SavingsBreakdown,
    SlotSchedule,
    TimeBlock,
)

router = APIRouter(prefix="/dispatch", tags=["Dispatch"])


def _blocks(column: np.ndarray) -> list[TimeBlock]:
    return [TimeBlock(start=slot_label(s), end=slot_label(e), slots=e - s) for s, e in schedule_blocks(column)]


def plan_to_response(plan: PlanResult, target_date: date) -> DispatchResponse:
    """Ubah ``PlanResult`` menjadi respons API (dipakai juga oleh modul lain)."""
    ids = plan.machine_ids
    tariff = plan.tariff_idr_per_wh if plan.tariff_idr_per_wh is not None else np.zeros(len(plan.load_w))
    slots: list[SlotSchedule] = []
    for t in range(plan.schedule.shape[0]):
        on = [ids[i] for i in np.flatnonzero(plan.schedule[t])]
        grid_w = float(plan.grid_w[t])
        slots.append(
            SlotSchedule(
                slot_index=t,
                time_label=slot_label(t),
                machines_on=on,
                machine_id=on[0] if on else "baseload",
                state=1 if on else 0,
                p_load_w=round(float(plan.load_w[t]), 1),
                p_pv_w=round(float(plan.pv_w[t]), 1),
                p_grid_w=round(grid_w, 1),
                p_curtail_w=round(float(plan.curtail_w[t]), 1),
                battery_soc_wh=None if plan.battery_soc_wh is None else round(float(plan.battery_soc_wh[t]), 1),
                baseline_load_w=round(float(plan.baseline_load_w[t]), 1),
                tariff_idr_per_kwh=round(float(tariff[t]) * 1000.0, 2),
                cost_idr=round(grid_w * SLOT_HOURS * float(tariff[t]), 2),
            )
        )

    habit = plan.baseline_schedule
    machine_ok = {m.machine_id: True for m in plan.machines}
    for v in plan.violations:
        mid = v.split(":", 1)[0]
        if mid in machine_ok:
            machine_ok[mid] = False
    machines: list[MachinePlan] = []
    for i, m in enumerate(plan.machines):
        col = plan.schedule[:, i]
        machines.append(
            MachinePlan(
                machine_id=m.machine_id,
                label=m.label,
                power_w=m.power_w,
                is_flexible=m.is_flexible,
                runtime_minutes=m.daily_runtime_slots * 15,
                scheduled_minutes=int(col.sum()) * 15,
                window=f"{slot_label(m.job_earliest_slot)}–{slot_label(m.job_deadline_slot)}",
                blocks=_blocks(col),
                habit_blocks=_blocks(habit[:, i]) if habit is not None else [],
                idle_minutes_habit=m.idle_slots_habit * 15,
                deadline_met=machine_ok.get(m.machine_id, True),
                on_slots=[int(t) for t in np.flatnonzero(col)],
            )
        )

    return DispatchResponse(
        target_date=target_date,
        schedule=slots,
        total_grid_kwh=round(plan.grid_kwh, 3),
        total_pv_kwh=round(plan.pv_used_kwh, 3),
        total_cost_idr=round(plan.cost_idr, 0),
        baseline_cost_idr=round(plan.baseline_cost_idr, 0),
        savings_idr=round(plan.savings_idr, 0),
        savings_pct=round(plan.savings_pct, 1),
        solver_used=plan.solver_used,
        curtailment_kwh=round(plan.curtail_kwh, 3),
        deadlines_met=plan.deadlines_met,
        pv_source=plan.pv_source,
        pv_generated_kwh=round(float(np.sum(plan.pv_w)) * SLOT_HOURS / 1000.0, 3),
        baseline_grid_kwh=round(plan.baseline_grid_kwh, 3),
        machines=machines,
        savings_breakdown=SavingsBreakdown(
            idle_idr=round(plan.idle_savings_idr, 0),
            shifting_idr=round(plan.shifting_savings_idr, 0),
        ),
        tariff_scheme=settings.tariff_scheme,
        notes=plan.notes,
    )


@router.get("/default-jobs", response_model=DefaultJobsResponse)
async def get_default_jobs() -> DefaultJobsResponse:
    """Contoh daftar mesin UMKM untuk dicoba di ``/dispatch/optimize``."""
    return DefaultJobsResponse(
        jobs=default_jobs(),
        baseload_w=settings.default_baseload_w,
        work_start_hour=settings.work_start_hour,
        work_end_hour=settings.work_end_hour,
        default_habit_start_hour=settings.default_habit_start_hour,
        note=(
            "Contoh mesin konveksi/sablon/laundry. Daya, runtime, dan menit idle adalah ASUMSI demo — "
            "ganti dengan data mesin Anda (atau hasil NILM) agar perhitungan bermakna."
        ),
    )


@router.post("/optimize", response_model=DispatchResponse)
async def optimize_dispatch(
    request: DispatchRequest,
    user: User = Depends(get_current_user),
) -> DispatchResponse:
    """
    Susun jadwal mesin satu hari lalu bandingkan dengan kebiasaan lama.

    Penghematan = biaya kebiasaan lama − biaya jadwal agen, keduanya memakai
    PLTS, baterai, dan tarif yang sama; nilainya bisa negatif.
    """
    jobs = list(request.jobs) or default_jobs()
    if request.apply_order_book:
        from app.digital_twin.orders import OrderBook

        jobs = OrderBook().jobs_for(request.target_date, jobs)

    solver = request.solver
    if request.use_rl_agent is not None and request.solver == "auto":
        solver = "auto" if request.use_rl_agent else "ortools"

    battery = Battery.from_kwh(request.battery_kwh) if request.battery_kwh > 0 else None
    try:
        plan = await run_in_threadpool(
            plan_day,
            jobs,
            request.target_date,
            kwp=request.kwp_capacity,
            baseload_w=request.baseload_w,
            battery=battery,
            solver=solver,
            lat=request.latitude,
            lon=request.longitude,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    response = plan_to_response(plan, request.target_date)
    if request.apply_order_book:
        from app.digital_twin.orders import OrderBook

        response.notes.insert(0, "Pola pesanan: " + OrderBook().explain(request.target_date))
    return response

from fastapi import APIRouter, HTTPException, status
from datetime import date
import numpy as np
from app.schemas.dispatch import DispatchRequest, DispatchResponse, SlotSchedule, MachineJob
from app.digital_twin.solar_engine import get_solar_engine
from app.digital_twin.factory_model import UMKMDigitalTwin, FlexibleMachine
from app.agent.umkm_env import UMKMDispatchEnv
from app.agent.ppo_scheduler import get_ppo_scheduler
from app.agent.ortools_baseline import solve_milp_schedule
from app.core.config import settings

router = APIRouter(prefix="/dispatch", tags=["Dispatch"])

N_SLOTS = 96
TARIFF_PEAK = settings.pln_tariff_peak_idr / 1000.0
TARIFF_OFFPEAK = settings.pln_tariff_offpeak_idr / 1000.0
BASELOAD_W = 800.0


def _make_twin(jobs: list[MachineJob]) -> UMKMDigitalTwin:
    machines = [
        FlexibleMachine(
            machine_id=j.machine_id,
            appliance_class=j.appliance_class,
            label=j.label,
            power_w=j.power_w,
            daily_runtime_slots=max(1, j.daily_runtime_minutes // 15),
            deadline_slot=j.deadline_hour * 4,
        )
        for j in jobs
        if j.is_flexible
    ]
    return UMKMDigitalTwin(machines=machines)


def _build_schedule_response(
    schedule: np.ndarray,
    infos: list[dict],
    twin: UMKMDigitalTwin,
    pv_curve_w: np.ndarray,
    target_date: date,
    solver_used: str,
) -> DispatchResponse:
    slots: list[SlotSchedule] = []
    total_grid_wh = 0.0
    total_pv_wh = 0.0
    total_cost_idr = 0.0
    total_curtail_wh = 0.0

    for t in range(N_SLOTS):
        hour = t // 4
        minute = (t % 4) * 15
        time_label = f"{hour:02d}:{minute:02d}"
        tariff = TARIFF_PEAK if 8 <= hour < 22 else TARIFF_OFFPEAK
        pv_w = float(pv_curve_w[t])

        # Total load di slot ini
        p_machines_w = sum(
            twin.machines[i].power_w * int(schedule[t, i])
            for i in range(len(twin.machines))
        ) if schedule.shape[1] > 0 else 0.0
        p_total_w = p_machines_w + BASELOAD_W

        grid_w = max(0.0, p_total_w - pv_w)
        curtail_w = max(0.0, pv_w - p_total_w)
        cost_slot = grid_w * 0.25 * tariff

        total_grid_wh += grid_w * 0.25
        total_pv_wh += min(pv_w, p_total_w) * 0.25
        total_cost_idr += cost_slot
        total_curtail_wh += curtail_w * 0.25

        # Ambil mesin pertama yang ON di slot ini untuk label (simplified)
        machine_id_on = "baseload"
        for i, m in enumerate(twin.machines):
            if schedule.shape[1] > i and schedule[t, i] == 1:
                machine_id_on = m.machine_id
                break

        slots.append(SlotSchedule(
            slot_index=t,
            time_label=time_label,
            machine_id=machine_id_on,
            state=1 if p_machines_w > 0 else 0,
            p_load_w=p_total_w,
            p_pv_w=pv_w,
            p_grid_w=grid_w,
            cost_idr=cost_slot,
        ))

    # Baseline: semua mesin dinyalakan dari jam 08:00 tanpa optimasi
    baseline_cost = sum(
        (sum(m.power_w for m in twin.machines) + BASELOAD_W)
        * (TARIFF_PEAK if 8 <= (t // 4) < 22 else TARIFF_OFFPEAK)
        * 0.25
        for t in range(N_SLOTS)
    )

    savings = max(0.0, baseline_cost - total_cost_idr)
    savings_pct = (savings / baseline_cost * 100) if baseline_cost > 0 else 0.0

    return DispatchResponse(
        target_date=target_date,
        schedule=slots,
        total_grid_kwh=round(total_grid_wh / 1000.0, 3),
        total_pv_kwh=round(total_pv_wh / 1000.0, 3),
        total_cost_idr=round(total_cost_idr, 0),
        baseline_cost_idr=round(baseline_cost, 0),
        savings_idr=round(savings, 0),
        savings_pct=round(savings_pct, 1),
        solver_used=solver_used,
        curtailment_kwh=round(total_curtail_wh / 1000.0, 3),
    )


@router.post("/optimize", response_model=DispatchResponse)
async def optimize_dispatch(request: DispatchRequest) -> DispatchResponse:
    """
    Jalankan optimasi jadwal mesin untuk satu hari.
    Gunakan RL agent (PPO) atau OR-Tools MILP sebagai baseline.
    """
    solar = get_solar_engine()
    twin = _make_twin(request.jobs)

    if not twin.machines:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada mesin fleksibel dalam permintaan",
        )

    pv_curve_w = solar.simulate_day(request.target_date, request.kwp_capacity)

    if request.use_rl_agent:
        env = UMKMDispatchEnv(twin=twin, solar=solar, kwp=request.kwp_capacity, target_date=request.target_date)
        scheduler = get_ppo_scheduler()
        schedule, infos = scheduler.run_episode(env)
        solver_used = "PPO-RL" if scheduler._model is not None else "Greedy-Solar"
    else:
        schedule, _, status_str = solve_milp_schedule(
            twin=twin, target_date=request.target_date, kwp=request.kwp_capacity
        )
        infos = []
        solver_used = f"OR-Tools-{status_str}"

    twin.reset()
    return _build_schedule_response(schedule, infos, twin, pv_curve_w, request.target_date, solver_used)

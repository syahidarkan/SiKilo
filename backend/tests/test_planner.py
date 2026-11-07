"""Tes planner.plan_day, baseline kebiasaan lama, dan fallback solver."""
from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.agent import planner as planner_mod
from app.agent import ppo_scheduler
from app.agent.baseline import habit_idle_load_w, habit_schedule
from app.agent.planner import PlanResult, default_jobs, plan_day
from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS
from app.digital_twin.battery import Battery
from app.digital_twin.factory_model import validate_schedule
from app.schemas.dispatch import MachineJob

DAY = date(2025, 7, 15)
BACKEND = Path(__file__).resolve().parents[1]


def _job(mid="a", power=1000.0, minutes=120, earliest=7, deadline=17, habit=None, idle=0, **kw) -> MachineJob:
    return MachineJob(
        machine_id=mid, label=mid.upper(), appliance_class=1, power_w=power,
        daily_runtime_minutes=minutes, earliest_hour=earliest, deadline_hour=deadline,
        habit_start_hour=habit, idle_minutes_habit=idle, **kw,
    )


@pytest.fixture(autouse=True)
def no_trained_model(monkeypatch, tmp_path):
    """Tes planner tidak boleh bergantung pada model PPO/sb3 yang kebetulan ada."""
    monkeypatch.setattr(settings, "rl_model_path", str(tmp_path / "tidak_ada.zip"))
    ppo_scheduler.reset_ppo_scheduler()
    yield
    ppo_scheduler.reset_ppo_scheduler()


# ── kebiasaan lama ─────────────────────────────────────────────────────────

class TestHabitBaseline:
    def test_starts_at_habit_hour_and_runs_continuously(self):
        sched = habit_schedule([_job(minutes=150, habit=9)])
        on = np.flatnonzero(sched[:, 0])
        assert on[0] == 36 and len(on) == 10 and np.all(np.diff(on) == 1)

    def test_uses_default_habit_hour(self):
        sched = habit_schedule([_job(minutes=60)])
        assert np.flatnonzero(sched[:, 0])[0] == settings.default_habit_start_hour * 4

    def test_block_is_kept_inside_working_hours(self):
        # Mulai 16:00 dengan runtime 3 jam akan melewati deadline 17:00 → digeser ke 14:00.
        sched = habit_schedule([_job(minutes=180, habit=16)])
        on = np.flatnonzero(sched[:, 0])
        assert on[0] == 56 and on[-1] == 67

    def test_is_not_all_machines_all_day(self):
        jobs = default_jobs()
        sched = habit_schedule(jobs)
        assert sched.sum() == sum(int(np.ceil(j.daily_runtime_minutes / 15)) for j in jobs)
        assert sched.sum() < N_SLOTS * len(jobs) / 2

    def test_idle_load_follows_block(self):
        load = habit_idle_load_w([_job(power=1000, minutes=60, habit=8, idle=30, idle_power_w=300)])
        assert np.flatnonzero(load).tolist() == [36, 37]
        assert load[36] == 300


# ── plan_day ───────────────────────────────────────────────────────────────

class TestPlanDay:
    def test_contract_fields(self):
        plan = plan_day(default_jobs(), DAY, kwp=2.0, solver="ortools")
        assert isinstance(plan, PlanResult)
        n = len(default_jobs())
        assert plan.schedule.shape == (N_SLOTS, n) and plan.schedule.dtype == np.int8
        assert len(plan.machine_ids) == n
        for arr in (plan.load_w, plan.pv_w, plan.grid_w, plan.curtail_w, plan.baseline_load_w):
            assert arr.shape == (N_SLOTS,)
        assert plan.deadlines_met is True
        assert plan.battery_soc_wh is None
        assert plan.pv_source in ("nasa_power", "clearsky_scaled")
        assert plan.savings_idr == pytest.approx(plan.baseline_cost_idr - plan.cost_idr)
        assert plan.savings_pct == pytest.approx(plan.savings_idr / plan.baseline_cost_idr * 100)

    def test_flat_tariff_without_pv_only_idle_saves(self):
        if settings.tariff_scheme != "flat":
            pytest.skip("hanya berlaku untuk tarif flat")
        jobs = [_job("a", idle=0), _job("b", power=2000, habit=10, idle=60, idle_power_w=500)]
        for solver in ("greedy", "ortools"):
            plan = plan_day(jobs, DAY, kwp=0.0, solver=solver)
            assert plan.shifting_savings_idr == pytest.approx(0.0, abs=1e-6)
            expected_idle = 500 * 1.0 * settings.tariff_flat_idr_per_kwh / 1000  # 60 menit × 500 W
            assert plan.idle_savings_idr == pytest.approx(expected_idle)
            assert plan.savings_idr == pytest.approx(expected_idle)
            assert any("flat" in n for n in plan.notes)

    def test_no_idle_no_pv_means_zero_savings(self):
        plan = plan_day([_job("a"), _job("b", habit=10)], DAY, kwp=0.0, solver="ortools")
        assert plan.savings_idr == pytest.approx(0.0, abs=1e-6)

    def test_pv_shifting_saves_and_uses_same_pv(self):
        # Kebiasaan lama mulai 07:00 (PV masih lemah); agen boleh geser ke siang.
        jobs = [_job("a", power=2000, minutes=180, habit=7), _job("b", power=1500, minutes=120, habit=7)]
        plan = plan_day(jobs, DAY, kwp=4.0, solver="ortools")
        assert plan.deadlines_met
        assert plan.shifting_savings_idr > 0
        # Energi beban sama (tanpa idle) → beda biaya murni dari pemakaian PV.
        assert plan.load_w.sum() == pytest.approx(plan.baseline_load_w.sum())
        baseline_grid_cost = float(np.sum(plan.baseline_grid_w * SLOT_HOURS * plan.tariff_idr_per_wh))
        assert baseline_grid_cost == pytest.approx(plan.baseline_cost_idr)

    def test_battery_is_shared_and_soc_stays_above_minimum(self):
        bat = Battery.from_kwh(5.0)
        plan = plan_day(default_jobs(), DAY, kwp=3.0, battery=bat, solver="ortools")
        assert plan.battery_soc_wh is not None
        assert plan.battery_soc_wh.min() >= bat.soc_min_wh - 1e-6
        assert plan.deadlines_met

    def test_savings_can_be_negative(self, monkeypatch):
        jobs = [_job("a", power=2000, minutes=120, habit=11)]

        def bad_greedy(problem):  # jadwal sah tetapi di pagi hari tanpa PV
            s = np.zeros((N_SLOTS, problem.n_machines), dtype=np.int8)
            s[28:36, 0] = 1
            return s

        monkeypatch.setattr(planner_mod, "greedy_schedule", bad_greedy)
        plan = plan_day(jobs, DAY, kwp=4.0, solver="greedy")
        assert plan.deadlines_met
        assert plan.savings_idr < 0
        assert any("negatif" in n for n in plan.notes)

    def test_tou_tariff_shifts_out_of_peak_without_pv(self, monkeypatch):
        monkeypatch.setattr(settings, "tariff_scheme", "tou")
        jobs = [_job("a", power=2000, minutes=120, earliest=14, deadline=22, habit=17)]
        plan = plan_day(jobs, DAY, kwp=0.0, solver="ortools")
        on = np.flatnonzero(plan.schedule[:, 0])
        assert on.max() < settings.tariff_wbp_start_hour * 4
        assert plan.savings_idr > 0

    def test_unknown_solver_rejected(self):
        with pytest.raises(ValueError):
            plan_day(default_jobs(), DAY, solver="sihir")


# ── pemilihan solver ───────────────────────────────────────────────────────

class _FakePPO:
    def __init__(self, fn):
        self.fn = fn
        self.is_ready = True
        self.status = "siap"
        self.n_max_machines = 6

    def schedule(self, problem):
        return self.fn(problem)


class TestSolverSelection:
    def test_ppo_without_model_falls_back_to_ortools(self):
        plan = plan_day(default_jobs(), DAY, kwp=2.0, solver="ppo")
        assert plan.solver_used.startswith("OR-Tools")
        assert any("PPO" in n for n in plan.notes)

    def test_auto_rejects_ppo_that_misses_deadlines(self, monkeypatch):
        fake = _FakePPO(lambda p: np.zeros((N_SLOTS, p.n_machines), dtype=np.int8))
        monkeypatch.setattr(ppo_scheduler, "get_ppo_scheduler", lambda: fake)
        plan = plan_day(default_jobs(), DAY, kwp=2.0, solver="auto")
        assert plan.solver_used.startswith("OR-Tools")
        assert plan.deadlines_met
        assert any("melanggar" in n for n in plan.notes)

    def test_auto_uses_valid_ppo_schedule(self, monkeypatch):
        fake = _FakePPO(lambda p: habit_schedule(p.machines))
        monkeypatch.setattr(ppo_scheduler, "get_ppo_scheduler", lambda: fake)
        plan = plan_day(default_jobs(), DAY, kwp=0.0, solver="auto")
        assert plan.solver_used == "PPO-RL"
        assert validate_schedule(plan.machines, plan.schedule) == []

    def test_auto_rejects_ppo_worse_than_habit(self, monkeypatch):
        jobs = [_job("a", power=2000, minutes=120, habit=11)]

        def early(p):
            s = np.zeros((N_SLOTS, p.n_machines), dtype=np.int8)
            s[28:36, 0] = 1
            return s

        monkeypatch.setattr(ppo_scheduler, "get_ppo_scheduler", lambda: _FakePPO(early))
        plan = plan_day(jobs, DAY, kwp=4.0, solver="auto")
        assert plan.solver_used.startswith("OR-Tools")
        assert plan.savings_idr >= 0

    def test_ppo_scheduler_without_model_is_not_ready(self):
        sched = ppo_scheduler.get_ppo_scheduler()
        assert not sched.is_ready
        assert "belum dilatih" in sched.status


def test_runtime_api_does_not_import_torch():
    code = (
        "import sys; import app.agent.planner, app.api.v1.endpoints_dispatch, app.agent.ppo_scheduler; "
        "print('torch' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=str(BACKEND), capture_output=True, text=True, timeout=120,
        env={**__import__("os").environ, "PRELOAD_MODELS": "false"},
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "False"


def test_optional_bc_pipeline_produces_loadable_model(tmp_path, monkeypatch):
    """Jalan hanya bila paket RL terpasang; memastikan BC → simpan → muat → planner."""
    pytest.importorskip("sb3_contrib")
    import json

    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    from app.agent.behavior_cloning import collect_demonstrations, pretrain_policy
    from app.agent.scenarios import ScenarioSampler
    from app.agent.umkm_env import OBS_VERSION, UMKMDispatchEnv

    sampler = ScenarioSampler(4, year=2025)
    env = DummyVecEnv([lambda: UMKMDispatchEnv(problem_sampler=sampler, n_max_machines=4)])
    model = MaskablePPO("MlpPolicy", env, n_steps=96, batch_size=96, device="cpu", seed=0)
    demos = collect_demonstrations(sampler, 2, 4, seed=0, time_limit_s=2.0)
    losses = pretrain_policy(model, demos, epochs=2)
    assert len(losses) == 2 and np.isfinite(losses).all()

    zip_path, meta_path = tmp_path / "m.zip", tmp_path / "m.meta.json"
    model.save(str(zip_path))
    meta_path.write_text(json.dumps({"obs_version": OBS_VERSION, "n_max_machines": 4}), encoding="utf-8")
    monkeypatch.setattr(settings, "rl_model_path", str(zip_path))
    monkeypatch.setattr(settings, "rl_meta_path", str(meta_path))
    ppo_scheduler.reset_ppo_scheduler()
    assert ppo_scheduler.get_ppo_scheduler().is_ready
    plan = plan_day(default_jobs(), DAY, kwp=2.0, solver="ppo")
    assert plan.deadlines_met  # PPO atau fallback, deadline tetap terjamin

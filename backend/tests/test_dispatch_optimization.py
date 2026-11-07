"""Tes model mesin, env RL, OR-Tools, greedy, dan endpoint /dispatch."""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.agent.baseline import greedy_schedule, habit_schedule
from app.agent.ortools_baseline import solve_milp_schedule
from app.agent.ppo_scheduler import _greedy_solar_dispatch
from app.agent.umkm_env import UMKMDispatchEnv, obs_size
from app.core.tariff import N_SLOTS, tariff_curve_idr_per_wh
from app.digital_twin.battery import Battery
from app.digital_twin.factory_model import (
    DispatchProblem,
    FlexibleMachine,
    UMKMDigitalTwin,
    machine_from_job,
    schedule_blocks,
    simulate_schedule,
    validate_schedule,
)


def _machine(mid="m1", power=1500.0, runtime=8, earliest=28, deadline=68, min_run=1, cooldown=2,
             habit=None, flexible=True, idle=0) -> FlexibleMachine:
    return FlexibleMachine(
        machine_id=mid, appliance_class=3, label=mid, power_w=power, daily_runtime_slots=runtime,
        earliest_slot=earliest, deadline_slot=deadline, min_continuous_slots=min_run,
        cooldown_slots=cooldown, habit_start_slot=habit, is_flexible=flexible,
        idle_slots_habit=idle, idle_power_w=0.4 * power,
    )


def _bell_pv(peak_w: float = 3000.0) -> np.ndarray:
    t = np.arange(N_SLOTS)
    pv = peak_w * np.exp(-0.5 * ((t - 48) / 9.0) ** 2)
    pv[(t < 24) | (t > 72)] = 0.0
    return pv


def _problem(machines, pv=None, base=500.0, battery=None) -> DispatchProblem:
    return DispatchProblem(
        machines=machines,
        pv_w=np.zeros(N_SLOTS) if pv is None else pv,
        base_load_w=np.full(N_SLOTS, base),
        tariff_idr_per_wh=tariff_curve_idr_per_wh(),
        battery=battery,
        target_date=date(2025, 7, 15),
        kwp=0.0 if pv is None else 3.0,
    )


def _mixed_machines():
    return [
        _machine("boiler", 1500, runtime=12, min_run=4, cooldown=2, habit=32),
        _machine("dryer", 1200, runtime=8, min_run=2, cooldown=4, habit=32),
        _machine("oven", 2000, runtime=6, earliest=32, deadline=56, min_run=3, cooldown=0),
        _machine("fixed", 800, runtime=4, habit=36, flexible=False),
    ]


# ── factory_model ──────────────────────────────────────────────────────────

class TestFactoryModel:
    def test_machine_from_job_rounds_up_and_uses_defaults(self):
        m = machine_from_job({
            "machine_id": "x", "label": "X", "power_w": 1000.0, "daily_runtime_minutes": 50,
            "earliest_hour": 8, "deadline_hour": 12, "min_continuous_minutes": 40,
        })
        assert m.daily_runtime_slots == 4  # 50 menit → 4 slot (dibulatkan ke atas)
        assert (m.earliest_slot, m.deadline_slot) == (32, 48)
        assert m.min_continuous_slots == 3
        assert m.idle_power_w == pytest.approx(400.0)

    def test_runtime_longer_than_window_is_rejected(self):
        with pytest.raises(ValueError):
            _machine(runtime=50, earliest=28, deadline=68)

    def test_non_flexible_machine_is_pinned_to_habit_block(self):
        m = _machine(runtime=4, habit=36, flexible=False)
        assert (m.earliest_slot, m.deadline_slot) == (36, 40)
        assert (m.job_earliest_slot, m.job_deadline_slot) == (28, 68)

    def test_forced_on_when_slack_is_zero(self):
        m = _machine(runtime=4, earliest=28, deadline=40)
        assert not m.forced_on(30)
        assert m.forced_on(36)  # 4 slot tersisa = runtime

    def test_validate_schedule_detects_violations(self):
        m = _machine(runtime=4, min_run=2, cooldown=2)
        sched = np.zeros((N_SLOTS, 1), dtype=np.int8)
        sched[10:14, 0] = 1  # di luar jendela
        assert any("luar jendela" in e for e in validate_schedule([m], sched))
        sched[:] = 0
        sched[30, 0] = 1
        sched[32:35, 0] = 1  # blok 1 slot (< min) dan jeda 1 slot (< cooldown)
        errs = validate_schedule([m], sched)
        assert any("minimal" in e for e in errs) and any("cooldown" in e for e in errs)


# ── env ────────────────────────────────────────────────────────────────────

class TestUMKMDispatchEnv:
    def _env(self, battery=None, n_max=None):
        return UMKMDispatchEnv(
            problem=_problem(_mixed_machines(), pv=_bell_pv(), battery=battery),
            n_max_machines=n_max,
        )

    def test_reset_returns_valid_obs(self):
        env = self._env(n_max=6)
        obs, _ = env.reset()
        assert obs.shape == (obs_size(6),)
        if env.observation_space is not None:
            assert env.observation_space.contains(obs)

    @pytest.mark.parametrize("seed", range(12))
    def test_random_actions_always_meet_deadlines(self, seed):
        env = self._env(n_max=6)
        rng = np.random.default_rng(seed)
        env.reset(seed=seed)
        p_on = rng.uniform(0.05, 0.95)
        terminated = False
        steps = 0
        while not terminated:
            _, reward, terminated, _, info = env.step((rng.random(6) < p_on).astype(np.int64))
            assert reward <= 0.0
            steps += 1
        assert steps == N_SLOTS
        assert info["unmet_slots"] == 0
        assert validate_schedule(env.problem.machines, env.schedule) == []

    @pytest.mark.parametrize("seed", range(40))
    def test_random_machines_random_actions_are_always_valid(self, seed):
        """Properti: aturan mask/forced menjamin jadwal sah untuk parameter mesin apa pun."""
        rng = np.random.default_rng(1000 + seed)
        machines = []
        for k in range(int(rng.integers(1, 6))):
            earliest = int(rng.integers(0, 60))
            deadline = int(rng.integers(earliest + 1, 97))
            runtime = int(rng.integers(0, deadline - earliest + 1))
            machines.append(_machine(
                f"m{k}", float(rng.integers(100, 3000)), runtime=runtime, earliest=earliest,
                deadline=deadline, min_run=int(rng.integers(1, 9)), cooldown=int(rng.integers(0, 5)),
                habit=int(rng.integers(0, 96)), flexible=bool(rng.random() > 0.2),
            ))
        env = UMKMDispatchEnv(problem=_problem(machines, pv=_bell_pv()), n_max_machines=6)
        env.reset()
        p_on = rng.uniform(0.0, 1.0)
        for _ in range(N_SLOTS):
            env.step((rng.random(6) < p_on).astype(np.int64))
        assert validate_schedule(machines, env.schedule) == []

    def test_all_off_actions_are_forced_to_finish_at_deadline(self):
        env = self._env()
        env.reset()
        for _ in range(N_SLOTS):
            env.step(np.zeros(4, dtype=np.int64))
        for i, m in enumerate(env.problem.machines):
            col = env.schedule[:, i]
            assert col.sum() == m.daily_runtime_slots
            if m.is_flexible:
                assert col[m.deadline_slot - m.daily_runtime_slots:m.deadline_slot].all()

    def test_all_on_actions_never_leave_window(self):
        env = self._env()
        env.reset()
        for _ in range(N_SLOTS):
            env.step(np.ones(4, dtype=np.int64))
        for i, m in enumerate(env.problem.machines):
            on = np.flatnonzero(env.schedule[:, i])
            assert on.min() >= m.earliest_slot and on.max() < m.deadline_slot

    def test_action_masks_are_consistent(self):
        env = self._env(n_max=6)
        env.reset()
        for t in range(N_SLOTS):
            masks = env.action_masks().reshape(6, 2)
            assert masks.any(axis=1).all()           # selalu ada aksi sah
            assert not masks[4:, 1].any()            # slot padding tak boleh ON
            forced = env.twin.get_forced_mask().astype(bool)
            allowed = env.twin.get_action_mask().astype(bool)
            assert (masks[:4, 0] == ~forced).all()
            assert (masks[:4, 1] == (allowed | forced)).all()
            # Ambil aksi sah acak → hasil efektif harus sama dengan aksi itu.
            choice = np.array([np.random.default_rng(t + i).choice(np.flatnonzero(masks[i])) for i in range(6)])
            _, _, _, _, info = env.step(choice)
            assert (info["effective_action"] == choice[:4]).all()

    def test_cost_uses_tariff_module(self):
        env = self._env()
        env.reset()
        _, _, _, _, info = env.step(np.zeros(4, dtype=np.int64))
        assert info["cost_idr"] == pytest.approx(info["grid_wh"] * tariff_curve_idr_per_wh()[0])

    def test_battery_soc_in_obs_and_never_below_minimum(self):
        bat = Battery.from_kwh(5.0)
        env = self._env(battery=bat)
        obs, _ = env.reset()
        assert obs[7] == pytest.approx(bat.soc_init_frac)
        rng = np.random.default_rng(0)
        for _ in range(N_SLOTS):
            _, _, _, _, info = env.step(rng.integers(0, 2, 4))
            assert info["soc_wh"] >= bat.soc_min_wh - 1e-6
        assert bat.soc_wh == pytest.approx(bat.capacity_wh * bat.soc_init_frac)  # objek asli tak berubah

    def test_rejects_more_machines_than_n_max(self):
        with pytest.raises(ValueError):
            UMKMDispatchEnv(problem=_problem(_mixed_machines()), n_max_machines=2)

    def test_legacy_constructor_still_works(self):
        twin = UMKMDigitalTwin()
        env = UMKMDispatchEnv(twin=twin, kwp=0.0, target_date=date(2025, 3, 3))
        obs, _ = env.reset()
        assert obs.shape == (obs_size(twin.n_machines),)


# ── OR-Tools ───────────────────────────────────────────────────────────────

class TestOrTools:
    def test_schedule_is_valid_and_not_worse_than_heuristics(self):
        p = _problem(_mixed_machines(), pv=_bell_pv())
        res = solve_milp_schedule(p, time_limit_s=10)
        assert res.status in ("OPTIMAL", "FEASIBLE")
        assert validate_schedule(p.machines, res.schedule) == []
        c_or = simulate_schedule(p, res.schedule).cost_idr
        assert c_or <= simulate_schedule(p, greedy_schedule(p)).cost_idr + 5.0
        assert c_or <= simulate_schedule(p, habit_schedule(p.machines)).cost_idr + 5.0

    def test_cooldown_and_min_run_are_real_constraints(self):
        # PV hanya di slot berselang 2 → tanpa cooldown solver akan memecah blok.
        pv = np.zeros(N_SLOTS)
        pv[[40, 41, 44, 45, 48, 49]] = 3000.0
        m = _machine("c", 1000, runtime=4, earliest=36, deadline=56, min_run=1, cooldown=3)
        p = _problem([m], pv=pv)
        res = solve_milp_schedule(p, time_limit_s=10)
        assert validate_schedule([m], res.schedule) == []
        blocks = schedule_blocks(res.schedule[:, 0])
        assert all(s2 - e1 >= 3 for (_, e1), (s2, _) in zip(blocks, blocks[1:]))

        m2 = _machine("r", 1000, runtime=6, earliest=36, deadline=56, min_run=3, cooldown=0)
        res2 = solve_milp_schedule(_problem([m2], pv=pv), time_limit_s=10)
        assert all(e - s >= 3 for s, e in schedule_blocks(res2.schedule[:, 0]))

    @pytest.mark.parametrize("seed", range(5))
    def test_milp_schedule_replays_exactly_in_env(self, seed):
        """MILP dan mask env memakai aturan yang sama → jadwal OR-Tools lolos mask tanpa koreksi."""
        from app.agent.behavior_cloning import rollout_schedule

        rng = np.random.default_rng(seed)
        machines = [
            _machine(f"m{k}", float(rng.integers(500, 2500)), runtime=int(rng.integers(2, 16)),
                     earliest=int(rng.integers(24, 36)), deadline=int(rng.integers(52, 72)),
                     min_run=int(rng.integers(1, 5)), cooldown=int(rng.integers(0, 4)),
                     habit=int(rng.integers(28, 44)))
            for k in range(3)
        ]
        p = _problem(machines, pv=_bell_pv(float(rng.integers(2000, 7000))))
        res = solve_milp_schedule(p, time_limit_s=10)
        *_, match = rollout_schedule(p, res.schedule, n_max=4)
        assert match

    def test_zero_kwp_matches_habit_cost(self):
        p = _problem(_mixed_machines())
        res = solve_milp_schedule(p, time_limit_s=10)
        habit = habit_schedule(p.machines)
        assert simulate_schedule(p, res.schedule).cost_idr == pytest.approx(simulate_schedule(p, habit).cost_idr)
        # Pemecah seri: tanpa manfaat, solver mempertahankan kebiasaan lama.
        assert (res.schedule == habit).all()

    def test_with_battery(self):
        p = _problem(_mixed_machines(), pv=_bell_pv(5000.0), battery=Battery.from_kwh(5.0))
        res = solve_milp_schedule(p, time_limit_s=10)
        assert validate_schedule(p.machines, res.schedule) == []
        sim = simulate_schedule(p, res.schedule)
        assert sim.soc_wh.min() >= p.battery.soc_min_wh - 1e-6


# ── greedy ─────────────────────────────────────────────────────────────────

class TestGreedy:
    def test_zero_pv_keeps_habit(self):
        p = _problem(_mixed_machines())
        assert (greedy_schedule(p) == habit_schedule(p.machines)).all()

    def test_prefers_solar_and_respects_window(self):
        p = _problem(_mixed_machines(), pv=_bell_pv(6000.0))
        sched = greedy_schedule(p)
        assert validate_schedule(p.machines, sched) == []
        boiler = np.flatnonzero(sched[:, 0])
        assert 36 <= boiler.mean() <= 60  # sekitar tengah hari

    def test_greedy_dispatch_through_env(self):
        env = UMKMDispatchEnv(problem=_problem(_mixed_machines(), pv=_bell_pv()), n_max_machines=6)
        schedule, infos = _greedy_solar_dispatch(env)
        assert schedule.shape == (N_SLOTS, 4) and len(infos) == N_SLOTS
        assert validate_schedule(env.problem.machines, schedule) == []


# ── endpoint ───────────────────────────────────────────────────────────────

@pytest.fixture
def no_ppo(monkeypatch, tmp_path):
    from app.agent import ppo_scheduler
    from app.core.config import settings

    monkeypatch.setattr(settings, "rl_model_path", str(tmp_path / "tidak_ada.zip"))
    ppo_scheduler.reset_ppo_scheduler()
    yield
    ppo_scheduler.reset_ppo_scheduler()


class TestDispatchEndpoint:
    def test_requires_login(self, client):
        resp = client.post("/api/v1/dispatch/optimize", json={"target_date": "2025-07-15"})
        assert resp.status_code == 401

    def test_default_jobs(self, client):
        resp = client.get("/api/v1/dispatch/default-jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["jobs"]) >= 3
        assert all("habit_start_hour" in j for j in body["jobs"])

    def test_optimize_per_machine_response(self, client, auth_headers, no_ppo):
        resp = client.post(
            "/api/v1/dispatch/optimize",
            json={"target_date": "2025-07-15", "kwp_capacity": 3.0, "battery_kwh": 5.0},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["solver_used"].startswith("OR-Tools")
        assert body["deadlines_met"] is True
        assert body["pv_source"] in ("nasa_power", "clearsky_scaled")
        assert len(body["schedule"]) == N_SLOTS
        assert len(body["machines"]) == 4
        for m in body["machines"]:
            assert m["scheduled_minutes"] == m["runtime_minutes"]
            assert m["deadline_met"] is True
            assert m["blocks"] and m["habit_blocks"]
        # Beberapa mesin bisa ON bersamaan; daftar lengkap ada di machines_on.
        assert max(len(s["machines_on"]) for s in body["schedule"]) >= 2
        assert body["savings_idr"] == pytest.approx(body["baseline_cost_idr"] - body["total_cost_idr"], abs=1.5)
        assert body["savings_breakdown"]["idle_idr"] > 0

    def test_optimize_without_pv_explains_flat_tariff(self, client, auth_headers, no_ppo):
        jobs = [{
            "machine_id": "mesin-a", "label": "Mesin A", "appliance_class": 1, "power_w": 1000,
            "daily_runtime_minutes": 120, "habit_start_hour": 9,
        }]
        resp = client.post(
            "/api/v1/dispatch/optimize",
            json={"target_date": "2025-07-15", "jobs": jobs, "solver": "greedy"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["savings_idr"] == 0  # tanpa idle & PLTS: tidak ada penghematan palsu
        assert any("flat" in n for n in body["notes"])
        assert body["machines"][0]["blocks"] == [{"start": "09:00", "end": "11:00", "slots": 8}]

    def test_rejects_runtime_longer_than_window(self, client, auth_headers):
        jobs = [{
            "machine_id": "x", "label": "X", "power_w": 1000, "daily_runtime_minutes": 600,
            "earliest_hour": 8, "deadline_hour": 12,
        }]
        resp = client.post(
            "/api/v1/dispatch/optimize",
            json={"target_date": "2025-07-15", "jobs": jobs},
            headers=auth_headers,
        )
        assert resp.status_code == 422

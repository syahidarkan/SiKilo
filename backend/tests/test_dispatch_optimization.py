import pytest
import numpy as np
from datetime import date
from app.digital_twin.factory_model import UMKMDigitalTwin, FlexibleMachine
from app.digital_twin.solar_engine import SolarEngine
from app.agent.umkm_env import UMKMDispatchEnv
from app.agent.ppo_scheduler import _greedy_solar_dispatch


def _make_simple_twin() -> UMKMDigitalTwin:
    machines = [
        FlexibleMachine(
            machine_id="boiler-01",
            appliance_class=3,
            label="Setrika Uap",
            power_w=1500.0,
            daily_runtime_slots=12,
            deadline_slot=68,
        ),
        FlexibleMachine(
            machine_id="dryer-01",
            appliance_class=4,
            label="Drum Pengering",
            power_w=1200.0,
            daily_runtime_slots=8,
            deadline_slot=68,
        ),
    ]
    return UMKMDigitalTwin(machines=machines)


class TestUMKMDispatchEnv:
    def setup_method(self):
        self.twin = _make_simple_twin()
        self.env = UMKMDispatchEnv(
            twin=self.twin,
            solar=SolarEngine(),
            kwp=2.0,
            target_date=date(2026, 11, 7),
        )

    def test_reset_returns_valid_obs(self):
        obs, info = self.env.reset()
        assert obs.shape == self.env.observation_space.shape
        assert self.env.observation_space.contains(obs)

    def test_step_with_all_on(self):
        self.env.reset()
        n = self.twin.n_machines
        action = np.ones(n, dtype=np.int8)
        obs, reward, terminated, truncated, info = self.env.step(action)
        assert isinstance(reward, float)
        assert not terminated  # Belum 96 step

    def test_full_episode_terminates(self):
        obs, _ = self.env.reset()
        total_reward = 0.0
        steps = 0
        for _ in range(100):
            action = self.env.action_space.sample()
            obs, reward, terminated, truncated, info = self.env.step(action)
            total_reward += reward
            steps += 1
            if terminated:
                break
        assert terminated, "Episode harus terminate setelah 96 step"
        assert steps == 96

    def test_action_masking_respects_quota(self):
        self.env.reset()
        n = self.twin.n_machines
        # Habiskan quota mesin 0
        action_on = np.array([1, 0], dtype=np.int8)
        for _ in range(self.twin.machines[0].daily_runtime_slots):
            self.env.step(action_on)
        # Setelah quota habis, mask harus 0 untuk mesin 0
        mask = self.twin.get_action_mask()
        assert mask[0] == 0, "Mesin yang quota-nya habis tidak boleh ON"

    def test_reward_is_negative(self):
        """Reward harus selalu negatif (kita meminimalkan biaya)."""
        obs, _ = self.env.reset()
        action = np.ones(self.twin.n_machines, dtype=np.int8)
        _, reward, _, _, _ = self.env.step(action)
        assert reward <= 0.0


class TestGreedySolarDispatch:
    def test_greedy_fills_solar_window(self):
        twin = _make_simple_twin()
        env = UMKMDispatchEnv(
            twin=twin,
            solar=SolarEngine(),
            kwp=3.0,
            target_date=date(2026, 6, 15),
        )
        schedule, infos = _greedy_solar_dispatch(env)
        assert schedule.shape == (96, 2)

        # Periksa total runtime: harus mendekati target (tidak harus persis karena masking)
        for i, m in enumerate(twin.machines):
            actual_runtime = int(np.sum(schedule[:, i]))
            assert actual_runtime <= m.daily_runtime_slots + 2, \
                f"Mesin {m.machine_id} melebihi quota harian"

    def test_greedy_prefers_solar_hours(self):
        twin = _make_simple_twin()
        env = UMKMDispatchEnv(
            twin=twin,
            solar=SolarEngine(),
            kwp=3.0,
            target_date=date(2026, 6, 15),
        )
        schedule, _ = _greedy_solar_dispatch(env)

        # Slot aktif mesin seharusnya lebih banyak di jam 10-14 (slot 40-56)
        solar_slots = schedule[40:56, :].sum()
        night_slots = schedule[0:16, :].sum()
        assert solar_slots >= night_slots, "Greedy dispatch harus lebih prefer jam surya"

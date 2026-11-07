import os
import numpy as np
from datetime import date
from typing import Optional, List
from app.agent.umkm_env import UMKMDispatchEnv
from app.digital_twin.factory_model import UMKMDigitalTwin, FlexibleMachine
from app.digital_twin.solar_engine import get_solar_engine
from app.core.config import settings

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env
    _SB3_AVAILABLE = True
except ImportError:
    PPO = None  # type: ignore[assignment,misc]
    make_vec_env = None  # type: ignore[assignment]
    _SB3_AVAILABLE = False


def _make_env(twin: UMKMDigitalTwin, kwp: float, target_date: date):
    def _init():
        env = UMKMDispatchEnv(
            twin=UMKMDigitalTwin(machines=[FlexibleMachine(**{
                "machine_id": m.machine_id,
                "appliance_class": m.appliance_class,
                "label": m.label,
                "power_w": m.power_w,
                "daily_runtime_slots": m.daily_runtime_slots,
                "deadline_slot": m.deadline_slot,
                "min_continuous_slots": m.min_continuous_slots,
                "cooldown_slots": m.cooldown_slots,
            }) for m in twin.machines]),
            solar=get_solar_engine(),
            kwp=kwp,
            target_date=target_date,
        )
        return env
    return _init


class PPOScheduler:
    """
    Wrapper Stable-Baselines3 PPO untuk optimasi jadwal dispatch harian.
    Jika model sudah dilatih dan tersimpan, load langsung.
    Jika belum, jalankan training pendek (online warm-up).
    """

    def __init__(self) -> None:
        self._model: Optional[PPO] = None
        self._load_pretrained()

    def _load_pretrained(self) -> None:
        if not _SB3_AVAILABLE:
            self._model = None
            return
        path = settings.rl_model_path
        if os.path.exists(path):
            try:
                dummy_env = UMKMDispatchEnv()
                self._model = PPO.load(path, env=dummy_env)
            except Exception:
                self._model = None

    def train(
        self,
        total_timesteps: int = 100_000,
        kwp: float = 2.0,
        n_envs: int = 4,
    ) -> None:
        if not _SB3_AVAILABLE:
            raise RuntimeError("stable-baselines3 tidak terinstall. Jalankan: pip install stable-baselines3 gymnasium")
        twin = UMKMDigitalTwin()
        vec_env = make_vec_env(
            _make_env(twin, kwp, date.today()),
            n_envs=n_envs,
        )
        self._model = PPO(
            "MlpPolicy",
            vec_env,
            verbose=1,
            learning_rate=3e-4,
            n_steps=512,
            batch_size=64,
            n_epochs=10,
            gamma=0.99,
            clip_range=0.2,
            ent_coef=0.01,
        )
        self._model.learn(total_timesteps=total_timesteps)
        os.makedirs(os.path.dirname(settings.rl_model_path), exist_ok=True)
        self._model.save(settings.rl_model_path)

    def run_episode(
        self,
        env: UMKMDispatchEnv,
    ) -> tuple[np.ndarray, List[dict]]:
        """
        Jalankan satu episode penuh menggunakan model PPO.
        Returns:
            schedule_matrix: (96, N_machines) int8 — aksi per slot
            slot_infos: list 96 dict berisi p_pv, cost, dll.
        """
        if self._model is None:
            # Fallback: greedy solar matching
            return _greedy_solar_dispatch(env)

        obs, _ = env.reset()
        n = env.twin.n_machines
        schedule = np.zeros((96, n), dtype=np.int8)
        infos = []

        for slot in range(96):
            action, _ = self._model.predict(obs, deterministic=True)
            obs, _, terminated, _, info = env.step(action)
            schedule[slot] = action.astype(np.int8)
            infos.append(info)
            if terminated:
                break

        return schedule, infos


def _greedy_solar_dispatch(env: UMKMDispatchEnv) -> tuple[np.ndarray, List[dict]]:
    """
    Strategi greedy: nyalakan semua mesin fleksibel saat P_pv tinggi.
    Digunakan sebagai fallback saat model PPO belum dilatih.
    """
    obs, _ = env.reset()
    n = env.twin.n_machines
    schedule = np.zeros((96, n), dtype=np.int8)
    infos = []

    # Rank slot berdasarkan P_pv tertinggi
    sorted_slots = np.argsort(env._pv_curve)[::-1]
    high_pv_slots = set(sorted_slots[:40].tolist())

    for slot in range(96):
        if slot in high_pv_slots:
            action = env.twin.get_action_mask()
        else:
            action = np.zeros(n, dtype=np.int8)

        obs, _, terminated, _, info = env.step(action)
        schedule[slot] = action
        infos.append(info)
        if terminated:
            break

    return schedule, infos


_ppo_scheduler: Optional[PPOScheduler] = None


def get_ppo_scheduler() -> PPOScheduler:
    global _ppo_scheduler
    if _ppo_scheduler is None:
        _ppo_scheduler = PPOScheduler()
    return _ppo_scheduler

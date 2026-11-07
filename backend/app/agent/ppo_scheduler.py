"""
Pemuat & pelaksana kebijakan MaskablePPO (sb3-contrib) untuk API WASKITA.

- ``sb3_contrib``/``torch`` di-import SECARA MALAS saat model dimuat. Bila
  paket tidak ada atau file model tidak ada, ``is_ready`` False dan planner
  memakai OR-Tools / greedy. Server API tidak butuh torch.
- Model dilatih dengan ``scripts/train_agent.py`` (behavior cloning + PPO) dan
  disimpan ke ``settings.rl_model_path`` beserta metadata
  ``settings.rl_meta_path`` (versi observasi & jumlah slot mesin). Model
  dengan versi observasi berbeda ditolak.
- ``_greedy_solar_dispatch`` = fallback greedy (lihat ``baseline.greedy_schedule``)
  yang dijalankan lewat env, sehingga tetap patuh mask & deadline.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, List, Optional

import numpy as np

from app.agent.baseline import greedy_schedule
from app.agent.umkm_env import OBS_VERSION, UMKMDispatchEnv
from app.core.config import settings
from app.core.tariff import N_SLOTS
from app.digital_twin.factory_model import DispatchProblem

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def resolve_path(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else BACKEND_ROOT / path


def sb3_available() -> bool:
    try:
        import sb3_contrib  # noqa: F401
    except ImportError:
        return False
    return True


class PPOScheduler:
    def __init__(self, model_path: Optional[str] = None, meta_path: Optional[str] = None) -> None:
        self.model_path = resolve_path(model_path or settings.rl_model_path)
        self.meta_path = resolve_path(meta_path or settings.rl_meta_path)
        self._model: Any = None
        self.meta: dict = {}
        self.n_max_machines: int = settings.rl_max_machines
        self.status = "belum dimuat"
        self._lock = threading.Lock()
        self._load_pretrained()

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def _load_pretrained(self) -> None:
        if not self.model_path.exists():
            self.status = f"model belum dilatih ({self.model_path.name} tidak ada)"
            return
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.meta = {}
        if self.meta.get("obs_version") != OBS_VERSION:
            self.status = (
                f"metadata model tidak cocok (obs_version {self.meta.get('obs_version')} ≠ {OBS_VERSION}); "
                "latih ulang dengan scripts/train_agent.py"
            )
            return
        self.n_max_machines = int(self.meta.get("n_max_machines", settings.rl_max_machines))
        try:
            from sb3_contrib import MaskablePPO
        except ImportError:
            self.status = "sb3-contrib/torch tidak terpasang (pip install -r requirements-rl.txt)"
            return
        try:
            self._model = MaskablePPO.load(str(self.model_path), device="cpu")
            self.status = "siap"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Gagal memuat model PPO %s", self.model_path)
            self._model = None
            self.status = f"gagal memuat model ({exc.__class__.__name__})"

    def schedule(self, problem: DispatchProblem) -> Optional[np.ndarray]:
        """Jadwal (96, n) dari kebijakan PPO, atau None bila model belum siap."""
        if self._model is None or problem.n_machines > self.n_max_machines:
            return None
        env = UMKMDispatchEnv(problem=problem, n_max_machines=self.n_max_machines)
        return run_policy(self._model, env, lock=self._lock)

    def run_episode(self, env: UMKMDispatchEnv) -> tuple[np.ndarray, List[dict]]:
        """Kompatibilitas lama: jalankan satu episode (PPO bila siap, selain itu greedy)."""
        if self._model is None or env.n_max != self.n_max_machines:
            return _greedy_solar_dispatch(env)
        infos: list[dict] = []
        schedule = run_policy(self._model, env, infos=infos, lock=self._lock)
        return schedule, infos


def run_policy(model: Any, env: UMKMDispatchEnv, infos: Optional[list] = None, lock: Any = None) -> np.ndarray:
    """Jalankan kebijakan (deterministik, dengan action mask) satu episode."""
    obs, _ = env.reset(options={"problem": env.problem})
    for _ in range(N_SLOTS):
        masks = env.action_masks()
        if lock is not None:
            with lock:
                action, _ = model.predict(obs, action_masks=masks, deterministic=True)
        else:
            action, _ = model.predict(obs, action_masks=masks, deterministic=True)
        obs, _, terminated, _, info = env.step(action)
        if infos is not None:
            infos.append(info)
        if terminated:
            break
    return env.schedule.copy()


def _greedy_solar_dispatch(env: UMKMDispatchEnv) -> tuple[np.ndarray, List[dict]]:
    """
    Fallback greedy: satu blok per mesin di jendela kerja yang menyerap surplus
    PV terbanyak (kWp = 0 → jam kebiasaan lama). Dijalankan lewat env sehingga
    hasilnya selalu mematuhi deadline, blok minimum, dan cooldown.
    """
    plan = greedy_schedule(env.problem)
    env.reset(options={"problem": env.problem})
    infos: list[dict] = []
    for t in range(N_SLOTS):
        action = np.zeros(env.n_max, dtype=np.int64)
        action[: plan.shape[1]] = plan[t]
        _, _, terminated, _, info = env.step(action)
        infos.append(info)
        if terminated:
            break
    return env.schedule.copy(), infos


_ppo_scheduler: Optional[PPOScheduler] = None
_ppo_lock = threading.Lock()


def get_ppo_scheduler() -> PPOScheduler:
    global _ppo_scheduler
    with _ppo_lock:
        if _ppo_scheduler is None:
            _ppo_scheduler = PPOScheduler()
        return _ppo_scheduler


def reset_ppo_scheduler() -> None:
    """Lupakan model yang sudah dimuat (dipakai tes / setelah melatih ulang)."""
    global _ppo_scheduler
    with _ppo_lock:
        _ppo_scheduler = None

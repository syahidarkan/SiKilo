"""
Lingkungan Gymnasium untuk agen penjadwal WASKITA.

- Horizon: 96 langkah (slot 15 menit). Satu episode = satu ``DispatchProblem``.
- Aksi: ``MultiDiscrete([2] * n_max)`` (0 = OFF, 1 = ON per slot mesin).
  Mesin di-*padding* sampai ``n_max`` agar satu kebijakan bisa dipakai untuk
  jumlah mesin berbeda; slot padding selalu di-mask OFF.
- ``action_masks()`` → bool ``(2·n_max,)`` untuk sb3-contrib MaskablePPO:
  ``[boleh_OFF_0, boleh_ON_0, boleh_OFF_1, ...]``. Forced-ON → hanya ON yang
  sah; tidak boleh ON (jendela/cooldown/runtime habis) → hanya OFF yang sah.
  ``step`` juga menerapkan aturan yang sama, sehingga aksi apa pun (bahkan acak)
  menghasilkan jadwal yang memenuhi semua deadline.
- Baterai opsional (``battery.Battery``); SoC masuk observasi dan tidak pernah
  di bawah batas minimum (dijamin oleh ``Battery``).
- Reward = −(biaya listrik PLN slot ini + Rp 1 per start mesin) × ``reward_scale``.
  Tarif dari ``app.core.tariff`` (lewat ``DispatchProblem.tariff_idr_per_wh``).

Gymnasium opsional: tanpa gymnasium kelas ini tetap bisa dipakai sebagai
simulator biasa (``action_space`` / ``observation_space`` bernilai ``None``).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

import numpy as np

from app.core.config import settings
from app.core.tariff import N_SLOTS, SLOT_HOURS, tariff_curve_idr_per_wh
from app.digital_twin.factory_model import DispatchProblem, UMKMDigitalTwin

try:
    import gymnasium as gym
    from gymnasium import spaces

    _GYM_AVAILABLE = True
except ImportError:  # pragma: no cover - tergantung instalasi
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]
    _GYM_AVAILABLE = False

OBS_VERSION = 2
N_GLOBAL_FEATURES = 10
N_MACHINE_FEATURES = 9
PV_REF_W = 5_000.0
POWER_REF_W = 5_000.0
TARIFF_REF_IDR_PER_WH = 2.5
BATTERY_REF_WH = 20_000.0
OBS_CLIP = 5.0

_BaseEnv = gym.Env if _GYM_AVAILABLE else object


def obs_size(n_max: int) -> int:
    return N_GLOBAL_FEATURES + N_MACHINE_FEATURES * n_max


class UMKMDispatchEnv(_BaseEnv):  # type: ignore[misc]
    metadata = {"render_modes": []}

    def __init__(
        self,
        problem: Optional[DispatchProblem] = None,
        problem_sampler: Optional[Callable[[np.random.Generator], DispatchProblem]] = None,
        n_max_machines: Optional[int] = None,
        reward_scale: float = 1e-4,
        start_penalty_idr: float = 1.0,
        # ── kompatibilitas lama: bangun problem dari twin + PLTS ──────────
        twin: Optional[UMKMDigitalTwin] = None,
        solar: Any = None,
        baseload_w: Optional[float] = None,
        target_date: Optional[date] = None,
        kwp: float = 0.0,
        battery: Any = None,
    ) -> None:
        super().__init__()
        if problem is None and problem_sampler is None:
            problem = _problem_from_twin(twin, solar, baseload_w, target_date, kwp, battery)
        self._fixed_problem = problem
        self._sampler = problem_sampler
        if n_max_machines is None:
            if problem is None:
                raise ValueError("n_max_machines wajib diisi bila memakai problem_sampler")
            n_max_machines = problem.n_machines
        self.n_max = int(n_max_machines)
        if problem is not None and problem.n_machines > self.n_max:
            raise ValueError(f"Jumlah mesin {problem.n_machines} > n_max_machines {self.n_max}")
        self.reward_scale = float(reward_scale)
        self.start_penalty_idr = float(start_penalty_idr)
        self._rng = np.random.default_rng()

        if _GYM_AVAILABLE:
            self.action_space = spaces.MultiDiscrete([2] * self.n_max)
            self.observation_space = spaces.Box(
                low=-OBS_CLIP, high=OBS_CLIP, shape=(obs_size(self.n_max),), dtype=np.float32
            )
        else:  # pragma: no cover
            self.action_space = None
            self.observation_space = None

        self.problem: DispatchProblem = problem  # type: ignore[assignment]
        self.twin: UMKMDigitalTwin = UMKMDigitalTwin(machines=problem.fresh_machines() if problem else [])
        self._battery = None
        self._soc_start_wh = 0.0
        self._current_slot = 0
        self.schedule = np.zeros((N_SLOTS, self.twin.n_machines), dtype=np.int8)
        self.total_cost_idr = 0.0
        if problem is not None:
            self._load_problem(problem)

    # ── util ───────────────────────────────────────────────────────────────
    @property
    def _pv_curve(self) -> np.ndarray:  # kompatibilitas lama
        return self.problem.pv_w

    def _load_problem(self, problem: DispatchProblem) -> None:
        if problem.n_machines > self.n_max:
            raise ValueError(f"Jumlah mesin {problem.n_machines} > n_max_machines {self.n_max}")
        self.problem = problem
        self.twin = UMKMDigitalTwin(machines=problem.fresh_machines())
        self.twin.reset()
        self._battery = problem.fresh_battery()
        self._soc_start_wh = self._battery.soc_wh if self._battery is not None else 0.0
        self._current_slot = 0
        self.schedule = np.zeros((N_SLOTS, problem.n_machines), dtype=np.int8)
        self.total_cost_idr = 0.0
        pv = problem.pv_w
        # Rata-rata PV ke depan (1 jam, 4 jam) dan sisa energi PV hari ini.
        csum = np.concatenate([[0.0], np.cumsum(pv)])
        idx = np.arange(N_SLOTS)
        self._pv_next4 = (csum[np.minimum(idx + 4, N_SLOTS)] - csum[idx]) / 4.0
        self._pv_next16 = (csum[np.minimum(idx + 16, N_SLOTS)] - csum[idx]) / 16.0
        self._pv_rest_wh = (csum[N_SLOTS] - csum[idx]) * SLOT_HOURS

    def _get_obs(self) -> np.ndarray:
        t = min(self._current_slot, N_SLOTS - 1)
        p = self.problem
        obs = np.zeros(obs_size(self.n_max), dtype=np.float32)
        soc_frac = self._battery.soc_frac if self._battery is not None else 0.0
        cap = self._battery.capacity_wh if self._battery is not None else 0.0
        obs[0] = self._current_slot / N_SLOTS
        obs[1] = p.pv_w[t] / PV_REF_W
        obs[2] = self._pv_next4[t] / PV_REF_W
        obs[3] = self._pv_next16[t] / PV_REF_W
        obs[4] = (p.pv_w[t] - p.base_load_w[t]) / PV_REF_W
        obs[5] = p.tariff_idr_per_wh[t] / TARIFF_REF_IDR_PER_WH
        obs[6] = float(np.mean(p.tariff_idr_per_wh[t:t + 16])) / TARIFF_REF_IDR_PER_WH
        obs[7] = soc_frac
        obs[8] = cap / BATTERY_REF_WH
        obs[9] = self._pv_rest_wh[t] / BATTERY_REF_WH
        for i, m in enumerate(self.twin.machines):
            o = N_GLOBAL_FEATURES + i * N_MACHINE_FEATURES
            in_day = self._current_slot < N_SLOTS
            obs[o + 0] = 1.0
            obs[o + 1] = m.power_w / POWER_REF_W
            obs[o + 2] = m.remaining_slots / 32.0
            obs[o + 3] = m.slack(t) / 32.0
            obs[o + 4] = float(m.current_state)
            obs[o + 5] = float(in_day and m.allowed_on(t))
            obs[o + 6] = float(in_day and m.forced_on(t))
            obs[o + 7] = float(m.in_window(t))
            obs[o + 8] = min(m.consecutive_on / max(m.min_run, 1), 1.0)
        return np.clip(obs, -OBS_CLIP, OBS_CLIP)

    def action_masks(self) -> np.ndarray:
        """Mask aksi sah untuk MaskablePPO, bool shape (2·n_max,)."""
        mask = np.zeros((self.n_max, 2), dtype=bool)
        mask[:, 0] = True
        if self._current_slot < N_SLOTS:
            forced = self.twin.get_forced_mask().astype(bool)
            allowed = self.twin.get_action_mask().astype(bool)
            n = self.twin.n_machines
            mask[:n, 1] = allowed | forced
            mask[:n, 0] = ~forced
        return mask.reshape(-1)

    # ── API gymnasium ─────────────────────────────────────────────────────
    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        if _GYM_AVAILABLE:
            super().reset(seed=seed)
            self._rng = self.np_random
        elif seed is not None:  # pragma: no cover
            self._rng = np.random.default_rng(seed)
        problem: Optional[DispatchProblem] = None
        if options and options.get("problem") is not None:
            problem = options["problem"]
        elif self._sampler is not None:
            problem = self._sampler(self._rng)
        else:
            problem = self._fixed_problem
        self._load_problem(problem)
        return self._get_obs(), {}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._current_slot >= N_SLOTS:
            raise RuntimeError("Episode sudah selesai; panggil reset()")
        t = self._current_slot
        prev_state = np.array([m.current_state for m in self.twin.machines], dtype=np.int8)
        eff = self.twin.step(np.asarray(action).reshape(-1)[: self.twin.n_machines])
        self.schedule[t] = eff
        p = self.problem
        p_machines_w = float(np.dot(eff, p.power_w)) if p.n_machines else 0.0
        p_total_w = p_machines_w + float(p.base_load_w[t])
        p_pv_w = float(p.pv_w[t])
        net_w = p_pv_w - p_total_w
        soc_wh = None
        if self._battery is not None:
            grid_wh, curtail_wh = self._battery.step(net_w, SLOT_HOURS)
            soc_wh = self._battery.soc_wh
        else:
            grid_wh = max(0.0, -net_w) * SLOT_HOURS
            curtail_wh = max(0.0, net_w) * SLOT_HOURS
        cost = grid_wh * float(p.tariff_idr_per_wh[t])
        n_starts = int(np.sum((eff == 1) & (prev_state == 0)))
        self.total_cost_idr += cost
        reward = -(cost + self.start_penalty_idr * n_starts) * self.reward_scale

        self._current_slot += 1
        terminated = self._current_slot >= N_SLOTS
        unmet = 0
        deficit_cost = 0.0
        if terminated:
            if self._battery is not None:
                # Sama dengan simulate_schedule: SoC yang dikuras di bawah SoC awal dibayar di akhir hari.
                from app.digital_twin.factory_model import soc_deficit_cost

                _, deficit_cost = soc_deficit_cost(
                    self._battery, self._soc_start_wh, self._battery.soc_wh, p.tariff_idr_per_wh
                )
                self.total_cost_idr += deficit_cost
                reward -= deficit_cost * self.reward_scale
            unmet = int(sum(m.remaining_slots for m in self.twin.machines))
            if unmet:  # seharusnya mustahil karena forced-ON; penalti pengaman
                reward -= 1_000.0 * unmet
        info = {
            "slot": t,
            "p_pv_w": p_pv_w,
            "p_total_w": p_total_w,
            "grid_wh": grid_wh,
            "curtail_wh": curtail_wh,
            "cost_idr": cost,
            "soc_wh": soc_wh,
            "effective_action": eff.copy(),
            "unmet_slots": unmet,
            "soc_deficit_cost_idr": deficit_cost,
        }
        return self._get_obs(), float(reward), terminated, False, info


def _problem_from_twin(twin, solar, baseload_w, target_date, kwp, battery) -> DispatchProblem:
    """Kompatibilitas: bangun DispatchProblem dari twin + PLTS (pemakaian interaktif)."""
    from app.digital_twin.solar_engine import get_solar_engine

    twin = twin if twin is not None else UMKMDigitalTwin()
    solar = solar if solar is not None else get_solar_engine()
    if target_date is None:
        target_date = date.today()
    pv = np.asarray(solar.simulate_day(target_date, kwp), dtype=np.float64) if kwp > 0 else np.zeros(N_SLOTS)
    base = settings.default_baseload_w if baseload_w is None else float(baseload_w)
    return DispatchProblem(
        machines=twin.machines,
        pv_w=pv,
        base_load_w=np.full(N_SLOTS, base),
        tariff_idr_per_wh=tariff_curve_idr_per_wh(N_SLOTS),
        battery=battery,
        target_date=target_date,
        kwp=float(kwp),
        pv_source=getattr(solar, "last_source", "none") if kwp > 0 else "none",
    )

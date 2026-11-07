from typing import Any, Optional
import numpy as np
from datetime import date, timedelta
from app.digital_twin.solar_engine import SolarEngine, get_solar_engine
from app.digital_twin.factory_model import UMKMDigitalTwin, FlexibleMachine
from app.core.config import settings

try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_AVAILABLE = True
except ImportError:
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]
    _GYM_AVAILABLE = False

N_SLOTS = 96  # 15-menit interval per hari


_BaseEnv = gym.Env if _GYM_AVAILABLE else object


class UMKMDispatchEnv(_BaseEnv):  # type: ignore[misc]
    """
    Custom Gymnasium environment untuk optimasi jadwal mesin UMKM.

    - Time horizon: 96 step per hari (tiap step = 15 menit)
    - Action: MultiBinary(N_machines) — 1=ON, 0=OFF per mesin fleksibel
    - Observation: [step/95, P_pv_norm, tarif_norm, remaining_slots × N]
    - Reward: minimasi biaya grid + penalti curtailment + deadline + switching
    """

    metadata = {"render_modes": []}

    # Bobot penalti dalam reward function
    W_CURTAILMENT: float = 1.5
    W_DEADLINE: float = 50.0
    W_SWITCHING: float = 0.5

    # Tarif PLN (Rp/kWh → Rp/Wh)
    TARIFF_PEAK_IDR_PER_WH: float = settings.pln_tariff_peak_idr / 1000.0
    TARIFF_OFFPEAK_IDR_PER_WH: float = settings.pln_tariff_offpeak_idr / 1000.0

    def __init__(
        self,
        twin: Optional[UMKMDigitalTwin] = None,
        solar: Optional[SolarEngine] = None,
        baseload_w: float = 800.0,
        target_date: Optional[date] = None,
        kwp: float = 2.0,
    ) -> None:
        super().__init__()
        self.twin = twin if twin is not None else UMKMDigitalTwin()
        self.solar = solar if solar is not None else get_solar_engine()
        self.baseload_w = baseload_w
        self.kwp = kwp
        self._target_date = target_date or date.today()

        n = self.twin.n_machines
        if _GYM_AVAILABLE:
            self.action_space = spaces.MultiBinary(n)
            low = np.zeros(3 + n, dtype=np.float32)
            high = np.ones(3 + n, dtype=np.float32)
            high[1] = 2.0
            self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        else:
            self._obs_size = 3 + n

        self._pv_curve: np.ndarray = np.zeros(N_SLOTS, dtype=np.float32)
        self._current_slot: int = 0
        self._prev_actions: Optional[np.ndarray] = None
        self._total_grid_wh: float = 0.0
        self._total_curtail_wh: float = 0.0

    def _get_tariff(self, slot: int) -> float:
        hour = slot // 4
        # WB-2 Tariff: peak 08:00-22:00, off-peak otherwise
        if 8 <= hour < 22:
            return self.TARIFF_PEAK_IDR_PER_WH
        return self.TARIFF_OFFPEAK_IDR_PER_WH

    def _get_obs(self) -> np.ndarray:
        slot_norm = self._current_slot / (N_SLOTS - 1)
        pv_max = self.kwp * 1000.0 * self.solar.INVERTER_EFF
        p_pv_norm = float(self._pv_curve[self._current_slot]) / max(pv_max, 1.0)
        tariff_id = 1.0 if self._get_tariff(self._current_slot) == self.TARIFF_PEAK_IDR_PER_WH else 0.0
        remaining = self.twin.get_state_vector()
        return np.array([slot_norm, p_pv_norm, tariff_id, *remaining], dtype=np.float32)

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        self.twin.reset()
        self._current_slot = 0
        self._prev_actions = None
        self._total_grid_wh = 0.0
        self._total_curtail_wh = 0.0

        # Simulasikan kurva surya untuk hari target
        if options and "target_date" in options:
            self._target_date = options["target_date"]
        self._pv_curve = self.solar.simulate_day(self._target_date, self.kwp)

        return self._get_obs(), {}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        action = np.asarray(action, dtype=np.int8)

        # Action masking: matikan aksi untuk mesin yang tidak bisa ON
        mask = self.twin.get_action_mask()
        effective_action = action & mask

        self.twin.step(effective_action)

        p_machines_w = self.twin.get_total_load_w()
        p_total_w = p_machines_w + self.baseload_w
        p_pv_w = float(self._pv_curve[self._current_slot])
        tariff = self._get_tariff(self._current_slot)

        # Energi per slot (15 menit = 0.25 jam)
        dt_h = 0.25
        p_net_w = p_total_w - p_pv_w

        grid_wh = max(0.0, p_net_w) * dt_h
        curtail_wh = max(0.0, -p_net_w) * dt_h

        self._total_grid_wh += grid_wh
        self._total_curtail_wh += curtail_wh

        # --- Reward ---
        cost_grid = grid_wh * tariff
        penalty_curtail = curtail_wh * self.W_CURTAILMENT
        penalty_deadline = self._deadline_penalty()
        penalty_switching = self._switching_penalty(effective_action)

        reward = -(cost_grid + penalty_curtail + penalty_deadline + penalty_switching)

        self._prev_actions = effective_action.copy()
        self._current_slot += 1
        terminated = self._current_slot >= N_SLOTS
        truncated = False

        if terminated:
            # Final deadline penalty untuk pekerjaan yang belum selesai
            for m in self.twin.machines:
                if m.remaining_slots > 0:
                    reward -= self.W_DEADLINE * m.remaining_slots * 20.0

        obs = self._get_obs() if not terminated else np.zeros(self.observation_space.shape, dtype=np.float32)
        info = {
            "slot": self._current_slot - 1,
            "p_pv_w": p_pv_w,
            "p_total_w": p_total_w,
            "grid_wh": grid_wh,
            "curtail_wh": curtail_wh,
            "cost_idr": cost_grid,
        }
        return obs, float(reward), terminated, truncated, info

    def _deadline_penalty(self) -> float:
        """Penalti eksponensial jika mesin berisiko tidak selesai sebelum deadline."""
        penalty = 0.0
        for m in self.twin.machines:
            if m.remaining_slots <= 0:
                continue
            slots_left_until_deadline = max(0, m.deadline_slot - self._current_slot)
            if slots_left_until_deadline < m.remaining_slots:
                # Tidak mungkin selesai tepat waktu
                deficit = m.remaining_slots - slots_left_until_deadline
                penalty += self.W_DEADLINE * (np.exp(deficit * 0.3) - 1)
        return penalty

    def _switching_penalty(self, action: np.ndarray) -> float:
        """Penalti jika terjadi switching ON-OFF berulang dalam jeda singkat."""
        if self._prev_actions is None:
            return 0.0
        switches = np.sum(action != self._prev_actions)
        return float(switches) * self.W_SWITCHING

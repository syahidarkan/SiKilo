"""
Model baterai sederhana untuk tiruan digital WASKITA.

- Efisiensi round-trip dibagi rata: η_charge = η_discharge = √η_rt.
- Batas daya ``max_charge_w`` / ``max_discharge_w`` diukur di sisi AC
  (daya yang ditukar dengan bus listrik UMKM).
- SoC tidak pernah turun di bawah ``soc_min_frac × capacity`` dan tidak
  pernah melebihi kapasitas.
- Surplus PV yang tidak bisa diserap dicatat sebagai curtailment (tidak
  dikreditkan ke PLN, sesuai Permen ESDM 2/2024 untuk PLTS atap).

Model ini tidak memodelkan degradasi, suhu, atau kurva tegangan; cukup untuk
perencanaan harian, belum divalidasi terhadap baterai nyata.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class BatteryRun:
    """Hasil menjalankan baterai sepanjang deret net_w."""

    grid_import_wh: np.ndarray   # (n,)
    curtail_wh: np.ndarray       # (n,)
    soc_wh: np.ndarray           # (n,) SoC SETELAH tiap langkah
    charge_wh: np.ndarray        # (n,) energi AC masuk baterai
    discharge_wh: np.ndarray     # (n,) energi AC keluar baterai


class Battery:
    def __init__(
        self,
        capacity_wh: float,
        max_charge_w: float,
        max_discharge_w: float,
        efficiency_rt: float = 0.90,
        soc_min_frac: float = 0.20,
        soc_init_frac: float = 0.50,
    ) -> None:
        if capacity_wh < 0:
            raise ValueError("capacity_wh tidak boleh negatif")
        if max_charge_w < 0 or max_discharge_w < 0:
            raise ValueError("batas daya tidak boleh negatif")
        if not 0.0 < efficiency_rt <= 1.0:
            raise ValueError("efficiency_rt harus di (0, 1]")
        if not 0.0 <= soc_min_frac < 1.0:
            raise ValueError("soc_min_frac harus di [0, 1)")
        self.capacity_wh = float(capacity_wh)
        self.max_charge_w = float(max_charge_w)
        self.max_discharge_w = float(max_discharge_w)
        self.efficiency_rt = float(efficiency_rt)
        self.soc_min_frac = float(soc_min_frac)
        self.soc_init_frac = float(min(max(soc_init_frac, soc_min_frac), 1.0))
        self.eta_charge = math.sqrt(self.efficiency_rt)
        self.eta_discharge = math.sqrt(self.efficiency_rt)
        self.last_charge_wh = 0.0
        self.last_discharge_wh = 0.0
        self._soc_wh = 0.0
        self.reset()

    # ── state ──────────────────────────────────────────────────────────────
    @property
    def soc_min_wh(self) -> float:
        return self.capacity_wh * self.soc_min_frac

    @property
    def soc_max_wh(self) -> float:
        return self.capacity_wh

    @property
    def soc_wh(self) -> float:
        return self._soc_wh

    @property
    def soc_frac(self) -> float:
        return self._soc_wh / self.capacity_wh if self.capacity_wh > 0 else 0.0

    @property
    def usable_wh(self) -> float:
        """Energi AC yang masih bisa dikeluarkan sampai SoC minimum."""
        return max(self._soc_wh - self.soc_min_wh, 0.0) * self.eta_discharge

    def reset(self, soc_frac: Optional[float] = None) -> None:
        frac = self.soc_init_frac if soc_frac is None else min(max(soc_frac, self.soc_min_frac), 1.0)
        self._soc_wh = self.capacity_wh * frac
        self.last_charge_wh = 0.0
        self.last_discharge_wh = 0.0

    # ── dinamika ───────────────────────────────────────────────────────────
    def step(self, net_w: float, dt_h: float = 0.25) -> tuple[float, float]:
        """
        Satu langkah waktu.

        Args:
            net_w: PV − beban (W). Positif = surplus, negatif = defisit.
            dt_h: lama langkah dalam jam (default 15 menit).

        Returns:
            (grid_import_wh, curtail_wh) setelah baterai menyerap surplus atau
            menutup defisit sebisanya.
        """
        if dt_h <= 0:
            raise ValueError("dt_h harus positif")
        net_w = float(net_w)
        self.last_charge_wh = 0.0
        self.last_discharge_wh = 0.0

        if net_w >= 0.0:
            surplus_wh = net_w * dt_h
            room_wh = max(self.soc_max_wh - self._soc_wh, 0.0) / self.eta_charge
            charge_ac_wh = min(surplus_wh, self.max_charge_w * dt_h, room_wh)
            self._soc_wh = min(self._soc_wh + charge_ac_wh * self.eta_charge, self.soc_max_wh)
            self.last_charge_wh = charge_ac_wh
            return 0.0, max(surplus_wh - charge_ac_wh, 0.0)

        deficit_wh = -net_w * dt_h
        available_ac_wh = max(self._soc_wh - self.soc_min_wh, 0.0) * self.eta_discharge
        discharge_ac_wh = min(deficit_wh, self.max_discharge_w * dt_h, available_ac_wh)
        self._soc_wh = max(self._soc_wh - discharge_ac_wh / self.eta_discharge, self.soc_min_wh)
        self.last_discharge_wh = discharge_ac_wh
        return max(deficit_wh - discharge_ac_wh, 0.0), 0.0

    def run(self, net_w_series, dt_h: float = 0.25, reset: bool = True) -> BatteryRun:
        """Jalankan ``step`` untuk seluruh deret (mis. 96 slot)."""
        if reset:
            self.reset()
        net = np.asarray(net_w_series, dtype=np.float64)
        n = net.shape[0]
        grid = np.zeros(n)
        curtail = np.zeros(n)
        soc = np.zeros(n)
        chg = np.zeros(n)
        dis = np.zeros(n)
        for i, v in enumerate(net):
            grid[i], curtail[i] = self.step(v, dt_h)
            soc[i] = self._soc_wh
            chg[i] = self.last_charge_wh
            dis[i] = self.last_discharge_wh
        return BatteryRun(grid, curtail, soc, chg, dis)

    @classmethod
    def from_kwh(
        cls,
        capacity_kwh: float,
        c_rate: float = 0.5,
        **kwargs,
    ) -> "Battery":
        """Pembuat praktis: batas daya = c_rate × kapasitas (default 0,5C)."""
        cap_wh = float(capacity_kwh) * 1000.0
        p = cap_wh * c_rate
        return cls(capacity_wh=cap_wh, max_charge_w=p, max_discharge_w=p, **kwargs)

    def __repr__(self) -> str:  # pragma: no cover - kosmetik
        return (
            f"Battery(capacity_wh={self.capacity_wh:.0f}, soc_wh={self._soc_wh:.0f}, "
            f"eta_rt={self.efficiency_rt:.2f}, soc_min_frac={self.soc_min_frac:.2f})"
        )

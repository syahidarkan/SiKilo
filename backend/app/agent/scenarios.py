"""
Generator skenario latih/evaluasi untuk agen penjadwal.

Setiap skenario = satu hari acak (sepanjang tahun yang dipilih) dengan:
- 2..n_max mesin hasil variasi template (daya, runtime, jendela kerja, jam
  kebiasaan, blok minimum, cooldown, idle, sebagian tidak fleksibel);
- runtime diskalakan ``orders.OrderBook`` menurut hari & musim (Minggu/Lebaran
  bisa nol);
- kWp acak (termasuk 0 = belum punya PLTS) dan baterai opsional;
- PV dari ``solar_engine`` untuk tanggal tersebut (NASA POWER bila cache ada).

Distribusi ini ASUMSI untuk melatih kebijakan yang umum, bukan data UMKM nyata.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional, Sequence

import numpy as np

from app.digital_twin.battery import Battery
from app.digital_twin.factory_model import DispatchProblem, UMKMDigitalTwin
from app.digital_twin.orders import OrderBook

KWP_CHOICES = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
KWP_PROBS = (0.15, 0.1, 0.2, 0.2, 0.15, 0.1, 0.1)
BATTERY_KWH_CHOICES = (2.5, 5.0, 10.0)


def dates_of_year(year: int) -> list[date]:
    d0 = date(year, 1, 1)
    n = (date(year + 1, 1, 1) - d0).days
    return [d0 + timedelta(days=i) for i in range(n)]


class ScenarioSampler:
    def __init__(
        self,
        n_max: int,
        dates: Optional[Sequence[date]] = None,
        year: int = 2025,
        battery_prob: float = 0.3,
        order_book: Optional[OrderBook] = None,
        solar: Any = None,
        min_machines: int = 2,
    ) -> None:
        self.n_max = int(n_max)
        self.dates = list(dates) if dates is not None else dates_of_year(year)
        self.battery_prob = float(battery_prob)
        self.order_book = order_book or OrderBook()
        self._solar = solar
        self.min_machines = max(1, min(int(min_machines), self.n_max))

    @property
    def solar(self) -> Any:
        if self._solar is None:
            from app.digital_twin.solar_engine import get_solar_engine

            self._solar = get_solar_engine()
        return self._solar

    def sample_jobs(self, rng: np.random.Generator, day: date) -> list[dict]:
        templates = UMKMDigitalTwin.DEFAULT_JOB_TEMPLATES
        n = int(rng.integers(self.min_machines, self.n_max + 1))
        jobs: list[dict] = []
        for k in range(n):
            t = dict(templates[k % len(templates)])
            earliest = int(rng.choice([6, 7, 8]))
            deadline = int(rng.choice([15, 16, 17, 18]))
            window_min = (deadline - earliest) * 60
            runtime = int(round(t["daily_runtime_minutes"] * rng.uniform(0.5, 1.4) / 15.0)) * 15
            runtime = int(min(max(runtime, 15), window_min - 60))
            jobs.append(
                {
                    "machine_id": f"{t['machine_id']}-{k}",
                    "appliance_class": t["appliance_class"],
                    "label": t["label"],
                    "power_w": float(round(t["power_w"] * rng.uniform(0.6, 1.5) / 50.0) * 50.0),
                    "daily_runtime_minutes": runtime,
                    "earliest_hour": earliest,
                    "deadline_hour": deadline,
                    "habit_start_hour": int(rng.integers(earliest, min(earliest + 4, deadline))),
                    "min_continuous_minutes": int(rng.choice([15, 30, 45, 60])),
                    "cooldown_minutes": int(rng.choice([0, 15, 30])),
                    "is_flexible": bool(rng.random() > 0.1),
                    "idle_minutes_habit": int(rng.choice([0, 15, 30, 45, 60])),
                }
            )
        return self.order_book.jobs_for(day, jobs)

    def __call__(self, rng: np.random.Generator) -> DispatchProblem:
        from app.agent.planner import build_problem

        day = self.dates[int(rng.integers(0, len(self.dates)))]
        jobs = self.sample_jobs(rng, day)
        kwp = float(rng.choice(KWP_CHOICES, p=KWP_PROBS))
        battery = None
        if rng.random() < self.battery_prob:
            battery = Battery.from_kwh(float(rng.choice(BATTERY_KWH_CHOICES)))
        baseload = float(round(rng.uniform(300.0, 1500.0) / 50.0) * 50.0)
        return build_problem(jobs, day, kwp=kwp, baseload_w=baseload, battery=battery, solar=self.solar)

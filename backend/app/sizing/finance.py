"""
Kelayakan finansial PLTS (harga riil, tanpa eskalasi tarif).

Arus kas tahun y (1..N, N = ``settings.panel_lifetime_years``):

    manfaat_y  = manfaat_1 × (1 − degradasi)^(y−1)
    OPEX       = opex_pct_of_capex × CAPEX total (konstan)
    penggantian baterai pada tahun L, 2L, … < N (L = battery_lifetime_years)
    CF_y       = manfaat_y − OPEX − penggantian_y

NPV = −CAPEX + Σ CF_y/(1+r)^y. PBP sederhana & PBP terdiskonto diinterpolasi
linear di dalam tahun saat kumulatif menjadi ≥ 0; ``None`` bila tidak balik
modal dalam umur proyek. LCOE = (CAPEX + PV(OPEX + penggantian)) / PV(produksi).

Catatan: penskalaan manfaat dengan degradasi produksi adalah pendekatan
konservatif (pada sistem yang sebagian PV-nya terbuang, manfaat turun lebih
lambat daripada produksi).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings


@dataclass
class FinanceResult:
    capex_idr: float
    pv_capex_idr: float
    battery_capex_idr: float
    annual_opex_idr: float
    npv_idr: float
    simple_payback_years: Optional[float]
    discounted_payback_years: Optional[float]
    lcoe_idr_per_kwh: float
    cashflows_idr: list[float] = field(default_factory=list)  # CF_1..CF_N (tidak didiskonto)


def _payback(cum_start: float, flows: list[float]) -> Optional[float]:
    cum = cum_start
    for y, cf in enumerate(flows, start=1):
        prev = cum
        cum += cf
        if cum >= 0.0 and cf > 0.0:
            return (y - 1) + (-prev / cf if prev < 0 else 0.0)
    return None


def evaluate_finance(
    year1_savings_idr: float,
    year1_generation_kwh: float,
    kwp: float,
    battery_kwh: float = 0.0,
    *,
    capex_per_kwp_idr: Optional[float] = None,
    battery_capex_per_kwh_idr: Optional[float] = None,
    lifetime_years: Optional[int] = None,
    discount_rate: Optional[float] = None,
    degradation_per_year: Optional[float] = None,
    opex_pct_of_capex: Optional[float] = None,
    battery_lifetime_years: Optional[int] = None,
) -> FinanceResult:
    s = settings
    capex_kwp = s.capex_per_kwp_idr if capex_per_kwp_idr is None else capex_per_kwp_idr
    capex_bat = s.battery_capex_per_kwh_idr if battery_capex_per_kwh_idr is None else battery_capex_per_kwh_idr
    n = int(s.panel_lifetime_years if lifetime_years is None else lifetime_years)
    r = float(s.discount_rate if discount_rate is None else discount_rate)
    d = float(s.panel_degradation_per_year if degradation_per_year is None else degradation_per_year)
    opex_pct = float(s.opex_pct_of_capex if opex_pct_of_capex is None else opex_pct_of_capex)
    bat_life = int(s.battery_lifetime_years if battery_lifetime_years is None else battery_lifetime_years)

    pv_capex = max(kwp, 0.0) * capex_kwp
    battery_capex = max(battery_kwh, 0.0) * capex_bat
    capex = pv_capex + battery_capex
    opex = opex_pct * capex

    flows: list[float] = []
    disc_flows: list[float] = []
    pv_costs = 0.0
    pv_gen = 0.0
    for y in range(1, n + 1):
        factor = (1.0 - d) ** (y - 1)
        replacement = battery_capex if (battery_capex > 0 and bat_life > 0 and y % bat_life == 0 and y < n) else 0.0
        cf = year1_savings_idr * factor - opex - replacement
        df = (1.0 + r) ** (-y)
        flows.append(cf)
        disc_flows.append(cf * df)
        pv_costs += (opex + replacement) * df
        pv_gen += year1_generation_kwh * factor * df

    npv = -capex + sum(disc_flows)
    lcoe = (capex + pv_costs) / pv_gen if pv_gen > 0 else float("inf")
    return FinanceResult(
        capex_idr=capex,
        pv_capex_idr=pv_capex,
        battery_capex_idr=battery_capex,
        annual_opex_idr=opex,
        npv_idr=npv,
        simple_payback_years=_payback(-capex, flows) if capex > 0 else 0.0,
        discounted_payback_years=_payback(-capex, disc_flows) if capex > 0 else 0.0,
        lcoe_idr_per_kwh=lcoe,
        cashflows_idr=flows,
    )

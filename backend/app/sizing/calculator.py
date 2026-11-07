import numpy as np
from typing import List
from datetime import date
from app.digital_twin.solar_engine import get_solar_engine
from app.schemas.sizing import SizingRequest, SizingResult
from app.core.config import settings


CO2_GRID_KG_PER_KWH: float = 0.785  # Faktor emisi PLN Jawa-Bali 2024


def calculate_optimal_sizing(request: SizingRequest) -> SizingResult:
    solar = get_solar_engine()

    # Bangun profil beban harian rata-rata (96 slot x 15 menit)
    daily_loads_wh: List[np.ndarray] = []
    for profile in request.load_profiles:
        # Konversi 24 jam → 96 slot (tiap jam dibagi 4 slot)
        slots = np.repeat(np.array(profile.hourly_kwh, dtype=np.float32), 4) * 1000.0 / 4.0
        daily_loads_wh.append(slots)

    avg_load_wh = np.mean(daily_loads_wh, axis=0)  # shape (96,)
    annual_load_kwh = float(np.sum(avg_load_wh)) / 1000.0 * 365.0

    # Binary search untuk menemukan kWp optimal
    kwp = _binary_search_kwp(
        avg_load_wh=avg_load_wh,
        solar=solar,
        target_self_consumption=request.target_self_consumption_pct,
    )

    # Simulasi 365 hari untuk metrik tahunan
    annual_gen, annual_self, annual_curtail = _simulate_annual(
        kwp=kwp,
        avg_load_wh=avg_load_wh,
        solar=solar,
    )

    self_consumption_rate = annual_self / max(annual_gen, 1.0)

    # --- Finansial ---
    capex = kwp * settings.capex_per_kwp_idr
    annual_savings_idr = annual_self * settings.tarif_pln_per_kwh_idr

    # LCOE: (CAPEX + OPEX_total) / total_generation_lifetime
    opex_annual = capex * 0.01  # 1% CAPEX/tahun untuk O&M
    total_capex_lifetime = capex
    total_opex_lifetime = opex_annual * settings.panel_lifetime_years
    total_generation_kwh = annual_gen * settings.panel_lifetime_years
    lcoe = (total_capex_lifetime + total_opex_lifetime) / max(total_generation_kwh, 1.0)

    # NPV dengan discount rate
    r = settings.discount_rate
    n = settings.panel_lifetime_years
    npv = -capex + annual_savings_idr * ((1 - (1 + r) ** (-n)) / r)

    # Simple PBP
    if annual_savings_idr > 0:
        pbp = capex / annual_savings_idr
    else:
        pbp = float("inf")

    co2_avoided = annual_self * CO2_GRID_KG_PER_KWH

    # Permen ESDM No. 2/2024: sistem zero export, self-consumption >= target
    permen_compliant = self_consumption_rate >= request.target_self_consumption_pct * 0.95

    note = (
        f"Kapasitas {kwp:.2f} kWp memenuhi {self_consumption_rate*100:.1f}% self-consumption "
        f"tanpa BESS. PBP {pbp:.1f} tahun. "
        + ("Memenuhi Permen ESDM No. 2/2024 (zero export)." if permen_compliant
           else "Perlu review konfigurasi inverter untuk zero-export compliance.")
    )

    return SizingResult(
        recommended_kwp=round(kwp, 2),
        annual_generation_kwh=round(annual_gen, 1),
        annual_self_consumption_kwh=round(annual_self, 1),
        annual_curtailment_kwh=round(annual_curtail, 1),
        self_consumption_rate_pct=round(self_consumption_rate * 100, 1),
        capex_idr=round(capex, 0),
        annual_savings_idr=round(annual_savings_idr, 0),
        lcoe_idr_per_kwh=round(lcoe, 1),
        npv_idr=round(npv, 0),
        payback_period_years=round(min(pbp, 99.9), 1),
        co2_avoided_kg_per_year=round(co2_avoided, 1),
        permen_esdm_compliant=permen_compliant,
        recommendation_note=note,
    )


def _simulate_annual(
    kwp: float,
    avg_load_wh: np.ndarray,
    solar,
) -> tuple[float, float, float]:
    gen_total = 0.0
    self_total = 0.0
    curtail_total = 0.0
    # Gunakan 12 hari representatif (awal tiap bulan)
    for month in range(1, 13):
        day = date(2026, month, 15)
        pv_w = solar.simulate_day(day, kwp)
        pv_wh = pv_w * 0.25

        self_wh = np.minimum(pv_wh, avg_load_wh)
        curtail_wh = np.maximum(pv_wh - avg_load_wh, 0.0)

        # Scale 12 days → 365 days (tiap hari representatif ≈ 30.4 hari)
        days_in_month = 30.4
        gen_total += float(np.sum(pv_wh)) / 1000.0 * days_in_month
        self_total += float(np.sum(self_wh)) / 1000.0 * days_in_month
        curtail_total += float(np.sum(curtail_wh)) / 1000.0 * days_in_month

    return gen_total, self_total, curtail_total


def _binary_search_kwp(
    avg_load_wh: np.ndarray,
    solar,
    target_self_consumption: float,
    lo: float = 0.5,
    hi: float = 20.0,
    iterations: int = 20,
) -> float:
    """Cari kWp minimum yang mencapai target self-consumption rate."""
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        _, self_wh, _ = _simulate_annual(mid, avg_load_wh, solar)
        gen_kwh, _, _ = _simulate_annual(mid, avg_load_wh, solar)
        rate = self_wh / max(gen_kwh, 1.0)
        if rate >= target_self_consumption:
            hi = mid
        else:
            lo = mid

    return round((lo + hi) / 2.0, 2)

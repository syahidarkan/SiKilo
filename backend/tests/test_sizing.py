"""Tes sizing PLTS (tahap "Punya PLTS"): kalkulator, finansial, compare, endpoint."""
from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.dispatch import MachineJob
from app.schemas.sizing import CompareRequest, DailyLoadProfile, SizingRequest
from app.sizing import calculate_optimal_sizing, compare_sizing_with_agent
from app.sizing.annual import representative_days
from app.sizing.calculator import _binary_search_kwp
from app.sizing.finance import evaluate_finance

YEAR = 2025


def _profiles(hourly_kw: list[float], n_days: int = 21, start: date = date(2025, 9, 1)) -> list[DailyLoadProfile]:
    return [DailyLoadProfile(date=start + timedelta(days=i), hourly_kwh=list(hourly_kw)) for i in range(n_days)]


def _daytime(kw: float, base: float = 0.0, start_h: int = 7, end_h: int = 17) -> list[float]:
    return [kw if start_h <= h < end_h else base for h in range(24)]


def _req(hourly: list[float], **kw) -> SizingRequest:
    kw.setdefault("reference_year", YEAR)
    return SizingRequest(load_profiles=_profiles(hourly), **kw)


# ── pencarian biner ─────────────────────────────────────────────────────────


def test_binary_search_returns_largest_kwp_meeting_target():
    calls = []

    def sc(k: float) -> float:
        calls.append(k)
        return 1.0 / (1.0 + k)  # turun monoton; SC ≥ 0.5 ⇔ k ≤ 1

    k = _binary_search_kwp(sc, 0.5, lo=0.01, hi=20.0)
    assert k == pytest.approx(1.0, abs=0.01)
    assert len(calls) <= 2 + 30  # satu evaluasi per iterasi (+ cek batas)


def test_binary_search_edges():
    assert _binary_search_kwp(lambda k: 1.0, 0.9, lo=0.1, hi=5.0) == 5.0
    assert _binary_search_kwp(lambda k: 0.1, 0.9, lo=0.1, hi=5.0) == 0.1


def test_regression_daytime_3kw_load_gives_kwp_well_above_lower_bound():
    """Bug lama: pencarian biner terbalik selalu konvergen ke ~0,5 kWp."""
    res = calculate_optimal_sizing(_req(_daytime(3.0, base=0.2)))
    assert res.kwp_for_target_sc > 2.0
    assert res.recommended_kwp > 2.0
    assert res.self_consumption_rate_pct >= res.target_self_consumption_pct - 0.1
    assert res.recommended_kwp <= res.kwp_for_target_sc + 1e-6


# ── kalkulator ──────────────────────────────────────────────────────────────


def test_self_consumption_monotone_and_npv_choice():
    res = calculate_optimal_sizing(_req(_daytime(3.0, base=0.2)))
    nb = sorted((c for c in res.candidates if c.battery_kwh == 0), key=lambda c: c.kwp)
    sc = [c.self_consumption_rate_pct for c in nb]
    assert all(a >= b - 1e-6 for a, b in zip(sc, sc[1:]))
    feas = [c for c in nb if c.feasible]
    assert feas
    best = max(feas, key=lambda c: c.npv_idr)
    assert res.recommended_kwp == pytest.approx(best.kwp, abs=0.01)
    # Penghematan = PV terpakai × tarif flat dari tariff.py
    assert res.annual_savings_idr == pytest.approx(
        res.annual_self_consumption_kwh * settings.tariff_flat_idr_per_kwh, rel=1e-3
    )
    assert res.annual_bill_after_idr == pytest.approx(res.annual_bill_before_idr - res.annual_savings_idr, abs=2)
    assert res.discounted_payback_years is None or res.discounted_payback_years >= res.payback_period_years


def test_tariff_comes_from_tariff_module(monkeypatch):
    base = calculate_optimal_sizing(_req(_daytime(2.0)))
    monkeypatch.setattr(settings, "tariff_flat_idr_per_kwh", settings.tariff_flat_idr_per_kwh * 2)
    doubled = calculate_optimal_sizing(_req(_daytime(2.0)))
    assert doubled.annual_bill_before_idr == pytest.approx(2 * base.annual_bill_before_idr, rel=1e-6)


def test_connected_power_limit_and_honest_regulatory_checks():
    res = calculate_optimal_sizing(_req(_daytime(5.0), connected_power_va=1300))
    assert res.recommended_kwp <= 1.3 + 1e-6
    assert res.max_kwp_limit == pytest.approx(1.3)
    checks = res.regulatory_checks
    assert checks is not None
    assert checks.kwp_within_connected_power is True
    assert checks.export_not_credited_modeled is True
    assert "Januari" in checks.application_window_note and "Juli" in checks.application_window_note
    assert "PLN" in checks.disclaimer
    assert "Memenuhi Permen" not in res.recommendation_note
    # kWp target SC tetap dilaporkan tanpa batas daya tersambung
    assert res.kwp_for_target_sc > 1.3


def test_unknown_connected_power_is_not_claimed_compliant():
    res = calculate_optimal_sizing(_req(_daytime(2.0)))
    assert res.regulatory_checks.kwp_within_connected_power is None
    assert res.permen_esdm_compliant is False


def test_location_is_used():
    near_eq = calculate_optimal_sizing(_req(_daytime(2.0)))
    far_north = calculate_optimal_sizing(_req(_daytime(2.0), location_lat=60.0, location_lon=10.0))
    gen_eq = {c.kwp: c.annual_generation_kwh for c in near_eq.candidates}
    gen_n = {c.kwp: c.annual_generation_kwh for c in far_north.candidates}
    common = sorted(set(gen_eq) & set(gen_n))
    assert common
    k = common[len(common) // 2]
    assert gen_n[k] < gen_eq[k] * 0.9


def test_representative_days_weighted_by_actual_month_length():
    leap = representative_days(2024, settings.site_latitude, settings.site_longitude)
    normal = representative_days(2025, settings.site_latitude, settings.site_longitude)
    assert len(leap) == len(normal) == 12
    assert sum(r.weight_days for r in leap) == 366
    assert sum(r.weight_days for r in normal) == 365
    assert leap[1].weight_days == 29 and normal[1].weight_days == 28
    assert all(r.day.year == 2025 and r.day.month == r.month for r in normal)


def test_battery_search_picks_battery_when_cheap(monkeypatch):
    monkeypatch.setattr(settings, "battery_capex_per_kwh_idr", 1.0)
    # Beban malam besar → surplus siang bernilai bila disimpan.
    hourly = [1.5 if (h < 6 or h >= 18) else 0.5 for h in range(24)]
    res = calculate_optimal_sizing(_req(hourly, include_battery=True, battery_options_kwh=[5.0, 10.0]))
    assert res.recommended_battery_kwh > 0
    with_bat = [c for c in res.candidates if c.battery_kwh > 0]
    assert with_bat
    nb = {c.kwp: c for c in res.candidates if c.battery_kwh == 0}
    for c in with_bat:
        if c.kwp in nb:
            assert c.self_consumption_rate_pct >= nb[c.kwp].self_consumption_rate_pct - 1e-6


def test_battery_not_chosen_when_ignored():
    res = calculate_optimal_sizing(_req(_daytime(2.0), include_battery=False))
    assert res.recommended_battery_kwh == 0
    assert all(c.battery_kwh == 0 for c in res.candidates)


def test_zero_load_rejected():
    with pytest.raises(ValueError):
        calculate_optimal_sizing(_req([0.0] * 24))


# ── finansial ───────────────────────────────────────────────────────────────


def test_finance_npv_matches_hand_calculation():
    fin = evaluate_finance(
        1_000_000.0, 1000.0, kwp=1.0,
        capex_per_kwp_idr=5_000_000.0, lifetime_years=10, discount_rate=0.1,
        degradation_per_year=0.0, opex_pct_of_capex=0.0,
    )
    annuity = (1 - 1.1 ** -10) / 0.1
    assert fin.npv_idr == pytest.approx(-5_000_000 + 1_000_000 * annuity, rel=1e-9)
    assert fin.simple_payback_years == pytest.approx(5.0)
    assert fin.discounted_payback_years > fin.simple_payback_years


def test_finance_degradation_opex_and_battery_replacement_reduce_npv():
    kw = dict(capex_per_kwp_idr=5_000_000.0, lifetime_years=25, discount_rate=0.07)
    plain = evaluate_finance(1e6, 1000.0, 1.0, degradation_per_year=0.0, opex_pct_of_capex=0.0, **kw)
    degr = evaluate_finance(1e6, 1000.0, 1.0, degradation_per_year=0.01, opex_pct_of_capex=0.0, **kw)
    opex = evaluate_finance(1e6, 1000.0, 1.0, degradation_per_year=0.0, opex_pct_of_capex=0.02, **kw)
    assert degr.npv_idr < plain.npv_idr and opex.npv_idr < plain.npv_idr
    bat = evaluate_finance(1e6, 1000.0, 1.0, battery_kwh=1.0, battery_capex_per_kwh_idr=1e6,
                           battery_lifetime_years=10, degradation_per_year=0.0, opex_pct_of_capex=0.0, **kw)
    # CAPEX baterai + 2 penggantian (tahun 10 & 20)
    expected = plain.npv_idr - 1e6 - 1e6 * (1.07 ** -10 + 1.07 ** -20)
    assert bat.npv_idr == pytest.approx(expected, rel=1e-9)


def test_finance_never_pays_back():
    fin = evaluate_finance(10_000.0, 10.0, kwp=1.0, capex_per_kwp_idr=10_000_000.0)
    assert fin.simple_payback_years is None and fin.discounted_payback_years is None
    assert fin.npv_idr < 0


# ── compare: kebiasaan lama vs agen ─────────────────────────────────────────


def test_compare_agent_vs_habit_curves():
    t0 = time.perf_counter()
    res = compare_sizing_with_agent(
        CompareRequest(target_savings_pct=20, kwp_candidates=[2.0, 4.0, 6.0], reference_year=YEAR)
    )
    assert time.perf_counter() - t0 < 60
    assert res.curve[0].kwp == 0.0
    assert res.reference_annual_bill_idr > 0
    for p in res.curve:
        assert p.agent_savings_idr_per_year >= p.habit_no_idle_savings_idr_per_year - 1
        assert p.habit_no_idle_savings_idr_per_year >= p.habit_savings_idr_per_year - 1
    habit = [p.habit_savings_idr_per_year for p in res.curve]
    assert all(b >= a - 1 for a, b in zip(habit, habit[1:]))
    assert res.min_kwp_agent is not None and res.min_kwp_habit is not None
    assert res.min_kwp_agent <= res.min_kwp_habit + 1e-6
    assert res.target_annual_savings_idr == pytest.approx(0.2 * res.reference_annual_bill_idr, rel=1e-6)
    assert res.headline and res.notes
    assert not res.timed_out


def test_compare_honest_when_agent_cannot_shift():
    jobs = [
        MachineJob(machine_id="m1", label="Mesin tetap", power_w=2000, daily_runtime_minutes=240,
                   earliest_hour=8, deadline_hour=17, habit_start_hour=9, is_flexible=False),
    ]
    res = compare_sizing_with_agent(
        CompareRequest(jobs=jobs, baseload_w=300, target_savings_pct=15, kwp_candidates=[1.0, 2.0, 3.0],
                       reference_year=YEAR)
    )
    assert res.agent_reduces_panel is False
    assert any("tidak memperkecil" in n for n in res.notes) or res.min_kwp_agent is None
    for p in res.curve:
        assert p.agent_annual_bill_idr == pytest.approx(p.habit_annual_bill_idr, abs=1)


def test_compare_time_budget_is_respected():
    res = compare_sizing_with_agent(
        CompareRequest(target_savings_idr_per_month=5_000_000, kwp_candidates=[1.0, 2.0], reference_year=YEAR),
        time_budget_s=0.0,
    )
    assert res.timed_out
    assert len(res.curve) == 1 and res.min_kwp_agent is None


def test_compare_request_requires_exactly_one_target():
    with pytest.raises(ValidationError):
        CompareRequest()
    with pytest.raises(ValidationError):
        CompareRequest(target_savings_pct=10, target_savings_idr_per_month=100_000)


def test_compare_connected_power_filters_candidates():
    res = compare_sizing_with_agent(
        CompareRequest(target_savings_pct=10, kwp_candidates=[1.0, 2.0, 5.0], connected_power_va=2200,
                       reference_year=YEAR)
    )
    assert max(res.kwp_candidates) <= 2.2
    assert all(p.kwp <= 2.2 + 1e-9 for p in res.curve)


# ── endpoint ────────────────────────────────────────────────────────────────


def test_sizing_endpoints_require_login(client):
    body = {"load_profiles": [{"date": "2025-09-01", "hourly_kwh": _daytime(2.0)}]}
    assert client.post("/api/v1/sizing/calculate", json=body).status_code == 401
    assert client.post("/api/v1/sizing/compare", json={"target_savings_pct": 10}).status_code == 401


def test_sizing_calculate_endpoint(client, auth_headers):
    body = {
        "load_profiles": [
            {"date": (date(2025, 9, 1) + timedelta(days=i)).isoformat(), "hourly_kwh": _daytime(2.5, 0.2)}
            for i in range(7)
        ],
        "connected_power_va": 5500,
        "reference_year": YEAR,
    }
    r = client.post("/api/v1/sizing/calculate", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert 0 < data["recommended_kwp"] <= 5.5
    assert data["regulatory_checks"]["kwp_within_connected_power"] is True


def test_sizing_calculate_endpoint_rejects_zero_load(client, auth_headers):
    body = {"load_profiles": [{"date": "2025-09-01", "hourly_kwh": [0.0] * 24}], "reference_year": YEAR}
    r = client.post("/api/v1/sizing/calculate", json=body, headers=auth_headers)
    assert r.status_code == 422


def test_sizing_compare_endpoint(client, auth_headers):
    body = {"target_savings_pct": 15, "kwp_candidates": [2.0, 4.0], "reference_year": YEAR}
    r = client.post("/api/v1/sizing/compare", json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["curve"][0]["kwp"] == 0.0
    assert "headline" in data and isinstance(data["notes"], list)


def test_no_old_brand_in_sizing_files():
    root = Path(__file__).resolve().parents[1]
    files = list((root / "app" / "sizing").glob("*.py")) + [
        root / "app" / "schemas" / "sizing.py",
        root / "app" / "api" / "v1" / "endpoints_sizing.py",
    ]
    for f in files:
        text = f.read_text(encoding="utf-8").lower()
        assert "nota listrik" not in text, f
        assert "memenuhi permen" not in text, f

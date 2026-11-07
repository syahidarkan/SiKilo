"""rapor.compute_sizing harus meneruskan daya tersambung PLN ke kalkulator sizing."""
from datetime import date, timedelta

import app.sizing.calculator as calc
from app.services_data import rapor


class _FakeSizing:
    recommended_kwp = 2.0
    payback_period_years = 5.0
    annual_savings_idr = 1_000_000.0
    capex_idr = 10_000_000.0


def _profiles(n=3):
    d0 = date(2026, 1, 1)
    return [(d0 + timedelta(days=i), [0.5] * 24) for i in range(n)]


def _run(monkeypatch, umkm):
    seen = []

    def fake(req):
        seen.append(req)
        return _FakeSizing()

    monkeypatch.setattr(calc, "calculate_optimal_sizing", fake)
    out = rapor.compute_sizing(_profiles(), umkm, 500_000.0)
    return seen[0], out


def test_connected_power_passed(monkeypatch):
    req, out = _run(monkeypatch, {"name": "A", "address": "B", "umkm_type": "laundry", "connected_power_va": 2200})
    assert req.connected_power_va == 2200.0
    assert out["recommended_kwp"] == 2.0


def test_connected_power_absent(monkeypatch):
    req, _ = _run(monkeypatch, {"name": "A", "address": "B", "umkm_type": "laundry"})
    assert req.connected_power_va is None

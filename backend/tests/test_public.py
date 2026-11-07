"""Tes endpoint publik simulator landing page (/api/v1/public/*)."""
from app.api.v1 import endpoints_public as pub


def test_catalog_lists_machines_and_power(client):
    r = client.get("/api/v1/public/catalog")
    assert r.status_code == 200
    body = r.json()
    assert set(body["machines"]) == set(pub.MACHINE_CATALOG)
    assert 5500 in body["connected_power_va"]


def test_estimate_without_login_returns_sane_numbers(client):
    r = client.post("/api/v1/public/estimate", json={"connected_power_va": 3500, "machines": ["mesin_cuci_dryer"]})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["monthly_bill_now_idr"] > 0
    assert b["tariff_idr_per_kwh"] > 0
    # Panel tidak boleh melebihi daya tersambung (3,5 kVA).
    if b["recommended_kwp"] is not None:
        assert 0 < b["recommended_kwp"] <= 3.5 + 1e-6
        assert b["capex_idr"] > 0
    assert b["headline"]
    # Kurva harus berisi beberapa kandidat kWp (bukan terpotong batas waktu).
    assert len(b["curve"]) >= 5


def test_estimate_snaps_va_and_rejects_unknown_machine(client):
    r = client.post("/api/v1/public/estimate", json={"connected_power_va": 3400, "machines": []})
    assert r.status_code == 200
    assert r.json()["connected_power_va"] == 3500
    bad = client.post("/api/v1/public/estimate", json={"connected_power_va": 3500, "machines": ["reaktor_nuklir"]})
    assert bad.status_code == 422


def test_machine_power_scaled_to_fit_connected_power():
    jobs, baseload = pub._build_jobs(900, ["setrika_uap", "oven_pemanas", "kompresor_angin", "mesin_cuci_dryer"])
    total = baseload + sum(j.power_w for j in jobs)
    assert total <= 0.85 * 900 + 1e-6


def test_rate_limiter_blocks_after_limit():
    ip = "203.0.113.77"
    pub._hits.pop(ip, None)
    results = [pub._rate_limited(ip) for _ in range(pub._RATE_LIMIT + 1)]
    assert results[:-1] == [False] * pub._RATE_LIMIT
    assert results[-1] is True

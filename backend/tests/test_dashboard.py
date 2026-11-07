"""Tes dashboard multi-peran: umkm, disperinaker, lead installer, bank, papan KPI."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.models import DailyPlan, Device
from app.nilm.disaggregator import HourlyEnergy
from app.schemas.telemetry import local_tz
from app.services_data import kpi, rapor
from app.services_data.ledger import upsert_ledger


def _today() -> date:
    return datetime.now(local_tz()).date()


def _seed_days(db_call, umkm_id: int, n_days: int, kwh_per_hour: float = 0.5, end: date | None = None):
    """n hari lengkap (24 jam) berakhir kemarin."""
    end = end or (_today() - timedelta(days=1))

    async def write(s):
        entries = []
        for k in range(n_days):
            d = end - timedelta(days=k)
            for h in range(24):
                entries.append(HourlyEnergy(d, h, "Setrika Pemanas Uap", kwh_per_hour))
        await upsert_ledger(s, umkm_id, entries)
        await s.commit()
    db_call(write)


def _seed_plan(db_call, umkm_id: int, day: date, savings_idr: float, savings_pct: float, met: bool = True):
    async def write(s):
        s.add(DailyPlan(umkm_id=umkm_id, day=day, solver="greedy", cost_idr=10000 - savings_idr,
                        baseline_cost_idr=10000, savings_idr=savings_idr, savings_pct=savings_pct,
                        deadlines_met=met, payload_json={}))
        await s.commit()
    db_call(write)


@pytest.fixture(autouse=True)
def _fake_sizing(monkeypatch):
    """Sizing asli lambat/milik modul lain; ganti dengan hasil tetap di tes ini."""
    calls = []

    def fake(profiles, umkm, monthly_cost):
        calls.append(len(profiles))
        return {"recommended_kwp": 3.456, "payback_years": 5.04, "annual_savings_idr": 4_000_000.0,
                "capex_idr": 36_000_000.0, "score": 72.0, "risk_category": "SEDANG"}

    monkeypatch.setattr(rapor, "compute_sizing", fake)
    rapor.clear_cache()
    yield calls
    rapor.clear_cache()


# ── UMKM ────────────────────────────────────────────────────────────────────
def test_umkm_dashboard(client, make_user, make_device, db_call, admin_headers, installer_user):
    owner = make_user("umkm")
    make_device(owner.umkm_id)
    _seed_days(db_call, owner.umkm_id, 3, end=_today())
    _seed_plan(db_call, owner.umkm_id, _today(), 2000, 20.0)

    r = client.get("/api/v1/dashboard/umkm", params={"include_rapor": True}, headers=owner.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["umkm"]["id"] == owner.umkm_id
    assert body["today"]["kwh"] == pytest.approx(12.0)
    assert body["last_7_days"]["kwh"] == pytest.approx(36.0)
    assert body["last_7_days"]["days_with_data"] == 3
    assert body["top_appliances"][0]["appliance_label"] == "Setrika Pemanas Uap"
    assert len(body["devices"]) == 1 and body["devices"][0]["online"] is False
    assert body["latest_plan"]["savings_pct"] == pytest.approx(20.0)
    assert body["rapor"]["status"] == "belum_ada_data"  # 2 hari lengkap sebelum hari ini < 7

    assert client.get("/api/v1/dashboard/umkm", headers=installer_user.headers).status_code == 403
    assert client.get("/api/v1/dashboard/umkm", headers=admin_headers).status_code == 422
    r = client.get("/api/v1/dashboard/umkm", params={"umkm_id": owner.umkm_id}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["rapor"] is None


# ── Disperinaker ────────────────────────────────────────────────────────────
def test_disperinaker_aggregate_respects_consent(client, make_user, db_call, disperinaker_user, umkm_user):
    kec = f"Kec-{datetime.now().timestamp():.0f}"
    a = make_user("umkm", kecamatan=kec, consent_share_data=True)
    b = make_user("umkm", kecamatan=kec, consent_share_data=True)
    hidden = make_user("umkm", kecamatan=kec, consent_share_data=False)
    _seed_days(db_call, a.umkm_id, 8)
    _seed_days(db_call, b.umkm_id, 2)
    _seed_days(db_call, hidden.umkm_id, 8)
    _seed_plan(db_call, a.umkm_id, _today() - timedelta(days=1), 1000, 10.0)
    _seed_plan(db_call, a.umkm_id, _today() - timedelta(days=2), 3000, 30.0)

    r = client.get("/api/v1/dashboard/disperinaker", headers=disperinaker_user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {u["umkm_id"] for u in body["umkm"]}
    assert a.umkm_id in ids and b.umkm_id in ids
    assert hidden.umkm_id not in ids
    assert body["n_umkm_total"] >= body["n_umkm_consent"] + 1
    stat = next(k for k in body["kecamatan"] if k["kecamatan"] == kec)
    assert stat["n_umkm"] == 2
    assert stat["kwh"] == pytest.approx(10 * 24 * 0.5)
    assert stat["potential_savings_idr_per_month"] == pytest.approx(30 * 2000)
    item_a = next(u for u in body["umkm"] if u["umkm_id"] == a.umkm_id)
    item_b = next(u for u in body["umkm"] if u["umkm_id"] == b.umkm_id)
    assert item_a["ready_for_pv"] is True and item_b["ready_for_pv"] is False
    assert "phone_whatsapp" not in item_a

    assert client.get("/api/v1/dashboard/disperinaker", headers=umkm_user.headers).status_code == 403


# ── Lead / installer ────────────────────────────────────────────────────────
def test_lead_lifecycle(client, make_user, db_call, admin_headers):
    owner = make_user("umkm")
    inst1 = make_user("installer")
    inst2 = make_user("installer")
    _seed_days(db_call, owner.umkm_id, 7)

    r = client.post("/api/v1/dashboard/leads", json={"notes": "Saya tertarik PLTS"}, headers=owner.headers)
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["status"] == "new" and lead["recommended_kwp"] == pytest.approx(3.46)
    assert lead["phone_whatsapp"]
    assert client.post("/api/v1/dashboard/leads", json={}, headers=owner.headers).status_code == 409
    r = client.post("/api/v1/dashboard/leads", json={"recommended_kwp": 5}, headers=owner.headers)
    assert r.status_code == 403

    # installer melihat lead terbuka, lalu mengambilnya
    seen = client.get("/api/v1/dashboard/leads", headers=inst1.headers).json()
    assert lead["id"] in {x["id"] for x in seen}
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"status": "contacted"}, headers=inst1.headers)
    assert r.status_code == 200, r.text
    assert r.json()["installer_user_id"] == inst1.id and r.json()["status"] == "contacted"

    # installer lain tidak melihat & tidak bisa mengubah
    assert lead["id"] not in {x["id"] for x in client.get("/api/v1/dashboard/leads", headers=inst2.headers).json()}
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"status": "surveyed"}, headers=inst2.headers)
    assert r.status_code == 403
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"installer_user_id": inst2.id}, headers=inst1.headers)
    assert r.status_code == 403

    # pemilik hanya bisa membatalkan
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"status": "installed"}, headers=owner.headers)
    assert r.status_code == 403
    mine = client.get("/api/v1/dashboard/leads", headers=owner.headers).json()
    assert [x["id"] for x in mine] == [lead["id"]]

    # admin memindahkan ke installer lain
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"installer_user_id": inst2.id}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["installer_user_id"] == inst2.id
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"installer_user_id": owner.id}, headers=admin_headers)
    assert r.status_code == 422
    r = client.patch(f"/api/v1/dashboard/leads/{lead['id']}", json={"status": "lost"}, headers=owner.headers)
    assert r.status_code == 200 and r.json()["status"] == "lost"

    # setelah lost, UMKM boleh mengajukan lagi; admin bisa langsung menugaskan
    r = client.post("/api/v1/dashboard/leads",
                    json={"umkm_id": owner.umkm_id, "installer_user_id": inst1.id, "recommended_kwp": 2.5},
                    headers=admin_headers)
    assert r.status_code == 201 and r.json()["recommended_kwp"] == pytest.approx(2.5)
    assert client.get("/api/v1/dashboard/leads", headers=make_user("bank").headers).status_code == 403


def test_lead_without_data_has_zero_kwp(client, umkm_user):
    r = client.post("/api/v1/dashboard/leads", json={}, headers=umkm_user.headers)
    assert r.status_code == 201
    body = r.json()
    assert body["recommended_kwp"] == 0
    assert "hari data" in body["notes"]


# ── Bank ────────────────────────────────────────────────────────────────────
def test_bank_dashboard(client, make_user, db_call, bank_user, umkm_user, _fake_sizing):
    ready = make_user("umkm", consent_share_data=True)
    hidden = make_user("umkm", consent_share_data=False)
    _seed_days(db_call, ready.umkm_id, 10)
    _seed_days(db_call, hidden.umkm_id, 10)

    r = client.get("/api/v1/dashboard/bank", params={"limit": 200}, headers=bank_user.headers)
    assert r.status_code == 200, r.text
    items = {i["umkm_id"]: i for i in r.json()["items"]}
    assert hidden.umkm_id not in items
    rap = items[ready.umkm_id]["rapor"]
    assert rap["status"] == "ok"
    assert rap["recommended_kwp"] == pytest.approx(3.46)
    assert rap["payback_years"] == pytest.approx(5.0)
    assert rap["score"] == pytest.approx(72.0)
    assert rap["data_days"] == 10
    assert rap["monthly_kwh"] == pytest.approx(12.0 * 30)
    assert "belum divalidasi" in rap["validation"]
    assert items[umkm_user.umkm_id]["rapor"]["status"] == "belum_ada_data"

    n_calls = len(_fake_sizing)
    client.get("/api/v1/dashboard/bank", params={"limit": 200}, headers=bank_user.headers)
    assert len(_fake_sizing) == n_calls  # cache dipakai bila data tidak berubah

    assert client.get("/api/v1/dashboard/bank", headers=umkm_user.headers).status_code == 403


def test_rapor_reports_failure(client, make_user, db_call, monkeypatch):
    u = make_user("umkm")
    _seed_days(db_call, u.umkm_id, 7)

    def boom(*_a, **_k):
        raise RuntimeError("modul sizing rusak")

    monkeypatch.setattr(rapor, "compute_sizing", boom)
    assert client.get("/api/v1/dashboard/umkm", headers=u.headers).json()["rapor"] is None
    r = client.get("/api/v1/dashboard/umkm", params={"include_rapor": True}, headers=u.headers)
    assert r.status_code == 200
    assert r.json()["rapor"]["status"] == "gagal"
    assert r.json()["rapor"]["recommended_kwp"] is None


# ── KPI ─────────────────────────────────────────────────────────────────────
def test_kpi_board(client, make_user, make_device, db_call, admin_headers, tmp_path, monkeypatch):
    owner = make_user("umkm")
    dev = make_device(owner.umkm_id)
    _seed_plan(db_call, owner.umkm_id, _today() - timedelta(days=1), 2000, 20.0, met=True)
    _seed_plan(db_call, owner.umkm_id, _today() - timedelta(days=2), 1000, 10.0, met=False)

    async def mark_online(s):
        d = await s.get(Device, dev.data["id"])
        d.last_seen = datetime.now(timezone.utc)
        await s.commit()
    db_call(mark_online)

    nilm = tmp_path / "nilm.json"
    nilm.write_text(json.dumps({
        "data_source": "synthetic",
        "validation_status": "belum divalidasi — data sintetis",
        "target": {"threshold": 0.8},
        "overall": {"energy_estimated_accuracy": 0.9, "macro_f1_appliances": 0.85},
        "generated_at": "2026-11-01T00:00:00",
    }), encoding="utf-8")
    twin = tmp_path / "twin.json"
    twin.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings, "nilm_metrics_path", str(nilm))
    monkeypatch.setattr(settings, "twin_validation_path", str(twin))

    r = client.get("/api/v1/dashboard/kpi", headers=owner.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "UMKM Anda"
    m = {x["key"]: x for x in body["metrics"]}
    assert set(m) == {"nilm_accuracy", "twin_bill_error", "avg_savings_pct", "orders_on_time_pct", "devices_online"}
    assert m["nilm_accuracy"]["value"] == pytest.approx(90.0)
    assert m["nilm_accuracy"]["status"] == "ok"
    assert "belum divalidasi" in m["nilm_accuracy"]["validation"]
    assert str(nilm.name) in m["nilm_accuracy"]["source"]
    assert m["twin_bill_error"]["status"] == "belum_ada_data"
    assert m["avg_savings_pct"]["value"] == pytest.approx(15.0)
    assert m["orders_on_time_pct"]["value"] == pytest.approx(50.0)
    assert m["orders_on_time_pct"]["status"] == "di_bawah_target"
    assert m["devices_online"]["value"] == 1 and m["devices_online"]["detail"]["total"] == 1
    for metric in body["metrics"]:
        assert metric["source"]

    # UMKM baru tanpa rencana/perangkat → belum ada data
    fresh = make_user("umkm")
    m2 = {x["key"]: x for x in client.get("/api/v1/dashboard/kpi", headers=fresh.headers).json()["metrics"]}
    assert m2["avg_savings_pct"]["status"] == "belum_ada_data"
    assert m2["devices_online"]["status"] == "belum_ada_data"

    monkeypatch.setattr(settings, "nilm_metrics_path", str(tmp_path / "tidak_ada.json"))
    r = client.get("/api/v1/dashboard/kpi", headers=admin_headers)
    m3 = {x["key"]: x for x in r.json()["metrics"]}
    assert r.json()["scope"] == "semua UMKM"
    assert m3["nilm_accuracy"]["status"] == "belum_ada_data"


def test_kpi_twin_metric_from_file(tmp_path):
    p = tmp_path / "twin.json"
    p.write_text(json.dumps({"bill_error_pct": 12.5, "target_bill_error_pct": 10.0, "source": "example",
                             "n_days": 30}), encoding="utf-8")
    m = kpi.twin_bill_error_metric(str(p))
    assert m["value"] == pytest.approx(12.5)
    assert m["status"] == "di_bawah_target"
    assert m["validation"] == "belum divalidasi"
    bad = tmp_path / "rusak.json"
    bad.write_text("{bukan json", encoding="utf-8")
    assert kpi.twin_bill_error_metric(str(bad))["status"] == "belum_ada_data"

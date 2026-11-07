"""
Tes regresi untuk perbaikan integrasi/keamanan/kebenaran WASKITA:
profil mesin & profil UMKM lewat API, idle di MachineProfile, beban dasar
terukur, nota mingguan dengan hari data berbeda, toleransi penghematan,
nilai SoC baterai, PV terpakai kebiasaan lama, headline idle-only, sizing
baterai pada data yang sama, replay disaggregator, Meta template, rapor POST
tidak terverifikasi.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import numpy as np
import pytest

from app.core.config import settings
from app.models import UMKM
from app.nilm.disaggregator import HourlyEnergy
from app.schemas.telemetry import local_tz
from app.services import jobs
from app.services_data.ledger import upsert_ledger

API = "/api/v1"


def _today() -> date:
    return datetime.now(local_tz()).date()


MACHINE = {
    "machine_id": "setrika-01",
    "label": "Setrika Uap",
    "appliance_class": 3,
    "power_w": 1500,
    "daily_runtime_minutes": 240,
    "earliest_hour": 7,
    "deadline_hour": 17,
    "habit_start_hour": 8,
    "min_continuous_minutes": 60,
    "idle_minutes_habit": 60,
}


# ── profil mesin & profil UMKM lewat API ───────────────────────────────────
def test_machine_profile_crud_owner_admin_installer(client, make_user, admin_headers):
    owner = make_user("umkm")
    other = make_user("umkm")
    inst = make_user("installer")

    r = client.post(f"{API}/umkm/me/machines", json=MACHINE, headers=owner.headers)
    assert r.status_code == 201, r.text
    assert r.json()["idle_minutes_habit"] == 60 and r.json()["umkm_id"] == owner.umkm_id
    assert client.post(f"{API}/umkm/me/machines", json=MACHINE, headers=owner.headers).status_code == 409
    bad = dict(MACHINE, machine_id="x", daily_runtime_minutes=900)
    assert client.post(f"{API}/umkm/me/machines", json=bad, headers=owner.headers).status_code == 422

    # pemilik lain & installer yang tidak ditugaskan ditolak
    assert client.get(f"{API}/umkm/{owner.umkm_id}/machines", headers=other.headers).status_code == 403
    assert client.get(f"{API}/umkm/{owner.umkm_id}/machines", headers=inst.headers).status_code == 403

    # admin menugaskan installer → installer boleh mengubah profil mesin
    r = client.post(f"{API}/dashboard/leads",
                    json={"umkm_id": owner.umkm_id, "installer_user_id": inst.id, "recommended_kwp": 2.0},
                    headers=admin_headers)
    assert r.status_code == 201
    r = client.patch(f"{API}/umkm/{owner.umkm_id}/machines/setrika-01",
                     json={"daily_runtime_minutes": 180, "idle_power_w": 300}, headers=inst.headers)
    assert r.status_code == 200, r.text
    assert r.json()["daily_runtime_minutes"] == 180 and r.json()["idle_power_w"] == 300
    r = client.patch(f"{API}/umkm/{owner.umkm_id}/machines/setrika-01",
                     json={"deadline_hour": 8}, headers=inst.headers)
    assert r.status_code == 422  # 180 menit tidak muat di 07–08

    listed = client.get(f"{API}/umkm/{owner.umkm_id}/machines", headers=admin_headers).json()
    assert [m["machine_id"] for m in listed] == ["setrika-01"]
    assert client.delete(f"{API}/umkm/me/machines/setrika-01", headers=owner.headers).status_code == 204
    assert client.get(f"{API}/umkm/me/machines", headers=owner.headers).json() == []


def test_umkm_patch_roles_and_consent(client, make_user, admin_headers, db_call):
    owner = make_user("umkm", consent_share_data=True)
    inst = make_user("installer")
    bank = make_user("bank")

    r = client.patch(f"{API}/umkm/me", json={"pv_kwp": 2.5, "battery_kwh": 5, "connected_power_va": 7700},
                     headers=owner.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pv_kwp"] == 2.5 and body["battery_kwh"] == 5 and body["connected_power_va"] == 7700

    # cabut persetujuan → bank langsung tidak bisa membaca rapor/ledger
    r = client.patch(f"{API}/umkm/me", json={"consent_share_data": False}, headers=owner.headers)
    assert r.status_code == 200 and r.json()["consent_share_data"] is False
    assert r.json()["consent_updated_at"]
    r = client.get(f"{API}/telemetry/ledger", params={"umkm_id": owner.umkm_id}, headers=bank.headers)
    assert r.status_code == 403

    # installer tidak ditugaskan → 403; ditugaskan → hanya field teknis
    assert client.patch(f"{API}/umkm/{owner.umkm_id}", json={"pv_kwp": 3}, headers=inst.headers).status_code == 403
    client.post(f"{API}/dashboard/leads",
                json={"umkm_id": owner.umkm_id, "installer_user_id": inst.id, "recommended_kwp": 2.0},
                headers=admin_headers)
    assert client.patch(f"{API}/umkm/{owner.umkm_id}", json={"pv_kwp": 3}, headers=inst.headers).status_code == 200
    r = client.patch(f"{API}/umkm/{owner.umkm_id}", json={"consent_share_data": True}, headers=inst.headers)
    assert r.status_code == 403
    assert client.patch(f"{API}/umkm/{owner.umkm_id}", json={"pv_kwp": 1}, headers=bank.headers).status_code == 403

    # ganti nomor → verifikasi batal
    r = client.post(f"{API}/umkm/{owner.umkm_id}/phone/mark-verified", headers=admin_headers)
    assert r.status_code == 200 and r.json()["phone_verified"] is True
    r = client.patch(f"{API}/umkm/me", json={"phone_whatsapp": "081311112222"}, headers=owner.headers)
    assert r.status_code == 200
    assert r.json()["phone_whatsapp"] == "6281311112222" and r.json()["phone_verified"] is False
    assert client.patch(f"{API}/umkm/me", json={"unknown": 1}, headers=owner.headers).status_code == 422


def test_daily_brief_works_for_api_registered_umkm(client, make_user, db_call):
    """Alur nyata: daftar → isi profil mesin lewat API → brief harian 200 dengan hemat idle > 0."""
    u = make_user("umkm")
    assert client.post(f"{API}/umkm/me/machines", json=MACHINE, headers=u.headers).status_code == 201
    r = client.get(f"{API}/agent/whatsapp/daily-brief", params={"solver": "greedy"}, headers=u.headers)
    assert r.status_code == 200, r.text
    plan = r.json()["plan"]
    assert plan["savings_idr"] > 0  # idle 60 menit dari profil mesin kini masuk kebiasaan lama
    assert not any("lebih mahal" in n for n in plan["notes"])
    assert any("Beban dasar memakai asumsi" in n for n in plan["notes"])


def test_machine_suggestions_from_ledger(client, make_user, db_call):
    u = make_user("umkm")
    end = _today() - timedelta(days=1)

    async def write(s):
        entries = []
        for k in range(7):
            d = end - timedelta(days=k)
            for h in range(24):
                entries.append(HourlyEnergy(d, h, "Baseload / Background", 0.2))
                if 9 <= h < 13:
                    entries.append(HourlyEnergy(d, h, "Setrika Pemanas Uap", 1.2))
        await upsert_ledger(s, u.umkm_id, entries)
        await s.commit()
    db_call(write)
    r = client.get(f"{API}/umkm/me/machines/suggestions", params={"days": 7}, headers=u.headers)
    assert r.status_code == 200, r.text
    sug = r.json()["suggestions"]
    assert len(sug) == 1
    s0 = sug[0]
    assert s0["label"] == "Setrika Pemanas Uap" and s0["power_w"] == pytest.approx(1200)
    assert s0["daily_runtime_minutes"] == 240 and s0["habit_start_hour"] == 9
    assert s0["idle_minutes_habit"] == 0 and s0["appliance_class"] == 3


# ── jobs: idle & beban dasar terukur ───────────────────────────────────────
def test_profiles_to_jobs_maps_idle_and_cooldown():
    p = SimpleNamespace(**{**MACHINE, "is_flexible": True, "idle_power_w": 500.0, "cooldown_minutes": 45})
    out, notes = jobs.profiles_to_jobs([p])
    assert not notes
    j = out[0]
    assert j.idle_minutes_habit == 60 and j.idle_power_w == 500.0 and j.cooldown_minutes == 45


def test_measured_baseload_from_ledger(client, make_user, db_call):
    u = make_user("umkm")
    end = _today() - timedelta(days=1)

    async def run(s):
        assert await jobs.measured_baseload_w(s, u.umkm_id, end=end) is None
        entries = [HourlyEnergy(end - timedelta(days=k), h, "Baseload / Background", 0.15)
                   for k in range(3) for h in range(24)]
        await upsert_ledger(s, u.umkm_id, entries)
        await s.commit()
        return await jobs.measured_baseload_w(s, u.umkm_id, end=end)

    assert db_call(run) == pytest.approx(150.0)


# ── nota mingguan: hari data berbeda ───────────────────────────────────────
def test_weekly_nota_compares_daily_average_when_days_differ():
    from app.services.whatsapp_agent import MachineWeekUsage, generate_weekly_nota

    usage = [MachineWeekUsage("Setrika Pemanas Uap", kwh=70, cost_idr=100_000, prev_kwh=30, prev_cost_idr=42_857)]
    start, end = date(2026, 10, 31), date(2026, 11, 6)
    msg = generate_weekly_nota("Konveksi", start, end, usage, days_this_week=7, days_prev_week=3)
    assert "naik 133%" not in msg
    assert "rata-rata per hari" in msg and "tetap" in msg
    assert "minggu ini 7 hari, minggu lalu 3 hari" in msg
    msg0 = generate_weekly_nota("Konveksi", start, end, usage, days_this_week=7, days_prev_week=0)
    assert "naik" not in msg0 and "Belum dibandingkan" in msg0


def test_safe_name_strips_links():
    from app.services.whatsapp_agent import generate_daily_brief, safe_name

    assert safe_name("Toko Baju https://evil.example/login *PROMO*") == "Toko Baju PROMO"
    assert "bit.ly" not in safe_name("Hadiah bit.ly/abc klik")
    assert safe_name("") == "Usaha Anda"
    from app.agent.planner import default_jobs, plan_day

    plan = plan_day(default_jobs(), date(2026, 11, 10), solver="greedy")
    assert "http" not in generate_daily_brief(plan, "Promo http://x.co/a", date(2026, 11, 10))


def test_scheduler_skips_unverified_and_inactive(client, make_user, db_call, admin_headers):
    from app.models import MachineProfile
    from app.models.types import utcnow

    a = make_user("umkm")
    b = make_user("umkm")

    async def setup(s):
        for uid in (a.umkm_id, b.umkm_id):
            s.add(MachineProfile(umkm_id=uid, machine_id="m", label="Mesin", appliance_class=1, power_w=1000,
                                 daily_runtime_minutes=60, earliest_hour=7, deadline_hour=17, is_flexible=True,
                                 min_continuous_minutes=15))
        umkm_b = await s.get(UMKM, b.umkm_id)
        umkm_b.phone_verified_at = utcnow()
        await s.commit()
        return await jobs.eligible_umkm_ids(s)

    ids = db_call(setup)
    assert a.umkm_id not in ids and b.umkm_id in ids
    client.patch(f"{API}/auth/users/{b.id}/status", json={"is_active": False}, headers=admin_headers)

    async def again(s):
        return await jobs.eligible_umkm_ids(s), await jobs.umkm_with_phone_ids(s)

    ids, weekly_ids = db_call(again)
    assert b.umkm_id not in ids and b.umkm_id not in weekly_ids


# ── WhatsApp Meta template ─────────────────────────────────────────────────
def test_meta_scheduled_message_uses_template(monkeypatch):
    import asyncio

    from app.services.whatsapp_sender import send_whatsapp, template_param

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    monkeypatch.setattr(settings, "whatsapp_api_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "123")
    monkeypatch.setattr(settings, "whatsapp_meta_template_name", "waskita_brief")
    res = asyncio.run(send_whatsapp("081234567890", "Baris 1\nBaris   2", provider="meta",
                                    transport=httpx.MockTransport(handler), scheduled=True))
    assert res.status == "sent"
    assert seen["body"]["type"] == "template"
    assert seen["body"]["template"]["name"] == "waskita_brief"
    param = seen["body"]["template"]["components"][0]["parameters"][0]["text"]
    assert "\n" not in param and param == "Baris 1 | Baris 2"
    res = asyncio.run(send_whatsapp("081234567890", "Balasan", provider="meta",
                                    transport=httpx.MockTransport(handler)))
    assert seen["body"]["type"] == "text"
    assert len(template_param("x" * 5000)) == 1024


# ── rapor POST tidak pernah "terukur" ──────────────────────────────────────
def test_post_scorecard_rejects_terukur_and_is_watermarked(client, umkm_user):
    sizing = {"recommended_kwp": 3.0, "capex_idr": 31_500_000, "annual_savings_idr": 6_000_000,
              "npv_idr": 20_000_000, "payback_period_years": 5.2}
    payload = {"umkm_name": "Uji", "avg_monthly_bill_idr": 1_000_000, "sizing": sizing,
               "load_data_source": "terukur"}
    r = client.post(f"{API}/agent/reports/bankability-scorecard", json=payload, headers=umkm_user.headers)
    assert r.status_code == 422
    payload["load_data_source"] = "input_pengguna"
    r = client.post(f"{API}/agent/reports/bankability-scorecard", json=payload, headers=umkm_user.headers)
    card = r.json()
    assert card["report_meta"]["data_verified_by_waskita"] is False
    assert "tidak diverifikasi WASKITA" in card["report_meta"]["data_verification"]
    assert card["data_sources"]["load_profile_measured"] is False


# ── planner: toleransi & nilai SoC ─────────────────────────────────────────
def test_equal_cost_has_no_negative_savings_note():
    from app.agent.planner import plan_day
    from app.schemas.dispatch import MachineJob

    job = MachineJob(**{**MACHINE, "idle_minutes_habit": 0})
    plan = plan_day([job], date(2026, 11, 10), solver="greedy")
    assert plan.savings_idr == 0.0 and str(plan.savings_idr) == "0.0"
    assert str(plan.savings_pct) == "0.0"
    assert not any("lebih mahal" in n for n in plan.notes)


def test_battery_gives_no_free_energy_without_pv():
    from app.agent.planner import default_jobs, plan_day
    from app.digital_twin.battery import Battery

    d = date(2025, 7, 15)
    no_bat = plan_day(default_jobs(), d, kwp=0.0, solver="greedy")
    with_bat = plan_day(default_jobs(), d, kwp=0.0, battery=Battery.from_kwh(10.0), solver="greedy")
    # Tanpa PV, baterai tidak boleh membuat biaya lebih murah daripada tanpa baterai.
    assert with_bat.cost_idr >= no_bat.cost_idr - 1e-6
    assert with_bat.baseline_cost_idr >= no_bat.baseline_cost_idr - 1e-6
    assert with_bat.soc_deficit_cost_idr > 0


def test_ortools_values_soc_deficit_too():
    from app.agent.planner import default_jobs, plan_day
    from app.digital_twin.battery import Battery

    d = date(2025, 7, 15)
    no_bat = plan_day(default_jobs(), d, kwp=0.0, solver="ortools")
    with_bat = plan_day(default_jobs(), d, kwp=0.0, battery=Battery.from_kwh(10.0), solver="ortools")
    assert with_bat.cost_idr >= no_bat.cost_idr - 1e-6


def test_habit_pv_used_never_exceeds_generation():
    from app.digital_twin.battery import Battery  # noqa: F401
    from app.sizing.annual import representative_days
    from app.sizing.compare import _evaluate_day
    from app.agent.planner import default_jobs

    rep = [r for r in representative_days(2024, settings.site_latitude, settings.site_longitude) if r.month == 7][0]
    for kwp in (0.0, 2.0):
        ev = _evaluate_day(default_jobs(), rep, kwp, None, 10.0, settings.site_latitude,
                           settings.site_longitude, False)
        assert ev.habit_pv_used_kwh <= ev.pv_generated_kwh + 1e-6
        if kwp == 0.0:
            assert ev.habit_pv_used_kwh == pytest.approx(0.0, abs=1e-9)


def test_compare_idle_only_target_claims_no_panel_reduction():
    from app.schemas.sizing import CompareRequest
    from app.sizing.compare import compare_sizing_with_agent

    res = compare_sizing_with_agent(
        CompareRequest(target_savings_pct=3, kwp_candidates=[1, 2], reference_year=2024)
    )
    assert res.min_kwp_agent == 0.0
    assert res.kwp_reduction is None and res.capex_reduction_idr is None
    assert res.agent_reduces_panel is False
    assert "TANPA PLTS" in res.headline and "100%" not in res.headline


# ── sizing: baterai dibandingkan pada data yang sama ───────────────────────
def test_tiny_battery_matches_no_battery_candidate():
    from app.schemas.sizing import DailyLoadProfile, SizingRequest
    from app.sizing import calculate_optimal_sizing

    profiles = []
    for i in range(31):
        day_kw = 0.6 if i < 17 else 3.0
        hourly = [day_kw if 7 <= h < 17 else 0.3 for h in range(24)]
        profiles.append(DailyLoadProfile(date=date(2025, 3, 1) + timedelta(days=i), hourly_kwh=hourly))
    res = calculate_optimal_sizing(SizingRequest(
        load_profiles=profiles, reference_year=2024, include_battery=True, battery_options_kwh=[0.001, 2.5],
    ))
    by = {}
    for c in res.candidates:
        by.setdefault(c.kwp, {})[c.battery_kwh] = c
    common = [k for k, v in by.items() if 0.0 in v and 0.001 in v]
    assert common
    for k in common:
        a, b = by[k][0.0], by[k][0.001]
        assert b.annual_savings_idr == pytest.approx(a.annual_savings_idr, rel=0.02, abs=2_000)
    assert res.annual_savings_idr <= res.annual_bill_before_idr
    assert res.annual_self_consumption_kwh <= res.annual_load_kwh + 1e-6
    # beban malam 0,3 kW tidak bisa dari PV tanpa baterai besar → solar fraction < 100 %
    assert res.solar_fraction_pct < 90


# ── disaggregator: replay sampel tersimpan tidak kehilangan energi ─────────
def test_replay_gap_preserves_energy():
    from app.nilm.disaggregator import LoadDisaggregator
    from app.nilm.event_detector import TelemetrySample
    from app.services_data.ingest import replay_max_gap_s

    def run(max_gap):
        dis = LoadDisaggregator(max_gap_s=max_gap)
        t = datetime(2026, 10, 1, 9, 0, tzinfo=local_tz())
        step = 0
        while t.hour == 9:
            dis.push(TelemetrySample(timestamp=t, p_active=1000.0, q_reactive=0.0, v_rms=220.0,
                                     i_rms=4.5, frequency=50.0))
            t += timedelta(seconds=10 if step % 2 == 0 else 11)
            step += 1
        return sum(e.kwh for e in dis.flush_hourly_energy())

    assert run(10.0) < 0.97  # perilaku lama: Δt dipotong → kurang ±5 %
    assert run(replay_max_gap_s()) == pytest.approx(1.0, rel=0.02)


# ── cuaca: koordinat di luar wilayah tidak memicu unduhan ──────────────────
def test_weather_no_network_outside_service_area(tmp_path):
    from app.digital_twin.weather import WeatherProvider

    calls = []

    def http(url, timeout):
        calls.append(url)
        raise RuntimeError("tidak boleh dipanggil")

    wp = WeatherProvider(cache_dir=tmp_path, allow_network=True, http_get_json=http)
    assert wp.load_year(60.0, 10.0, 2024) is None
    assert calls == []


# ── migrasi aditif kolom baru pada DB lama ─────────────────────────────────
def test_additive_migration_adds_new_columns(tmp_path):
    from sqlalchemy import create_engine, inspect, text

    import app.models  # noqa: F401
    from app.core.database import _add_missing_columns

    eng = create_engine(f"sqlite:///{(tmp_path / 'lama.db').as_posix()}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE machine_profiles (id INTEGER PRIMARY KEY, umkm_id INTEGER, machine_id VARCHAR(64), "
            "label VARCHAR(80), appliance_class INTEGER, power_w FLOAT, daily_runtime_minutes INTEGER, "
            "earliest_hour INTEGER, deadline_hour INTEGER, habit_start_hour INTEGER, is_flexible BOOLEAN, "
            "min_continuous_minutes INTEGER)"
        ))
        conn.execute(text("INSERT INTO machine_profiles (id, umkm_id, machine_id, label, appliance_class, power_w, "
                          "daily_runtime_minutes, earliest_hour, deadline_hour, is_flexible, min_continuous_minutes) "
                          "VALUES (1, 1, 'm', 'Mesin', 1, 1000, 60, 7, 17, 1, 15)"))
        _add_missing_columns(conn)
    cols = {c["name"] for c in inspect(eng).get_columns("machine_profiles")}
    assert {"idle_minutes_habit", "idle_power_w", "cooldown_minutes"} <= cols
    with eng.connect() as conn:
        row = conn.execute(text("SELECT idle_minutes_habit, idle_power_w FROM machine_profiles")).one()
    assert row[0] == 0 and row[1] is None

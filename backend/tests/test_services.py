"""Tes layanan "Hemat": pesan WhatsApp, pengirim, penjadwal, job, rapor PDF, endpoint agen."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import UMKM, DailyPlan, MachineProfile, MessageLog
from app.nilm.disaggregator import HourlyEnergy
from app.services import jobs, scheduler, scorecard_data
from app.services.scorecard_generator import (
    SCORE_WEIGHTS,
    generate_bankability_scorecard,
    render_scorecard_pdf,
)
from app.services.whatsapp_agent import (
    MAX_MESSAGE_CHARS,
    MachineWeekUsage,
    format_rentang,
    format_rupiah,
    format_tanggal,
    generate_daily_brief,
    generate_weekly_nota,
)
from app.services.whatsapp_sender import normalize_phone, send_whatsapp
from app.services_data.ledger import upsert_ledger


# ── Helper ─────────────────────────────────────────────────────────────────
def _plan(jobs_list=None, day=date(2026, 11, 9), solver="greedy"):
    from app.agent.planner import default_jobs, plan_day

    return plan_day(jobs_list or default_jobs(), day, kwp=0.0, solver=solver)


def _job(mid, label, minutes=120, power=1000.0, earliest=7, deadline=17, habit=None, min_cont=15):
    from app.schemas.dispatch import MachineJob

    return MachineJob(
        machine_id=mid, label=label, power_w=power, daily_runtime_minutes=minutes,
        earliest_hour=earliest, deadline_hour=deadline, habit_start_hour=habit, min_continuous_minutes=min_cont,
    )


def _sizing(**over):
    base = dict(
        recommended_kwp=4.0, capex_idr=42_000_000.0, annual_generation_kwh=5_600.0,
        annual_self_consumption_kwh=5_100.0, annual_curtailment_kwh=500.0, self_consumption_rate_pct=91.0,
        annual_savings_idr=7_400_000.0, lcoe_idr_per_kwh=900.0, npv_idr=38_000_000.0,
        payback_period_years=5.7, co2_avoided_kg_per_year=4_000.0, permen_esdm_compliant=False,
        annual_bill_before_idr=30_000_000.0, recommendation_note="uji", pv_source="clearsky_scaled",
        regulatory_checks={"connected_power_kva": 5.5, "kwp_within_connected_power": True,
                           "export_not_credited_modeled": True},
    )
    base.update(over)
    return base


def _today():
    return jobs.local_today()


# ── Format tanggal & angka ────────────────────────────────────────────────
def test_format_tanggal_indonesia_tanpa_strftime():
    assert format_tanggal(date(2026, 11, 8)) == "Minggu, 8 November 2026"
    assert format_tanggal(date(2026, 1, 5), with_day=False) == "5 Januari 2026"
    assert format_rentang(date(2026, 11, 1), date(2026, 11, 7)) == "1–7 Nov 2026"
    assert format_rentang(date(2025, 12, 29), date(2026, 1, 4)) == "29 Des 2025 – 4 Jan 2026"
    assert format_rupiah(1234567.4) == "Rp 1.234.567"
    assert format_rupiah(-500) == "-Rp 500"


# ── Brief harian ───────────────────────────────────────────────────────────
def test_brief_dari_planresult_semua_mesin_dan_rentang():
    plan = _plan()
    msg = generate_daily_brief(plan, "Konveksi Bu Sri", date(2026, 11, 9))
    assert "WASKITA" in msg and "NOTA LISTRIK" not in msg.upper().replace("WASKITA", "")
    assert "Senin, 9 November 2026" in msg
    assert len(msg) <= MAX_MESSAGE_CHARS
    for m in plan.machines:
        if plan.schedule[:, plan.machine_ids.index(m.machine_id)].any():
            assert m.label in msg
    # rentang jam berbentuk HH:MM–HH:MM
    assert "–" in msg and ":" in msg


def test_brief_banyak_blok_per_mesin():
    from app.agent.planner import PlanResult

    sched = np.zeros((96, 2), dtype=np.int8)
    sched[36:40, 0] = 1  # 09:00–10:00
    sched[52:56, 0] = 1  # 13:00–14:00
    sched[40:48, 1] = 1  # 10:00–12:00
    z = np.zeros(96)
    plan = PlanResult(
        schedule=sched, machine_ids=["jahit", "setrika"], load_w=z, pv_w=z, grid_w=z, curtail_w=z,
        cost_idr=1000.0, baseline_load_w=z, baseline_cost_idr=1500.0, savings_idr=500.0, savings_pct=33.3,
        solver_used="greedy", deadlines_met=True, battery_soc_wh=None,
    )
    msg = generate_daily_brief(plan, "UMKM A", date(2026, 11, 9))
    assert "jahit: 09:00–10:00, 13:00–14:00" in msg
    assert "setrika: 10:00–12:00" in msg
    assert "Rp 500" in msg and "33,3%" in msg


def test_brief_penghematan_negatif_jujur_dan_peringatan_tenggat():
    from app.schemas.dispatch import DispatchResponse, MachinePlan, TimeBlock

    resp = DispatchResponse(
        target_date=date(2026, 11, 9), schedule=[], total_grid_kwh=10, total_pv_kwh=0, total_cost_idr=15000,
        baseline_cost_idr=14000, savings_idr=-1000, savings_pct=-7.1, solver_used="greedy", curtailment_kwh=0,
        deadlines_met=False,
        machines=[
            MachinePlan(machine_id="m1", label="Mesin Obras", power_w=500, is_flexible=True, runtime_minutes=60,
                        scheduled_minutes=30, window="07:00–17:00",
                        blocks=[TimeBlock(start="09:00", end="09:30", slots=2)], deadline_met=False),
        ],
    )
    msg = generate_daily_brief(resp, "UMKM B")
    assert "LEBIH MAHAL" in msg and "Rp 1.000" in msg
    assert "PERHATIAN" in msg and "Mesin Obras" in msg
    assert "Senin, 9 November 2026" in msg


def test_brief_dispatchresponse_lama_dari_slot():
    from app.schemas.dispatch import DispatchResponse, SlotSchedule

    slots = [
        SlotSchedule(slot_index=t, time_label="", machines_on=["a", "b"] if 40 <= t < 44 else (["a"] if 44 <= t < 46 else []),
                     state=1 if 40 <= t < 46 else 0, p_load_w=0, p_pv_w=0, p_grid_w=0, cost_idr=0)
        for t in range(96)
    ]
    resp = DispatchResponse(target_date=date(2026, 11, 9), schedule=slots, total_grid_kwh=0, total_pv_kwh=0,
                            total_cost_idr=0, baseline_cost_idr=0, savings_idr=0, savings_pct=0,
                            solver_used="x", curtailment_kwh=0)
    msg = generate_daily_brief(resp, "UMKM C")
    assert "- a: 10:00–11:30" in msg
    assert "- b: 10:00–11:00" in msg


def test_brief_selalu_di_bawah_batas_karakter():
    jobs_list = [_job(f"m{i}", f"Mesin Produksi Sangat Panjang Namanya Nomor {i}", minutes=30) for i in range(25)]
    plan = _plan(jobs_list)
    msg = generate_daily_brief(plan, "UMKM dengan nama yang cukup panjang sekali " * 3, date(2026, 11, 9))
    assert len(msg) <= MAX_MESSAGE_CHARS
    assert "mesin lain" in msg


# ── Nota mingguan ──────────────────────────────────────────────────────────
def test_nota_mingguan_perbandingan_dan_tips_idle():
    usage = [
        MachineWeekUsage("Setrika Uap", kwh=20, cost_idr=28_900, prev_kwh=16, prev_cost_idr=23_100,
                         off_hours_kwh=1.5, off_hours_cost_idr=2_167, off_hours_hours=3),
        MachineWeekUsage("Mesin Jahit", kwh=5, cost_idr=7_200, prev_kwh=6, prev_cost_idr=8_700),
        MachineWeekUsage("Baseload / Background", kwh=8, cost_idr=11_500, prev_kwh=8, prev_cost_idr=11_500),
    ]
    msg = generate_weekly_nota("Laundry Pak Budi", date(2026, 11, 1), date(2026, 11, 7), usage)
    assert "Nota Mingguan" in msg and "WASKITA" in msg
    assert "1–7 Nov 2026" in msg
    assert "Setrika Uap: 20,0 kWh, Rp 28.900 (naik 25%)" in msg
    assert "Mesin Jahit" in msg and "turun 17%" in msg
    assert "Paling boros: *Setrika Uap*" in msg
    assert "di luar jam kerja 3 jam" in msg
    assert len(msg) <= MAX_MESSAGE_CHARS


def test_nota_mingguan_tanpa_data():
    msg = generate_weekly_nota("X", date(2026, 11, 1), date(2026, 11, 7), [])
    assert "Belum ada data" in msg


# ── Pengirim WhatsApp ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("081234567890", "6281234567890"),
        ("+62 812-3456-7890", "6281234567890"),
        ("6281234567890", "6281234567890"),
        ("81234567890", "6281234567890"),
        ("0062812345678", "62812345678"),
        ("620812345678", "62812345678"),
        ("0274123456", None),
        ("", None),
        (None, None),
        ("abc", None),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def _run(coro):
    return asyncio.run(coro)


def test_send_provider_none_skipped():
    res = _run(send_whatsapp("081234567890", "halo", provider="none"))
    assert res.status == "skipped" and res.provider == "none"


def test_send_fonnte_sukses(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "tok-fonnte")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"status": True, "id": ["123"], "detail": "success"})

    res = _run(send_whatsapp("0812-3456-7890", "Halo UMKM", provider="fonnte", transport=httpx.MockTransport(handler)))
    assert res.status == "sent" and res.message_id == "123"
    assert seen["url"] == "https://api.fonnte.com/send"
    assert seen["auth"] == "tok-fonnte"
    assert "target=6281234567890" in seen["body"] and "message=Halo+UMKM" in seen["body"]


def test_send_fonnte_ditolak(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "tok")
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"status": False, "reason": "invalid token"}))
    res = _run(send_whatsapp("081234567890", "x", provider="fonnte", transport=transport))
    assert res.status == "failed" and "invalid token" in res.error


def test_send_fonnte_tanpa_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "")
    res = _run(send_whatsapp("081234567890", "x", provider="fonnte"))
    assert res.status == "failed" and "TOKEN" in res.error


def test_send_meta_sukses(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "tok-meta")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "10987")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.X"}]})

    res = _run(send_whatsapp("081234567890", "Halo", provider="meta", transport=httpx.MockTransport(handler)))
    assert res.status == "sent" and res.message_id == "wamid.X"
    assert seen["url"] == f"https://graph.facebook.com/{settings.whatsapp_meta_api_version}/10987/messages"
    assert seen["auth"] == "Bearer tok-meta"
    assert seen["json"]["to"] == "6281234567890"
    assert seen["json"]["type"] == "text" and seen["json"]["text"]["body"] == "Halo"


def test_send_meta_di_luar_24_jam_butuh_template(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "tok")
    monkeypatch.setattr(settings, "whatsapp_phone_number_id", "1")
    transport = httpx.MockTransport(
        lambda r: httpx.Response(400, json={"error": {"code": 131047, "message": "Re-engagement message"}})
    )
    res = _run(send_whatsapp("081234567890", "x", provider="meta", transport=transport))
    assert res.status == "failed" and "template" in res.error and res.http_status == 400


def test_send_timeout_dan_galat_tidak_melempar(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_api_token", "tok")

    def timeout_handler(request):
        raise httpx.ReadTimeout("lambat", request=request)

    def boom(request):
        raise RuntimeError("tak terduga")

    res = _run(send_whatsapp("081234567890", "x", provider="fonnte", transport=httpx.MockTransport(timeout_handler)))
    assert res.status == "failed" and "Waktu habis" in res.error
    res = _run(send_whatsapp("081234567890", "x", provider="fonnte", transport=httpx.MockTransport(boom)))
    assert res.status == "failed"
    res = _run(send_whatsapp("12345", "x", provider="fonnte"))
    assert res.status == "failed" and "tidak valid" in res.error


# ── Rapor kelayakan ────────────────────────────────────────────────────────
def test_scorecard_label_netral_dan_bobot():
    card = generate_bankability_scorecard("UMKM A", "Jl. A", "Konveksi", _sizing(), 2_500_000)
    text = json.dumps(card, ensure_ascii=False)
    for banned in ("tier A", "tier B", "bunga preferensial", "BNI", "BRI", "NOTA LISTRIK", "Nota Listrik"):
        assert banned not in text
    assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9
    score = card["bankability_score"]
    assert score["calibrated"] is False and "heuristik" in score["method_note"]
    assert score["risk_category"] in ("Indikasi kelayakan kuat", "Indikasi kelayakan sedang", "Perlu kajian lanjut")
    assert score["breakdown"]["compliance_score"] == 100.0
    # PBP 5,7 th → (13-5,7)/10 = 73; PI = 38/42 → 90,5
    assert score["breakdown"]["payback_period_score"] == pytest.approx(73.0)
    assert score["breakdown"]["npv_score"] == pytest.approx(90.5, abs=0.1)


def test_scorecard_daya_tersambung_tidak_diketahui_dan_pbp_tak_balik_modal():
    card = generate_bankability_scorecard(
        "B", "", "x", _sizing(regulatory_checks={"kwp_within_connected_power": None}, payback_period_years=99.9,
                              npv_idr=-5_000_000.0), 1_000_000,
    )
    br = card["bankability_score"]["breakdown"]
    assert br["compliance_score"] == 50.0
    assert br["payback_period_score"] == 0.0 and br["npv_score"] == 0.0
    assert card["bankability_score"]["category_code"] == "perlu_kajian"
    assert any("Daya tersambung" in n for n in card["notes"])
    # Kepatuhan yang tidak diperiksa harus null, bukan false (dibaca bank lewat JSON).
    habit = card["plts_recommendation"]["current_habit"]
    assert habit["permen_esdm_2_2024_compliant"] is None
    assert habit["kwp_within_connected_power"] is None


def test_scorecard_kepatuhan_ikut_regulatory_checks():
    card = generate_bankability_scorecard("C", "", "x", _sizing(), 1_000_000)
    habit = card["plts_recommendation"]["current_habit"]
    assert habit["permen_esdm_2_2024_compliant"] is True
    assert habit["kwp_within_connected_power"] is True


def test_scorecard_pdf_lengkap():
    card = generate_bankability_scorecard(
        "Konveksi Bu Sri & Anak <Uji>", "Jl. Melati 3", "Konveksi", _sizing(), 2_500_000,
        audit_period_days=21, audit_period_start=date(2026, 10, 1), audit_period_end=date(2026, 10, 21),
        machine_usage=[{"label": "Setrika Uap", "kwh": 120.5, "cost_idr": 174_000},
                       {"label": "Mesin Jahit", "kwh": 30, "cost_idr": 43_300}],
        agent_compare={"target_monthly_savings_idr": 600_000, "min_kwp_habit": 4.0, "min_kwp_agent": 3.0,
                       "kwp_reduction": 1.0, "capex_reduction_idr": 10_500_000, "headline": "Agen menghemat 1 kWp"},
        load_data_source="terukur",
    )
    assert card["machine_usage"][0]["share_pct"] == pytest.approx(80.1, abs=0.1)
    assert card["plts_recommendation"]["agent_compare"]["min_kwp_agent"] == 3.0
    assert card["data_sources"]["load_profile_measured"] is True
    pdf = render_scorecard_pdf(card)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000


# ── Penjadwal ──────────────────────────────────────────────────────────────
def test_scheduler_noop_bila_nonaktif(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", False)
    assert scheduler.start_scheduler() is None
    scheduler.shutdown_scheduler()


def test_scheduler_job_harian_dan_mingguan(monkeypatch):
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_send_hour", 17)
    monkeypatch.setattr(settings, "whatsapp_send_minute", 30)
    monkeypatch.setattr(settings, "weekly_report_weekday", 5)

    async def main():
        sched = scheduler.start_scheduler()
        try:
            assert sched is not None and sched.running
            daily = sched.get_job(scheduler.DAILY_JOB_ID)
            weekly = sched.get_job(scheduler.WEEKLY_JOB_ID)
            assert daily is not None and weekly is not None
            fields = {f.name: str(f) for f in weekly.trigger.fields}
            assert fields["day_of_week"] == "sat" and fields["hour"] == "17" and fields["minute"] == "30"
            nxt = daily.next_run_time
            assert nxt.utcoffset() == timedelta(hours=7)
            assert (nxt.hour, nxt.minute) == (17, 30)
        finally:
            scheduler.shutdown_scheduler()
        assert scheduler.get_scheduler() is None

    asyncio.run(main())


# ── Job & endpoint (pakai DB tes) ──────────────────────────────────────────
def _add_profiles(db_call, umkm_id: int, n: int = 2):
    async def write(s):
        for i in range(n):
            s.add(MachineProfile(
                umkm_id=umkm_id, machine_id=f"mesin{i}", label=f"Mesin Uji {i}", appliance_class=1,
                power_w=1200.0 + 100 * i, daily_runtime_minutes=90 + 30 * i, earliest_hour=7, deadline_hour=17,
                habit_start_hour=8, is_flexible=True, min_continuous_minutes=30,
            ))
        await s.commit()
    db_call(write)


def _seed_ledger(db_call, umkm_id: int, days: int, end: date | None = None):
    end = end or (_today() - timedelta(days=1))

    async def write(s):
        entries = []
        for k in range(days):
            d = end - timedelta(days=k)
            for h in range(24):
                entries.append(HourlyEnergy(d, h, "Baseload / Background", 0.3))
                if 8 <= h < 15:
                    entries.append(HourlyEnergy(d, h, "Setrika Uap", 1.0 if k < 7 else 0.8))
                if h in (5, 20) and k < 7:
                    entries.append(HourlyEnergy(d, h, "Setrika Uap", 0.4))  # di luar jam kerja
        await upsert_ledger(s, umkm_id, entries)
        await s.commit()
    db_call(write)


def _verify_phone(db_call, umkm_id: int):
    from app.models.types import utcnow

    async def write(s):
        umkm = await s.get(UMKM, umkm_id)
        umkm.phone_verified_at = utcnow()
        await s.commit()
    db_call(write)


def test_job_harian_simpan_plan_dan_log(client, db_call, make_user):
    u = make_user("umkm")
    _add_profiles(db_call, u.umkm_id)
    _verify_phone(db_call, u.umkm_id)
    target = _today() + timedelta(days=1)

    summary = client.portal.call(lambda: jobs.run_daily_briefs(target, solver="greedy"))
    mine = [r for r in summary["results"] if r["umkm_id"] == u.umkm_id]
    assert len(mine) == 1 and mine[0]["status"] == "skipped"  # WHATSAPP_PROVIDER=none di tes
    assert "Mesin Uji 0" in mine[0]["message"]

    async def check(s):
        plans = (await s.execute(select(DailyPlan).where(DailyPlan.umkm_id == u.umkm_id))).scalars().all()
        logs = (await s.execute(select(MessageLog).where(MessageLog.umkm_id == u.umkm_id))).scalars().all()
        return plans, logs
    plans, logs = db_call(check)
    assert len(plans) == 1 and plans[0].day == target and plans[0].payload_json["machines"]
    assert len(logs) == 1 and logs[0].kind == "daily" and logs[0].status == "skipped"


def test_job_harian_pakai_pv_umkm(client, db_call, make_user):
    u = make_user("umkm")
    _add_profiles(db_call, u.umkm_id, n=1)

    async def set_pv(s):
        umkm = await s.get(UMKM, u.umkm_id)
        umkm.pv_kwp = 3.0
        umkm.battery_kwh = 5.0
        await s.commit()
    db_call(set_pv)

    async def run(s):
        umkm = await s.get(UMKM, u.umkm_id)
        return await jobs.run_daily_brief_for_umkm(s, umkm, date(2026, 11, 10), send=False, solver="greedy")
    out = db_call(run)
    assert out.status == "not_sent" and out.plan_id
    assert "PLTS diperkirakan" in out.message


def test_job_mingguan(client, db_call, make_user):
    u = make_user("umkm")
    _seed_ledger(db_call, u.umkm_id, days=14)
    _verify_phone(db_call, u.umkm_id)
    summary = client.portal.call(lambda: jobs.run_weekly_notas())
    mine = [r for r in summary["results"] if r["umkm_id"] == u.umkm_id]
    assert mine and mine[0]["status"] == "skipped"
    assert "Setrika Uap" in mine[0]["message"] and "luar jam kerja" in mine[0]["message"]


def test_endpoint_brief_auth_dan_akses(client, db_call, make_user, admin_headers):
    owner = make_user("umkm")
    other = make_user("umkm")
    _add_profiles(db_call, owner.umkm_id)

    assert client.get("/api/v1/agent/whatsapp/daily-brief").status_code == 401
    r = client.get("/api/v1/agent/whatsapp/daily-brief", params={"solver": "greedy"}, headers=owner.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["umkm_id"] == owner.umkm_id and "WASKITA" in body["message"]
    assert body["char_count"] <= MAX_MESSAGE_CHARS
    assert body["target_date"] == (_today() + timedelta(days=1)).isoformat()

    r = client.get("/api/v1/agent/whatsapp/daily-brief", params={"umkm_id": owner.umkm_id}, headers=other.headers)
    assert r.status_code == 403
    r = client.get("/api/v1/agent/whatsapp/daily-brief", params={"solver": "greedy"}, headers=other.headers)
    assert r.status_code == 409  # belum ada profil mesin
    r = client.get("/api/v1/agent/whatsapp/daily-brief", headers=admin_headers)
    assert r.status_code == 422
    r = client.get("/api/v1/agent/whatsapp/daily-brief",
                   params={"umkm_id": owner.umkm_id, "solver": "greedy", "save_plan": True}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["plan_id"]


def test_endpoint_send_now(client, db_call, make_user, bank_user, monkeypatch):
    u = make_user("umkm")
    _add_profiles(db_call, u.umkm_id, n=1)
    # Nomor belum diverifikasi → ditolak.
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "daily", "solver": "greedy"}, headers=u.headers)
    assert r.status_code == 409 and "diverifikasi" in r.json()["detail"]
    # Verifikasi OTP (WHATSAPP_PROVIDER=none di tes → kode dikembalikan sebagai dev_code).
    r = client.post("/api/v1/umkm/me/phone/request-otp", headers=u.headers)
    assert r.status_code == 200, r.text
    code = r.json()["dev_code"]
    assert code and len(code) == 6
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/v1/umkm/me/phone/verify", json={"code": wrong}, headers=u.headers).status_code == 400
    r = client.post("/api/v1/umkm/me/phone/verify", json={"code": code}, headers=u.headers)
    assert r.status_code == 200 and r.json()["phone_verified"] is True
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "daily", "solver": "greedy"}, headers=u.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped" and r.json()["message_log_id"]
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "weekly"}, headers=u.headers)
    assert r.status_code == 200 and r.json()["kind"] == "weekly"
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"umkm_id": u.umkm_id}, headers=bank_user.headers)
    assert r.status_code == 403

    no_phone = make_user("umkm", phone_whatsapp=None)
    r = client.post("/api/v1/agent/whatsapp/send-now", json={}, headers=no_phone.headers)
    assert r.status_code == 409

    # Batas harian: hitung pesan sent/failed hari ini (provider palsu "failed" agar tercatat).
    from app.services import whatsapp_sender

    async def fake_send(phone, body, **kw):
        return whatsapp_sender.SendResult("failed", "fonnte", "uji")

    monkeypatch.setattr(jobs, "send_whatsapp", fake_send)
    monkeypatch.setattr(settings, "whatsapp_send_now_max_per_day", 1)
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "weekly"}, headers=u.headers)
    assert r.status_code == 200 and r.json()["status"] == "failed"
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "weekly"}, headers=u.headers)
    assert r.status_code == 429

    # Berhenti berlangganan → tidak dikirim.
    assert client.patch("/api/v1/umkm/me", json={"whatsapp_opt_out": True}, headers=u.headers).status_code == 200
    r = client.post("/api/v1/agent/whatsapp/send-now", json={"kind": "daily", "solver": "greedy"}, headers=u.headers)
    assert r.status_code == 409


def test_endpoint_weekly_nota(client, db_call, make_user):
    u = make_user("umkm")
    _seed_ledger(db_call, u.umkm_id, days=14)
    r = client.get("/api/v1/agent/reports/weekly-nota", headers=u.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    setrika = next(x for x in body["usage"] if x["label"] == "Setrika Uap")
    assert setrika["kwh"] == pytest.approx(7 * 7 * 1.0 + 7 * 2 * 0.4)
    assert setrika["prev_kwh"] == pytest.approx(7 * 7 * 0.8)
    assert setrika["off_hours_hours"] == 14
    assert "Paling boros" in body["message"]


def test_endpoint_scorecard_post_json_dan_pdf(client, umkm_user):
    payload = {"umkm_name": "UMKM Uji", "avg_monthly_bill_idr": 2_000_000, "sizing": _sizing()}
    assert client.post("/api/v1/agent/reports/bankability-scorecard", json=payload).status_code == 401
    r = client.post("/api/v1/agent/reports/bankability-scorecard", json=payload, headers=umkm_user.headers)
    assert r.status_code == 200, r.text
    assert r.json()["bankability_score"]["calibrated"] is False
    r = client.post("/api/v1/agent/reports/bankability-scorecard.pdf", json=payload, headers=umkm_user.headers)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    bad = dict(payload, sizing={"recommended_kwp": 1})
    assert client.post("/api/v1/agent/reports/bankability-scorecard", json=bad,
                       headers=umkm_user.headers).status_code == 422


def test_endpoint_scorecard_dari_db(client, db_call, make_user, monkeypatch):
    calls = {}

    def fake_sizing(profiles, connected_power_va):
        calls["days"] = len(profiles)
        calls["va"] = connected_power_va
        return SimpleNamespace(**_sizing())

    def fake_compare(jobs_list, target_pct, info):
        calls["target_pct"] = target_pct
        calls["n_jobs"] = len(jobs_list)
        calls["baseload_w"] = info.get("baseload_w")
        return {"target_monthly_savings_idr": 600_000, "min_kwp_habit": 4.0, "min_kwp_agent": 3.5,
                "kwp_reduction": 0.5, "capex_reduction_idr": 5_250_000, "headline": "uji"}

    monkeypatch.setattr(scorecard_data, "compute_habit_sizing", fake_sizing)
    monkeypatch.setattr(scorecard_data, "compute_agent_compare", fake_compare)

    owner = make_user("umkm", consent_share_data=True)
    _seed_ledger(db_call, owner.umkm_id, days=10)
    _add_profiles(db_call, owner.umkm_id)

    r = client.get("/api/v1/agent/reports/bankability-scorecard", headers=owner.headers)
    assert r.status_code == 200, r.text
    card = r.json()
    assert calls["days"] == 10 and calls["va"] == 5500 and calls["n_jobs"] == 2
    assert calls["baseload_w"] == pytest.approx(300.0)  # median terukur 0,3 kWh/jam, bukan default 800 W
    assert calls["target_pct"] == pytest.approx(7_400_000 / 30_000_000 * 100, abs=0.01)
    assert card["audit_period"]["days"] == 10
    assert card["data_sources"]["load_profile"] == "terukur"
    assert {u["label"] for u in card["machine_usage"]} >= {"Setrika Uap", "Baseload / Background"}
    assert card["plts_recommendation"]["agent_compare"]["min_kwp_agent"] == 3.5
    assert card["plts_recommendation"]["agent_compare"]["included_in_score"] is False
    assert "300 W" in card["plts_recommendation"]["agent_compare"]["basis"]
    assert card["report_meta"]["data_verified_by_waskita"] is True

    r = client.get("/api/v1/agent/reports/bankability-scorecard.pdf", headers=owner.headers)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    bank = make_user("bank")
    r = client.get("/api/v1/agent/reports/bankability-scorecard.pdf", params={"umkm_id": owner.umkm_id},
                   headers=bank.headers)
    assert r.status_code == 200
    disper = make_user("disperinaker")
    r = client.get("/api/v1/agent/reports/bankability-scorecard", params={"umkm_id": owner.umkm_id},
                   headers=disper.headers)
    assert r.status_code == 403

    no_consent = make_user("umkm", consent_share_data=False)
    r = client.get("/api/v1/agent/reports/bankability-scorecard", params={"umkm_id": no_consent.umkm_id},
                   headers=bank.headers)
    assert r.status_code == 403
    # data belum cukup → 409, bukan rapor karangan
    r = client.get("/api/v1/agent/reports/bankability-scorecard", headers=no_consent.headers)
    assert r.status_code == 409

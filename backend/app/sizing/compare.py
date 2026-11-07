"""
Ukuran PLTS dengan jadwal kebiasaan lama vs jadwal agen (fitur pembeda WASKITA).

Pertanyaan yang dijawab: "Untuk hemat tagihan sebesar target, berapa kWp
minimum yang dibutuhkan bila mesin tetap dinyalakan menurut kebiasaan lama,
dan berapa bila jadwalnya diatur agen?" Di bawah Permen ESDM No. 2/2024
(ekspor tidak dikreditkan), PV yang tidak terpakai saat itu juga terbuang,
sehingga menggeser beban ke jam surya bisa membuat panel yang sama lebih
bernilai — atau panel yang lebih kecil cukup.

Metode:
- 12 hari representatif (median energi PV per bulan, tahun acuan) berbobot
  jumlah hari sebenarnya; hari operasional = ``operating_days_per_week/7``
  dari hari di bulan itu, hari tutup = beban dasar saja.
- Untuk tiap (bulan, kWp): ``plan_day(..., solver="greedy")`` memberi biaya
  kebiasaan lama (dengan idle), kebiasaan lama tanpa idle, dan jadwal greedy.
  Mode ``ortools`` menambah OR-Tools dengan batas waktu kecil
  (``settings.sizing_compare_ortools_time_limit_s``) dan mengambil jadwal
  valid termurah. Jadwal agen tidak pernah dianggap lebih mahal daripada
  "kebiasaan lama tanpa idle" bila jadwal itu valid (agen selalu boleh
  mempertahankan jam lama).
- Hasil di-cache per (bulan, kWp, input) di memori proses.
- Batas waktu total ``settings.sizing_compare_time_budget_s``; bila habis,
  OR-Tools dimatikan, dan bila tetap habis, kandidat kWp sisanya dilewati
  (``timed_out=True``).

Tagihan yang dihitung = biaya energi (kWh × tarif) saja; biaya beban/abonemen
tidak ikut. Penjadwal cepat ini adalah batas bawah kemampuan agen penuh
(PPO/OR-Tools dengan waktu lebih panjang).
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional, Sequence

import numpy as np

from app.core.config import settings
from app.core.tariff import tariff_curve_idr_per_wh
from app.digital_twin.battery import Battery
from app.schemas.sizing import CompareRequest, ComparePoint, CompareResult
from app.sizing.annual import (
    RepresentativeDay,
    default_reference_year,
    representative_days,
    resolve_location,
    summarize_source,
)
from app.sizing.regulatory import connected_kva

logger = logging.getLogger(__name__)

_CACHE_MAX = 4096
REFINE_ITERS = 4
REFINE_MIN_STEP_KWP = 0.05
_cache: "OrderedDict[tuple, DayEval]" = OrderedDict()
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class DayEval:
    habit_cost: float
    habit_no_idle_cost: float
    agent_cost: float
    habit_pv_used_kwh: float
    agent_pv_used_kwh: float
    pv_generated_kwh: float
    deadlines_met: bool
    solver: str


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(key: tuple) -> Optional[DayEval]:
    with _cache_lock:
        v = _cache.get(key)
        if v is not None:
            _cache.move_to_end(key)
        return v


def _cache_put(key: tuple, value: DayEval) -> None:
    with _cache_lock:
        _cache[key] = value
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def _battery(battery_kwh: float) -> Optional[Battery]:
    return Battery.from_kwh(battery_kwh, c_rate=settings.battery_c_rate) if battery_kwh > 0 else None


def _evaluate_day(
    jobs: Sequence[Any],
    rep: RepresentativeDay,
    kwp: float,
    baseload_w: Optional[float],
    battery_kwh: float,
    lat: float,
    lon: float,
    use_ortools: bool,
) -> DayEval:
    """Biaya satu hari representatif: kebiasaan lama, tanpa idle, dan jadwal agen."""
    from app.agent.planner import build_problem, plan_day
    from app.digital_twin.factory_model import simulate_schedule, validate_schedule

    plan = plan_day(
        list(jobs), rep.day, kwp=kwp, baseload_w=baseload_w, battery=_battery(battery_kwh),
        solver="greedy", lat=lat, lon=lon,
    )
    pv_kwh = float(np.sum(plan.pv_w) * 0.25 / 1000.0)
    habit_cost = float(plan.baseline_cost_idr)
    habit_no_idle = float(plan.baseline_no_idle_cost_idr) if jobs else habit_cost
    # PV terpakai kebiasaan lama (dengan idle): beban − impor − ... dihitung dari grid & load.
    habit_used = float(np.sum(plan.baseline_load_w - (plan.baseline_grid_w if plan.baseline_grid_w is not None else 0.0))
                       * 0.25 / 1000.0)
    best_cost = float(plan.cost_idr) if plan.deadlines_met else float("inf")
    best_used = float(plan.pv_used_kwh)
    solver = "greedy"
    ok = bool(plan.deadlines_met)

    if jobs:
        problem = None
        if use_ortools:
            try:
                from app.agent.ortools_baseline import solve_milp_schedule

                problem = build_problem(list(jobs), rep.day, kwp, baseload_w, _battery(battery_kwh), lat, lon)
                res = solve_milp_schedule(
                    problem, time_limit_s=settings.sizing_compare_ortools_time_limit_s, num_workers=4
                )
                if res.schedule is not None and not validate_schedule(problem.machines, res.schedule):
                    sim = simulate_schedule(problem, res.schedule)
                    if sim.cost_idr < best_cost - 1e-6:
                        best_cost, best_used, solver, ok = sim.cost_idr, sim.pv_used_kwh, "ortools", True
            except Exception as exc:  # noqa: BLE001
                logger.warning("OR-Tools gagal pada sizing compare: %s", exc)
        # Agen selalu boleh mempertahankan jam lama (tanpa idle) bila jadwal itu valid.
        if plan.baseline_schedule is not None and not validate_schedule(plan.machines, plan.baseline_schedule):
            if habit_no_idle < best_cost - 1e-6:
                if problem is None:
                    problem = build_problem(list(jobs), rep.day, kwp, baseload_w, _battery(battery_kwh), lat, lon)
                sim = simulate_schedule(problem, plan.baseline_schedule)
                best_cost, best_used, solver, ok = sim.cost_idr, sim.pv_used_kwh, "jam-lama-tanpa-idle", True
    if not np.isfinite(best_cost):
        best_cost, best_used = float(plan.cost_idr), float(plan.pv_used_kwh)

    return DayEval(
        habit_cost=habit_cost,
        habit_no_idle_cost=habit_no_idle,
        agent_cost=float(best_cost),
        habit_pv_used_kwh=max(habit_used, 0.0),
        agent_pv_used_kwh=float(best_used),
        pv_generated_kwh=pv_kwh,
        deadlines_met=ok,
        solver=solver,
    )


def _auto_candidates(jobs: Sequence[Any], baseload_w: float, rep_days, limit_kw: Optional[float], n: int) -> list[float]:
    peak_kw = (baseload_w + sum(float(j.power_w) for j in jobs)) / 1000.0
    pv_peak = max(max(float(r.pv_per_kwp_w.max()) for r in rep_days) / 1000.0, 0.3)
    hi = max(1.0, peak_kw / pv_peak)
    if limit_kw is not None:
        hi = min(hi, limit_kw)
    step = hi / n
    return [round(step * i, 2) for i in range(1, n + 1)]


def _min_kwp(kwps: Sequence[float], savings: Sequence[float], target: float) -> Optional[float]:
    """kWp minimum (interpolasi linear antar kandidat) yang mencapai target penghematan."""
    for i, (k, s) in enumerate(zip(kwps, savings)):
        if s >= target - 1e-6:
            if i == 0:
                return float(k)
            k0, s0 = kwps[i - 1], savings[i - 1]
            if s - s0 <= 1e-9:
                return float(k)
            return float(k0 + (target - s0) / (s - s0) * (k - k0))
    return None


def _fmt_idr(v: float) -> str:
    return f"Rp{v:,.0f}".replace(",", ".")


def compare_sizing_with_agent(request: CompareRequest, time_budget_s: Optional[float] = None) -> CompareResult:
    from app.agent.planner import default_jobs

    t0 = time.perf_counter()
    budget = float(settings.sizing_compare_time_budget_s if time_budget_s is None else time_budget_s)
    jobs = list(request.jobs) or default_jobs()
    baseload = settings.default_baseload_w if request.baseload_w is None else float(request.baseload_w)
    lat, lon = resolve_location(request.location_lat, request.location_lon)
    year = request.reference_year or default_reference_year()
    opd = request.operating_days_per_week or settings.sizing_operating_days_per_week
    limit_kw = connected_kva(request.connected_power_va)
    battery_kwh = float(request.battery_kwh)

    rep_days = representative_days(year, lat, lon)
    if request.kwp_candidates:
        cands = sorted({round(float(k), 3) for k in request.kwp_candidates if k > 0})
    else:
        cands = _auto_candidates(jobs, baseload, rep_days, limit_kw, settings.sizing_compare_n_candidates)
    notes: list[str] = []
    if limit_kw is not None and any(k > limit_kw + 1e-9 for k in cands):
        cands = [k for k in cands if k <= limit_kw + 1e-9]
        notes.append(f"Kandidat di atas daya tersambung ({limit_kw:.1f} kVA) dibuang.")
    kwps = [0.0] + cands

    jobs_key = tuple(j.model_dump_json() for j in jobs)
    tariff_key = tuple(np.round(tariff_curve_idr_per_wh(), 9).tolist())
    use_ortools = request.solver == "ortools"
    ortools_dropped = False
    timed_out = False
    n_plans = 0
    solvers_used: set[str] = set()

    def evaluate(rep: RepresentativeDay, k: float, operating: bool) -> DayEval:
        nonlocal n_plans
        day_jobs = jobs if operating else []
        key = (jobs_key if operating else (), baseload, battery_kwh, round(lat, 4), round(lon, 4),
               rep.day, round(k, 3), use_ortools and operating, tariff_key)
        cached = _cache_get(key)
        if cached is not None:
            return cached
        ev = _evaluate_day(day_jobs, rep, k, baseload, battery_kwh, lat, lon, use_ortools and operating)
        n_plans += 1
        _cache_put(key, ev)
        return ev

    def point_at(k: float) -> ComparePoint:
        habit = habit_ni = agent = 0.0
        habit_used = agent_used = gen = 0.0
        ok = True
        for rep in rep_days:
            w_op = rep.weight_days * opd / 7.0
            w_closed = rep.weight_days - w_op
            ev = evaluate(rep, k, True)
            solvers_used.add(ev.solver)
            ok = ok and ev.deadlines_met
            habit += ev.habit_cost * w_op
            habit_ni += ev.habit_no_idle_cost * w_op
            agent += ev.agent_cost * w_op
            habit_used += ev.habit_pv_used_kwh * w_op
            agent_used += ev.agent_pv_used_kwh * w_op
            gen += ev.pv_generated_kwh * rep.weight_days
            if w_closed > 1e-9:
                ec = evaluate(rep, k, False)
                habit += ec.habit_cost * w_closed
                habit_ni += ec.habit_cost * w_closed
                agent += ec.habit_cost * w_closed
                habit_used += ec.habit_pv_used_kwh * w_closed
                agent_used += ec.habit_pv_used_kwh * w_closed
        return ComparePoint(
            kwp=round(k, 3),
            pv_capex_idr=round(k * settings.capex_per_kwp_idr, 0),
            habit_annual_bill_idr=round(habit, 0),
            habit_no_idle_annual_bill_idr=round(habit_ni, 0),
            agent_annual_bill_idr=round(agent, 0),
            habit_savings_idr_per_year=0.0,
            habit_no_idle_savings_idr_per_year=0.0,
            agent_savings_idr_per_year=0.0,
            habit_savings_pct=0.0,
            agent_savings_pct=0.0,
            habit_pv_used_kwh=round(habit_used, 1),
            agent_pv_used_kwh=round(agent_used, 1),
            pv_generated_kwh=round(gen, 1),
            deadlines_met=ok,
        )

    def over_budget(frac: float = 1.0) -> bool:
        return time.perf_counter() - t0 > budget * frac

    points: dict[float, ComparePoint] = {}
    for k in kwps:
        if use_ortools and over_budget(0.6):
            use_ortools = False
            ortools_dropped = True
        if points and over_budget():
            timed_out = True
            break
        points[round(k, 3)] = point_at(k)

    ref = points[0.0].habit_annual_bill_idr
    if ref <= 0:
        raise ValueError("Tagihan acuan nol; periksa daftar mesin dan beban dasar")
    if request.target_savings_pct is not None:
        target = ref * request.target_savings_pct / 100.0
    else:
        target = float(request.target_savings_idr_per_month) * 12.0

    series = {
        "habit": lambda p: ref - p.habit_annual_bill_idr,
        "habit_no_idle": lambda p: ref - p.habit_no_idle_annual_bill_idr,
        "agent": lambda p: ref - p.agent_annual_bill_idr,
    }

    # Perhalus kWp minimum tiap kurva dengan bisection di antara dua kandidat yang mengapit target.
    refined = 0
    for fn in series.values():
        for _ in range(REFINE_ITERS):
            ks_sorted = sorted(points)
            vals = [fn(points[k]) for k in ks_sorted]
            idx = next((i for i, v in enumerate(vals) if v >= target - 1e-6), None)
            if idx is None or idx == 0:
                break
            lo_k, hi_k = ks_sorted[idx - 1], ks_sorted[idx]
            if hi_k - lo_k < REFINE_MIN_STEP_KWP:
                break
            if use_ortools and over_budget(0.6):
                use_ortools = False
                ortools_dropped = True
            if over_budget(0.9):
                break
            mid = round(0.5 * (lo_k + hi_k), 3)
            points[mid] = point_at(mid)
            refined += 1

    ordered = [points[k] for k in sorted(points)]
    for p in ordered:
        p.habit_savings_idr_per_year = round(series["habit"](p), 0)
        p.habit_no_idle_savings_idr_per_year = round(series["habit_no_idle"](p), 0)
        p.agent_savings_idr_per_year = round(series["agent"](p), 0)
        p.habit_savings_pct = round(p.habit_savings_idr_per_year / ref * 100, 2)
        p.agent_savings_pct = round(p.agent_savings_idr_per_year / ref * 100, 2)

    ks = [p.kwp for p in ordered]
    k_habit = _min_kwp(ks, [p.habit_savings_idr_per_year for p in ordered], target)
    k_hni = _min_kwp(ks, [p.habit_no_idle_savings_idr_per_year for p in ordered], target)
    k_agent = _min_kwp(ks, [p.agent_savings_idr_per_year for p in ordered], target)

    red = red_pct = capex_red = None
    reduces = False
    if k_habit is not None and k_agent is not None:
        red = k_habit - k_agent
        red_pct = red / k_habit * 100.0 if k_habit > 0 else 0.0
        capex_red = red * settings.capex_per_kwp_idr
        reduces = red > 0.01

    target_m = target / 12.0
    if k_habit is not None and k_agent is not None and reduces:
        headline = (
            f"Untuk hemat {_fmt_idr(target_m)}/bulan, jadwal agen butuh PLTS {k_agent:.2f} kWp, kebiasaan lama "
            f"{k_habit:.2f} kWp — panel {red_pct:.0f}% lebih kecil (CAPEX ±{_fmt_idr(capex_red)} lebih hemat)."
        )
    elif k_agent is not None and k_habit is None:
        headline = (
            f"Target hemat {_fmt_idr(target_m)}/bulan tercapai dengan jadwal agen pada {k_agent:.2f} kWp, "
            f"sedangkan kebiasaan lama belum mencapainya sampai {ks[-1]:.2f} kWp."
        )
    elif k_agent is None:
        headline = (
            f"Target hemat {_fmt_idr(target_m)}/bulan belum tercapai sampai {ks[-1]:.2f} kWp, baik dengan "
            "kebiasaan lama maupun jadwal agen."
        )
    else:
        headline = (
            f"Jadwal agen tidak memperkecil panel: target hemat {_fmt_idr(target_m)}/bulan butuh ±{k_agent:.2f} kWp "
            f"pada kedua jadwal."
        )

    # ── catatan jujur ──────────────────────────────────────────────────────
    idle_save = ordered[0].agent_savings_idr_per_year
    if idle_save > 0:
        notes.append(
            f"Sebagian penghematan agen ({_fmt_idr(idle_save)}/tahun, juga tanpa PLTS) berasal dari mematikan mesin "
            "idle, bukan dari menggeser jam ke siang; kurva 'kebiasaan lama tanpa idle' memisahkan efek ini."
        )
        if k_hni is not None and k_agent is not None:
            notes.append(
                f"Dengan jam lama tetapi tanpa idle dibutuhkan {k_hni:.2f} kWp; selisih terhadap jadwal agen "
                f"({max(k_hni - k_agent, 0):.2f} kWp) adalah efek penggeseran jam saja."
            )
    if not reduces and k_agent is not None:
        notes.append(
            "Agen tidak memperkecil panel untuk kasus ini (mis. mesin sudah berjalan di siang hari atau jendela kerja "
            "sempit); manfaat agen bisa tetap ada pada tagihan harian."
        )
    if settings.tariff_scheme == "flat":
        notes.append(
            f"Tarif {settings.tariff_group} flat: tanpa PLTS menggeser jam tidak menghemat; manfaat geser jam hanya "
            "karena PV terpakai lebih banyak."
        )
    notes.append(
        f"Diasumsikan beroperasi {opd} hari/minggu; hari tutup hanya beban dasar. Tagihan = biaya energi saja "
        "(biaya beban/abonemen tidak dihitung)."
    )
    notes.append(
        "Jadwal agen di sini memakai penjadwal cepat (greedy" + (" + OR-Tools berbatas waktu" if request.solver == "ortools" else "")
        + "); agen penuh bisa sama atau lebih baik. Kurva PV dari tiruan digital yang belum divalidasi lapangan."
    )
    if len(kwps) > 1:
        notes.append(
            f"{len(kwps) - 1} kandidat kWp + {refined} titik perhalusan (bisection) di dekat target; kWp minimum "
            "diinterpolasi linear di antara dua titik terdekat."
        )
    if ortools_dropped:
        notes.append("Batas waktu hampir habis: OR-Tools dimatikan, sisa kandidat memakai greedy.")
    if timed_out:
        notes.append(f"Batas waktu {budget:.0f} detik tercapai; kandidat kWp di atas {ks[-1]:.2f} tidak dihitung.")
    if not all(p.deadlines_met for p in ordered):
        notes.append("PERINGATAN: sebagian jadwal agen tidak memenuhi semua batasan mesin.")

    return CompareResult(
        reference_annual_bill_idr=round(ref, 0),
        target_annual_savings_idr=round(target, 0),
        target_monthly_savings_idr=round(target_m, 0),
        target_savings_pct=round(target / ref * 100.0, 2),
        min_kwp_habit=None if k_habit is None else round(k_habit, 2),
        min_kwp_habit_no_idle=None if k_hni is None else round(k_hni, 2),
        min_kwp_agent=None if k_agent is None else round(k_agent, 2),
        kwp_reduction=None if red is None else round(red, 2),
        kwp_reduction_pct=None if red_pct is None else round(red_pct, 1),
        capex_reduction_idr=None if capex_red is None else round(capex_red, 0),
        agent_reduces_panel=reduces,
        headline=headline,
        curve=ordered,
        kwp_candidates=[round(k, 3) for k in kwps if round(k, 3) in points],
        max_kwp_limit=None if limit_kw is None else round(limit_kw, 2),
        battery_kwh=battery_kwh,
        operating_days_per_week=opd,
        solver="+".join(sorted(solvers_used)) or "none",
        reference_year=year,
        pv_source=summarize_source(rep_days),
        n_plans=n_plans,
        compute_time_s=round(time.perf_counter() - t0, 2),
        timed_out=timed_out,
        notes=notes,
    )

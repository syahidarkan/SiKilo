"""
Sizing PLTS atap WASKITA (tahap "Punya PLTS").

Kriteria (Permen ESDM No. 2/2024 — energi ekspor tidak dikreditkan):

1. Simulasi tahun pertama dengan 12 hari representatif berbobot jumlah hari
   sebenarnya (``app.sizing.annual``), lokasi dari request, tarif dari
   ``app.core.tariff``.
2. Manfaat = energi PV yang dipakai sendiri × tarif pada slot itu (surplus
   terbuang tidak bernilai).
3. Untuk tiap kandidat kWp (dan kapasitas baterai bila ``include_battery``)
   dihitung NPV dengan degradasi panel, OPEX, dan penggantian baterai
   (``app.sizing.finance``).
4. Rekomendasi = NPV maksimum dengan batasan self-consumption ≥ target dan
   kWp ≤ daya tersambung (bila diketahui). kWp terbesar yang masih memenuhi
   target self-consumption juga dilaporkan (``kwp_for_target_sc``).

Semua hasil adalah estimasi model yang belum divalidasi terhadap produksi PLTS
nyata di lokasi UMKM; lihat docs/SIZING.md.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Optional

import numpy as np

from app.core.config import settings
from app.core.tariff import average_tariff_idr_per_kwh, tariff_curve_idr_per_wh
from app.schemas.sizing import SizingCandidate, SizingRequest, SizingResult
from app.sizing.annual import (
    annual_no_battery,
    annual_with_battery,
    default_reference_year,
    month_load_matrix,
    representative_days,
    resolve_location,
    summarize_source,
)
from app.sizing.finance import FinanceResult, evaluate_finance
from app.sizing.regulatory import build_regulatory_checks, connected_kva

MAX_GRID_POINTS = 80
MAX_BATTERY_KWP_POINTS = 10
BATTERY_MAX_DAYS_PER_MONTH = 14
KWP_ABS_MAX = 1000.0


def _binary_search_kwp(
    self_consumption_at: Callable[[float], float],
    target_self_consumption: float,
    lo: float,
    hi: float,
    iterations: int = 30,
) -> float:
    """
    kWp TERBESAR di [lo, hi] dengan self-consumption ≥ target.

    Self-consumption tanpa baterai turun monoton seiring kWp naik
    (Σmin(k·p, L)/k tidak naik), jadi bila target tercapai di ``mid`` batas
    bawah dinaikkan. Satu simulasi per iterasi. Bila target sudah gagal di
    ``lo``, hasilnya ``lo`` (pemanggil menandai tidak layak); bila masih
    tercapai di ``hi``, hasilnya ``hi``.
    """
    if self_consumption_at(hi) >= target_self_consumption:
        return float(hi)
    if self_consumption_at(lo) < target_self_consumption:
        return float(lo)
    for _ in range(iterations):
        mid = 0.5 * (lo + hi)
        if self_consumption_at(mid) >= target_self_consumption:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-3:
            break
    return float(lo)


def _kwp_grid(hi: float, n_max: int = MAX_GRID_POINTS) -> np.ndarray:
    step = 25.0
    for s in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0):
        if hi / s <= n_max:
            step = s
            break
    grid = np.round(np.arange(step, hi + 1e-9, step), 4)
    if grid.size == 0 or grid[-1] < hi - 1e-6:
        grid = np.append(grid, round(hi, 4))
    return grid


def _search_upper_bound(loads: dict[int, np.ndarray], rep_days, load_kwh: float) -> float:
    """Batas atas pencarian: lewat titik di mana hampir semua tambahan PV terbuang."""
    peak_w = max(float(L.mean(axis=0).max()) for L in loads.values()) / 0.25
    pv_peak_kw = max(max(float(r.pv_per_kwp_w.max()) for r in rep_days) / 1000.0, 0.3)
    yields = [float(r.pv_per_kwp_wh.sum()) / 1000.0 for r in rep_days]
    min_yield = max(min(yields), 1.0)
    daily_kwh = load_kwh / 365.0
    hi = max(1.0, 1.5 * (peak_w / 1000.0) / pv_peak_kw, daily_kwh / min_yield)
    return float(min(hi, KWP_ABS_MAX))


def _fmt_idr(v: float) -> str:
    return f"Rp{v:,.0f}".replace(",", ".")


def _round_or_none(v: Optional[float], nd: int = 1) -> Optional[float]:
    if v is None or not math.isfinite(v):
        return None
    return round(v, nd)


def calculate_optimal_sizing(request: SizingRequest, solar: Any = None) -> SizingResult:
    lat, lon = resolve_location(request.location_lat, request.location_lon)
    year = request.reference_year or default_reference_year()
    target = float(request.target_self_consumption_pct)
    tariff = tariff_curve_idr_per_wh()

    rep_days = representative_days(year, lat, lon, solar=solar)
    pv_source = summarize_source(rep_days)
    loads = month_load_matrix((p.date, p.hourly_kwh) for p in request.load_profiles)

    base = annual_no_battery([0.0], rep_days, loads, tariff)
    load_kwh, bill_before = base.load_kwh, base.bill_before_idr
    if bill_before <= 0:
        raise ValueError("Tagihan dasar nol; periksa profil beban dan tarif")

    hi = _search_upper_bound(loads, rep_days, load_kwh)
    kva = connected_kva(request.connected_power_va)
    limit = kva
    grid_hi = hi if limit is None else min(hi, limit)
    grid = _kwp_grid(grid_hi)

    def sc_at(k: float) -> float:
        return float(annual_no_battery([k], rep_days, loads, tariff).self_consumption[0])

    # kWp terbesar yang masih memenuhi target self-consumption (tanpa baterai, tanpa batas daya).
    search_hi = hi
    while sc_at(search_hi) >= target and search_hi < KWP_ABS_MAX:
        search_hi = min(search_hi * 2.0, KWP_ABS_MAX)
    lo_k = min(0.01, float(grid[0]))
    kwp_target = _binary_search_kwp(sc_at, target, lo=lo_k, hi=search_hi)
    target_feasible = sc_at(lo_k) >= target

    # ── kandidat tanpa baterai (tervektorisasi) ───────────────────────────
    energy = annual_no_battery(grid, rep_days, loads, tariff)
    rows: list[dict[str, Any]] = []
    sc = energy.self_consumption
    for i, k in enumerate(grid):
        fin = evaluate_finance(float(energy.savings_idr[i]), float(energy.generation_kwh[i]), float(k), 0.0)
        rows.append(dict(
            kwp=float(k), battery_kwh=0.0, sc=float(sc[i]), gen=float(energy.generation_kwh[i]),
            used=float(energy.used_kwh[i]), curtail=float(energy.curtail_kwh[i]),
            savings=float(energy.savings_idr[i]), fin=fin,
        ))

    # ── kandidat dengan baterai ───────────────────────────────────────────
    battery_note: Optional[str] = None
    if request.include_battery:
        options = request.battery_options_kwh or list(settings.sizing_battery_options_kwh)
        options = sorted({round(float(b), 3) for b in options if b > 0})
        # Kandidat kWp untuk baterai: dari optimum tanpa baterai ke atas (baterai memungkinkan
        # panel lebih besar), ditambah beberapa titik di bawahnya.
        nb_feas = [i for i, r in enumerate(rows) if r["sc"] >= target - 1e-9]
        i_best = max(nb_feas, key=lambda i: rows[i]["fin"].npv_idr) if nb_feas else 0
        idx = np.unique(np.concatenate([
            np.linspace(i_best, len(grid) - 1, min(MAX_BATTERY_KWP_POINTS, len(grid) - i_best)),
            np.linspace(0, i_best, min(3, i_best + 1)),
        ]).round().astype(int))
        # Simulasi baterai (berurutan per hari) hanya memakai ≤ 14 hari terakhir tiap
        # bulan agar cepat. Supaya kandidat baterai & tanpa baterai dibandingkan pada
        # DATA YANG SAMA, manfaat baterai diukur sebagai selisih terhadap kandidat
        # tanpa baterai pada subset yang sama, lalu ditambahkan ke hasil tanpa
        # baterai pada data penuh:
        #   X_bat = X_nobat_penuh + (X_bat_subset − X_nobat_subset)
        # sehingga tagihan awal, beban, dan hemat konsisten (baterai sangat kecil
        # ≈ tanpa baterai, bukan "hemat" palsu dari perbedaan hari).
        bat_loads = {m: L[-BATTERY_MAX_DAYS_PER_MONTH:] for m, L in loads.items()}
        kidx = [int(i) for i in idx]
        nb_sub = annual_no_battery([float(grid[i]) for i in kidx], rep_days, bat_loads, tariff)
        for b in options:
            for j, i in enumerate(kidx):
                k = float(grid[i])
                e = annual_with_battery(k, b, rep_days, bat_loads, tariff)
                d_sav = float(e.savings_idr[0]) - float(nb_sub.savings_idr[j])
                d_used = float(e.used_kwh[0]) - float(nb_sub.used_kwh[j])
                gen = float(energy.generation_kwh[i])
                used = min(max(float(energy.used_kwh[i]) + d_used, 0.0), gen, load_kwh)
                sav = min(max(float(energy.savings_idr[i]) + d_sav, 0.0), bill_before)
                fin = evaluate_finance(sav, gen, k, b)
                rows.append(dict(
                    kwp=k, battery_kwh=b, sc=used / gen if gen > 0 else 1.0, gen=gen,
                    used=used, curtail=max(gen - used, 0.0),
                    savings=sav, fin=fin,
                ))
        battery_note = (
            "Baterai dicoba pada kapasitas " + ", ".join(f"{b:g}" for b in options) + " kWh "
            f"(C-rate {settings.battery_c_rate:g}, diganti tiap {settings.battery_lifetime_years} tahun)."
        )

    def feasible(r: dict[str, Any]) -> bool:
        return r["sc"] >= target - 1e-9 and (limit is None or r["kwp"] <= limit + 1e-9)

    feas = [r for r in rows if feasible(r)]
    if feas:
        best = max(feas, key=lambda r: r["fin"].npv_idr)
    else:
        # Target SC tidak tercapai bahkan pada kWp terkecil: pakai kWp terkecil tanpa baterai.
        best = rows[0]
    fin: FinanceResult = best["fin"]
    kwp = best["kwp"]
    viable = fin.npv_idr > 0

    checks = build_regulatory_checks(kwp, request.connected_power_va)
    savings = best["savings"]
    used = best["used"]
    bill_after = bill_before - savings
    simple_pbp = fin.simple_payback_years

    notes: list[str] = []
    n_days = len({p.date for p in request.load_profiles})
    months = sorted({p.date.month for p in request.load_profiles})
    if n_days < 28:
        notes.append(f"Data beban baru {n_days} hari; hasil bisa berubah setelah data ≥ 30 hari.")
    if len(months) < 12:
        notes.append(
            f"Data beban hanya mencakup {len(months)} bulan; bulan lain memakai pola beban yang sama "
            "(musim pesanan belum tercermin)."
        )
    if "clearsky" in pv_source:
        notes.append(
            "Produksi PV memakai model clear-sky × indeks kecerahan karena data cuaca NASA POWER tidak tersedia."
        )
    notes.append(
        "Produksi PV dari tiruan digital yang belum divalidasi terhadap PLTS nyata di lokasi; "
        "survei penyedia PLTS tetap diperlukan."
    )
    if not target_feasible:
        notes.append(
            f"Target self-consumption {target:.0%} tidak tercapai bahkan pada kWp terkecil: beban siang hari terlalu "
            "kecil. Rekomendasi memakai kWp terkecil yang dicoba."
        )
    if limit is not None and kwp >= limit - 1e-6:
        notes.append(f"Ukuran dibatasi daya tersambung ({limit:.1f} kVA).")
    if not viable:
        notes.append(
            "NPV tidak positif pada asumsi biaya & tarif saat ini: PLTS belum layak finansial untuk pola beban ini."
        )
    if battery_note:
        notes.append(battery_note)
        if best["battery_kwh"] <= 0:
            notes.append("Baterai tidak menambah NPV pada harga baterai saat ini; rekomendasi tanpa baterai.")
    if settings.tariff_scheme == "flat":
        notes.append(
            f"Tarif {settings.tariff_group} flat {_fmt_idr(settings.tariff_flat_idr_per_kwh)}/kWh, tanpa kenaikan tarif "
            "(perhitungan harga riil)."
        )

    bat_txt = f" + baterai {best['battery_kwh']:g} kWh" if best["battery_kwh"] > 0 else ""
    pbp_txt = f"balik modal ±{simple_pbp:.1f} tahun" if simple_pbp is not None else "tidak balik modal dalam umur panel"
    rec_note = (
        f"Rekomendasi {kwp:.2f} kWp{bat_txt}: {best['sc'] * 100:.1f}% produksi PV terpakai sendiri, "
        f"hemat ±{_fmt_idr(savings / 12)}/bulan, {pbp_txt}, NPV {_fmt_idr(fin.npv_idr)}. "
        f"Ukuran maksimum untuk target self-consumption {target:.0%}: {kwp_target:.2f} kWp. "
        "Estimasi model, belum divalidasi; kepatuhan regulasi final ditentukan PLN."
    )

    candidates = [
        SizingCandidate(
            kwp=round(r["kwp"], 3),
            battery_kwh=r["battery_kwh"],
            self_consumption_rate_pct=round(r["sc"] * 100, 1),
            annual_generation_kwh=round(r["gen"], 1),
            annual_self_consumption_kwh=round(r["used"], 1),
            annual_savings_idr=round(r["savings"], 0),
            capex_idr=round(r["fin"].capex_idr, 0),
            npv_idr=round(r["fin"].npv_idr, 0),
            feasible=feasible(r),
        )
        for r in rows
    ]

    return SizingResult(
        recommended_kwp=round(kwp, 2),
        recommended_battery_kwh=best["battery_kwh"],
        kwp_for_target_sc=round(kwp_target, 2),
        target_self_consumption_pct=round(target * 100, 1),
        target_sc_feasible=target_feasible,
        max_kwp_limit=None if limit is None else round(limit, 2),
        annual_generation_kwh=round(best["gen"], 1),
        annual_self_consumption_kwh=round(used, 1),
        annual_curtailment_kwh=round(best["curtail"], 1),
        self_consumption_rate_pct=round(best["sc"] * 100, 1),
        annual_load_kwh=round(load_kwh, 1),
        solar_fraction_pct=round(min(used / load_kwh, 1.0) * 100, 1) if load_kwh > 0 else 0.0,
        annual_bill_before_idr=round(bill_before, 0),
        annual_bill_after_idr=round(bill_after, 0),
        pv_capex_idr=round(fin.pv_capex_idr, 0),
        battery_capex_idr=round(fin.battery_capex_idr, 0),
        capex_idr=round(fin.capex_idr, 0),
        annual_opex_idr=round(fin.annual_opex_idr, 0),
        annual_savings_idr=round(savings, 0),
        lcoe_idr_per_kwh=round(fin.lcoe_idr_per_kwh, 1) if math.isfinite(fin.lcoe_idr_per_kwh) else 0.0,
        npv_idr=round(fin.npv_idr, 0),
        payback_period_years=round(min(simple_pbp, 99.9), 1) if simple_pbp is not None else 99.9,
        discounted_payback_years=_round_or_none(fin.discounted_payback_years),
        financially_viable=viable,
        co2_avoided_kg_per_year=round(used * settings.grid_emission_kg_per_kwh, 1),
        permen_esdm_compliant=bool(checks.kwp_within_connected_power),
        regulatory_checks=checks,
        reference_year=year,
        pv_source=pv_source,
        tariff_group=settings.tariff_group,
        tariff_scheme=settings.tariff_scheme,
        candidates=candidates,
        assumptions={
            "capex_per_kwp_idr": settings.capex_per_kwp_idr,
            "battery_capex_per_kwh_idr": settings.battery_capex_per_kwh_idr,
            "opex_pct_of_capex": settings.opex_pct_of_capex,
            "discount_rate": settings.discount_rate,
            "panel_lifetime_years": settings.panel_lifetime_years,
            "panel_degradation_per_year": settings.panel_degradation_per_year,
            "battery_lifetime_years": settings.battery_lifetime_years,
            "average_tariff_idr_per_kwh": round(average_tariff_idr_per_kwh(), 2),
            "grid_emission_kg_per_kwh": settings.grid_emission_kg_per_kwh,
            "location_lat": lat,
            "location_lon": lon,
            "representative_days": [r.day.isoformat() for r in rep_days],
            "export_credited": False,
        },
        notes=notes,
        recommendation_note=rec_note,
    )

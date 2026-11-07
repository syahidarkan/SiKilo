"""
Penyusun rapor kelayakan dari data UMKM di basis data (EnergyLedger + MachineProfile).

Alur ``build_scorecard_for_umkm``:
1. Ambil profil kWh per jam 30 hari terakhir (hari lengkap ≥ 20 jam) dari
   ``EnergyLedger``. Bila < ``settings.sizing_min_data_days`` hari →
   ``InsufficientData`` (rapor TIDAK dikarang dari data kosong).
2. Profil pemakaian per mesin = total kWh & Rp per label di periode yang sama.
3. Sizing pola pakai saat ini: ``calculate_optimal_sizing`` (kontrak §5).
4. kWp setelah jadwal agen: ``compare_sizing_with_agent`` (kontrak §5) dengan
   profil mesin UMKM, beban dasar TERUKUR (median label "Baseload /
   Background" di ledger; default config bila data kurang) dan target hemat
   (persen) yang sama dengan hasil sizing. Beban perbandingan ini tetap model
   (profil mesin), bukan beban terukur; rapor mencatat selisih tagihan acuan
   model vs tagihan terukur dan bagian ini TIDAK ikut skor.
   Bila modul/profil mesin belum ada, bagian ini dikosongkan beserta catatan.
5. ``generate_bankability_scorecard`` → dict (siap JSON/PDF).

Fungsi hitung berat (``compute_habit_sizing``, ``compute_agent_compare``)
dijalankan di thread dan boleh di-monkeypatch di tes.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import UMKM

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
SIZING_TIMEOUT_S = 120.0
COMPARE_TIMEOUT_S = 120.0


class InsufficientData(Exception):
    def __init__(self, n_days: int, min_days: int):
        super().__init__(f"Butuh minimal {min_days} hari data lengkap; baru ada {n_days} hari.")
        self.n_days = n_days
        self.min_days = min_days


def _find(name: str, modules: tuple[str, ...]) -> Optional[Callable[..., Any]]:
    for mod in modules:
        try:
            m = importlib.import_module(mod)
        except ImportError:
            continue
        fn = getattr(m, name, None)
        if callable(fn):
            return fn
    return None


def compute_habit_sizing(profiles: list[tuple[date, list[float]]], connected_power_va: Optional[float]) -> Any:
    """Sizing PLTS dari profil terukur (pola pakai saat ini)."""
    from app.schemas.sizing import DailyLoadProfile, SizingRequest

    fn = _find("calculate_optimal_sizing", ("app.sizing", "app.sizing.calculator"))
    if fn is None:
        raise RuntimeError("Modul sizing (calculate_optimal_sizing) tidak tersedia")
    kwargs: dict[str, Any] = {
        "load_profiles": [DailyLoadProfile(date=d, hourly_kwh=p) for d, p in profiles],
        "location_lat": settings.site_latitude,
        "location_lon": settings.site_longitude,
    }
    if connected_power_va and "connected_power_va" in SizingRequest.model_fields:
        kwargs["connected_power_va"] = float(connected_power_va)
    return fn(SizingRequest(**kwargs))


def compute_agent_compare(jobs: list[Any], target_savings_pct: float, umkm_info: dict[str, Any]) -> Any:
    """kWp minimum kebiasaan lama vs jadwal agen untuk target hemat (persen) yang sama."""
    fn = _find("compare_sizing_with_agent", ("app.sizing", "app.sizing.compare", "app.sizing.calculator"))
    if fn is None:
        raise RuntimeError("Modul pembanding sizing (compare_sizing_with_agent) belum tersedia")
    from app.schemas.sizing import CompareRequest

    kwargs: dict[str, Any] = {
        "jobs": jobs,
        "target_savings_pct": float(target_savings_pct),
        "location_lat": settings.site_latitude,
        "location_lon": settings.site_longitude,
        "battery_kwh": float(umkm_info.get("battery_kwh") or 0.0),
        "solver": "greedy",
    }
    if umkm_info.get("baseload_w") is not None:
        kwargs["baseload_w"] = float(umkm_info["baseload_w"])
    if umkm_info.get("connected_power_va"):
        kwargs["connected_power_va"] = float(umkm_info["connected_power_va"])
    fields = getattr(CompareRequest, "model_fields", {})
    return fn(CompareRequest(**{k: v for k, v in kwargs.items() if not fields or k in fields}))


async def machine_usage(db: AsyncSession, umkm_id: int, start: date, end: date) -> list[dict[str, Any]]:
    from app.services_data.ledger import top_appliances

    rows = await top_appliances(db, umkm_id, start, end, limit=100)
    return [{"label": r["appliance_label"], "kwh": r["kwh"], "cost_idr": r["cost_idr"]} for r in rows]


def _target_pct(sizing: Any) -> Optional[float]:
    savings = float(getattr(sizing, "annual_savings_idr", 0.0) or 0.0)
    bill = float(getattr(sizing, "annual_bill_before_idr", 0.0) or 0.0)
    if savings <= 0 or bill <= 0:
        return None
    pct = savings / bill * 100.0
    return round(pct, 2) if 0.5 <= pct < 99.0 else None


async def build_scorecard_for_umkm(
    db: AsyncSession,
    umkm: UMKM,
    today: Optional[date] = None,
    *,
    include_agent_compare: bool = True,
) -> dict[str, Any]:
    from app.core.tariff import tariff_idr_per_kwh
    from app.services.jobs import load_machine_profiles, local_today, measured_baseload_w, profiles_to_jobs
    from app.services.scorecard_generator import generate_bankability_scorecard
    from app.services_data.ledger import hourly_profiles

    today = today or local_today()
    start, end = today - timedelta(days=WINDOW_DAYS), today - timedelta(days=1)
    profiles = await hourly_profiles(db, umkm.id, start, end)
    n_days = len(profiles)
    if n_days < settings.sizing_min_data_days:
        raise InsufficientData(n_days, settings.sizing_min_data_days)

    daily_cost = sum(kwh * tariff_idr_per_kwh(h) for _, p in profiles for h, kwh in enumerate(p)) / n_days
    usage = await machine_usage(db, umkm.id, profiles[0][0], profiles[-1][0])
    notes: list[str] = []

    sizing = await asyncio.wait_for(
        asyncio.to_thread(compute_habit_sizing, profiles, umkm.connected_power_va), timeout=SIZING_TIMEOUT_S
    )

    compare = None
    compare_basis: Optional[str] = None
    if include_agent_compare:
        mprofiles = await load_machine_profiles(db, umkm.id)
        jobs, job_notes = profiles_to_jobs(mprofiles)
        notes.extend(job_notes)
        target = _target_pct(sizing)
        if not jobs:
            notes.append("Profil mesin belum diisi; kWp setelah jadwal agen tidak dihitung.")
        elif target is None:
            notes.append("Sizing tidak menghasilkan penghematan positif; perbandingan dengan jadwal agen dilewati.")
        else:
            baseload = await measured_baseload_w(db, umkm.id, end=profiles[-1][0])
            info = {
                "battery_kwh": umkm.battery_kwh,
                "connected_power_va": umkm.connected_power_va,
                "baseload_w": baseload,
            }
            if baseload is None:
                compare_basis = (
                    f"profil mesin UMKM + beban dasar asumsi {settings.default_baseload_w:.0f} W "
                    "(data beban dasar terukur belum cukup); simulasi, bukan beban terukur"
                )
            else:
                compare_basis = (
                    f"profil mesin UMKM + beban dasar terukur {baseload:.0f} W (median ledger); "
                    "simulasi jadwal, bukan beban terukur"
                )
            try:
                compare = await asyncio.wait_for(
                    asyncio.to_thread(compute_agent_compare, jobs, target, info), timeout=COMPARE_TIMEOUT_S
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Perbandingan kWp agen UMKM %s gagal: %s", umkm.id, exc)
                notes.append(f"Perbandingan kWp dengan jadwal agen gagal dihitung ({type(exc).__name__}).")
            if compare is not None:
                ref = float(getattr(compare, "reference_annual_bill_idr", 0.0) or 0.0)
                measured_annual = daily_cost * 365.0
                if ref > 0 and measured_annual > 0:
                    dev = (ref - measured_annual) / measured_annual * 100.0
                    notes.append(
                        f"Tagihan acuan model perbandingan agen Rp{ref:,.0f}/tahun vs tagihan terukur "
                        f"Rp{measured_annual:,.0f}/tahun (selisih {dev:+.0f}%).".replace(",", ".")
                        + (" Selisih besar: periksa profil mesin (daya, runtime, idle)." if abs(dev) > 25 else "")
                    )

    return generate_bankability_scorecard(
        umkm_name=umkm.name,
        umkm_address=umkm.address,
        umkm_type=umkm.umkm_type,
        sizing=sizing,
        avg_monthly_pln_bill_idr=daily_cost * 30.0,
        audit_period_days=n_days,
        prepared_date=today,
        agent_compare=compare,
        machine_usage=usage,
        audit_period_start=profiles[0][0],
        audit_period_end=profiles[-1][0],
        load_data_source="terukur",
        pv_data_source=str(getattr(sizing, "pv_source", "") or "") or None,
        bill_source="terukur",
        verified=True,
        agent_compare_basis=compare_basis,
        umkm_id=umkm.id,
        kecamatan=umkm.kecamatan,
        extra_notes=[
            f"Biaya listrik/bulan dihitung dari {n_days} hari data perangkat × tarif "
            f"{settings.tariff_group}, bukan dari tagihan resmi PLN.",
            *notes,
        ],
    )


__all__ = ["InsufficientData", "build_scorecard_for_umkm", "compute_agent_compare", "compute_habit_sizing"]

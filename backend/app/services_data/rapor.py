"""
Ringkasan rapor kelayakan PLTS per UMKM dari data ledger lapangan.

- Butuh ≥ ``settings.sizing_min_data_days`` hari lengkap (≥ 20 jam tercatat)
  dalam 30 hari terakhir; bila kurang → status ``belum_ada_data``.
- Ukuran PLTS dihitung lewat kontrak ``app.sizing.calculate_optimal_sizing``
  dan skor lewat ``app.services.scorecard_generator.generate_bankability_scorecard``.
  Bila modul itu gagal, status ``gagal`` beserta alasannya (tidak dikarang).
- Hasil di-cache per UMKM selama data ledger tidak berubah.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import UMKM
from app.services_data.ledger import hourly_profiles

logger = logging.getLogger(__name__)

WINDOW_DAYS = 30
COMPUTE_TIMEOUT_S = 90.0
VALIDATION_NOTE = (
    "Perkiraan otomatis dari data perangkat WASKITA; belum divalidasi auditor energi. "
    "Survei lokasi oleh penyedia PLTS tetap diperlukan."
)

_cache: dict[int, tuple[tuple, dict[str, Any]]] = {}


def clear_cache() -> None:
    _cache.clear()


def compute_sizing(
    profiles: list[tuple[date, list[float]]], umkm: dict[str, Any], monthly_cost_idr: float
) -> dict[str, Any]:
    """Hitung kWp, PBP, dan skor (sinkron; dijalankan di thread). Dapat di-monkeypatch di tes."""
    from app.schemas.sizing import DailyLoadProfile, SizingRequest
    from app.sizing.calculator import calculate_optimal_sizing

    req = SizingRequest(
        load_profiles=[DailyLoadProfile(date=d, hourly_kwh=p) for d, p in profiles],
        location_lat=settings.site_latitude,
        location_lon=settings.site_longitude,
    )
    sizing = calculate_optimal_sizing(req)
    out: dict[str, Any] = {
        "recommended_kwp": float(getattr(sizing, "recommended_kwp", 0.0) or 0.0),
        "payback_years": _maybe_float(getattr(sizing, "payback_period_years", None)),
        "annual_savings_idr": _maybe_float(getattr(sizing, "annual_savings_idr", None)),
        "capex_idr": _maybe_float(getattr(sizing, "capex_idr", None)),
        "score": None,
        "risk_category": None,
    }
    try:
        from app.services.scorecard_generator import generate_bankability_scorecard

        card = generate_bankability_scorecard(
            umkm_name=umkm["name"],
            umkm_address=umkm["address"],
            umkm_type=umkm["umkm_type"],
            sizing=sizing,
            avg_monthly_pln_bill_idr=monthly_cost_idr,
            audit_period_days=len(profiles),
        )
        score = (card or {}).get("bankability_score", {})
        out["score"] = _maybe_float(score.get("total_score"))
        out["risk_category"] = score.get("risk_category")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Skor rapor tidak dapat dihitung: %s", exc)
    return out


def _maybe_float(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


async def rapor_summary(db: AsyncSession, umkm: UMKM, today: Optional[date] = None) -> dict[str, Any]:
    from app.core.tariff import tariff_idr_per_kwh
    from app.schemas.telemetry import local_tz

    if today is None:
        from datetime import datetime

        today = datetime.now(local_tz()).date()
    start, end = today - timedelta(days=WINDOW_DAYS), today - timedelta(days=1)
    profiles = await hourly_profiles(db, umkm.id, start, end)
    n_days = len(profiles)
    base: dict[str, Any] = {
        "status": "belum_ada_data",
        "data_days": n_days,
        "min_data_days": settings.sizing_min_data_days,
        "monthly_kwh": None,
        "monthly_cost_idr": None,
        "recommended_kwp": None,
        "payback_years": None,
        "score": None,
        "risk_category": None,
        "annual_savings_idr": None,
        "note": "",
        "validation": VALIDATION_NOTE,
    }
    if n_days:
        daily_kwh = sum(sum(p) for _, p in profiles) / n_days
        daily_cost = sum(kwh * tariff_idr_per_kwh(h) for _, p in profiles for h, kwh in enumerate(p)) / n_days
        base["monthly_kwh"] = round(daily_kwh * 30, 2)
        base["monthly_cost_idr"] = round(daily_cost * 30, 0)
    if n_days < settings.sizing_min_data_days:
        base["note"] = (
            f"Butuh minimal {settings.sizing_min_data_days} hari data lengkap; baru ada {n_days} hari."
        )
        return base

    key = (n_days, profiles[0][0], profiles[-1][0], round(sum(sum(p) for _, p in profiles), 3))
    cached = _cache.get(umkm.id)
    if cached is not None and cached[0] == key:
        return dict(cached[1])

    umkm_info = {"name": umkm.name, "address": umkm.address, "umkm_type": umkm.umkm_type}
    try:
        computed = await asyncio.wait_for(
            asyncio.to_thread(compute_sizing, profiles, umkm_info, base["monthly_cost_idr"] or 0.0),
            timeout=COMPUTE_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sizing UMKM %s gagal: %s", umkm.id, exc)
        base.update(status="gagal", note=f"Perhitungan ukuran PLTS gagal: {type(exc).__name__}")
        return base

    base.update({k: v for k, v in computed.items() if k in base})
    if base["payback_years"] is not None:
        base["payback_years"] = round(base["payback_years"], 1)
    if base["recommended_kwp"] is not None:
        base["recommended_kwp"] = round(base["recommended_kwp"], 2)
    base["status"] = "ok"
    base["note"] = f"Dihitung dari {n_days} hari data lapangan ({profiles[0][0]} s/d {profiles[-1][0]})."
    _cache[umkm.id] = (key, dict(base))
    return base

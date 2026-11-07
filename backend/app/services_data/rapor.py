"""
Ringkasan rapor kelayakan PLTS per UMKM dari data ledger lapangan.

- Butuh ≥ ``settings.sizing_min_data_days`` hari lengkap (≥ 20 jam tercatat)
  dalam 30 hari terakhir; bila kurang → status ``belum_ada_data``.
- Ukuran PLTS dihitung lewat kontrak ``app.sizing.calculate_optimal_sizing``
  dan skor lewat ``app.services.scorecard_generator.generate_bankability_scorecard``.
  Bila modul itu gagal, status ``gagal`` beserta alasannya (tidak dikarang).
- Hasil di-cache per UMKM selama data ledger tidak berubah. Perhitungan
  memakai executor khusus (``settings.rapor_max_workers`` thread) dan
  single-flight per UMKM: bila batas waktu habis, perhitungan tetap selesai di
  latar belakang dan permintaan berikutnya memakai hasilnya (tidak memulai
  salinan baru).
"""
from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
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

# Hasil compute_sizing per UMKM (kunci = ringkasan data) & perhitungan yang sedang berjalan.
_computed: dict[int, tuple[tuple, dict[str, Any]]] = {}
_inflight: dict[int, tuple[tuple, asyncio.Future]] = {}
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, int(settings.rapor_max_workers)), thread_name_prefix="rapor"
            )
        return _executor


def clear_cache() -> None:
    _computed.clear()
    _inflight.clear()


def forget(umkm_id: int) -> None:
    """Hapus cache rapor satu UMKM (mis. setelah persetujuan berbagi data dicabut)."""
    _computed.pop(umkm_id, None)
    _inflight.pop(umkm_id, None)


def is_cached(umkm_id: int) -> bool:
    return umkm_id in _computed


def compute_sizing(
    profiles: list[tuple[date, list[float]]], umkm: dict[str, Any], monthly_cost_idr: float
) -> dict[str, Any]:
    """Hitung kWp, PBP, dan skor (sinkron; dijalankan di thread). Dapat di-monkeypatch di tes."""
    from app.schemas.sizing import DailyLoadProfile, SizingRequest
    from app.sizing.calculator import calculate_optimal_sizing

    kwargs: dict[str, Any] = {
        "load_profiles": [DailyLoadProfile(date=d, hourly_kwh=p) for d, p in profiles],
        "location_lat": settings.site_latitude,
        "location_lon": settings.site_longitude,
    }
    # Sama dengan jalur scorecard: batasi kWp oleh daya tersambung PLN bila diketahui.
    if umkm.get("connected_power_va"):
        kwargs["connected_power_va"] = float(umkm["connected_power_va"])
    req = SizingRequest(**kwargs)
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


async def rapor_summary(
    db: AsyncSession, umkm: UMKM, today: Optional[date] = None, *, wait: bool = True
) -> dict[str, Any]:
    """
    Ringkasan rapor. ``wait=False``: bila belum ada di cache, perhitungan
    dimulai di latar belakang dan status ``diproses`` dikembalikan segera.
    """
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

    key = (
        n_days,
        profiles[0][0],
        profiles[-1][0],
        round(sum(sum(p) for _, p in profiles), 3),
        umkm.connected_power_va,
    )
    cached = _computed.get(umkm.id)
    if cached is not None and cached[0] == key:
        return _finish(base, dict(cached[1]), n_days, profiles)

    umkm_info = {
        "name": umkm.name,
        "address": umkm.address,
        "umkm_type": umkm.umkm_type,
        "connected_power_va": umkm.connected_power_va,
    }
    fut = _start_compute(umkm.id, key, profiles, umkm_info, base["monthly_cost_idr"] or 0.0)
    if not wait and not fut.done():
        base.update(status="diproses", note="Rapor sedang dihitung di latar belakang; muat ulang sebentar lagi.")
        return base
    try:
        # shield: bila batas waktu habis, perhitungan TETAP berjalan (satu saja per UMKM)
        # dan hasilnya masuk cache untuk permintaan berikutnya.
        computed = await asyncio.wait_for(asyncio.shield(fut), timeout=COMPUTE_TIMEOUT_S)
    except asyncio.TimeoutError:
        base.update(status="diproses", note="Perhitungan rapor masih berjalan; coba lagi beberapa saat lagi.")
        return base
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sizing UMKM %s gagal: %s", umkm.id, exc)
        base.update(status="gagal", note=f"Perhitungan ukuran PLTS gagal: {type(exc).__name__}")
        return base
    return _finish(base, computed, n_days, profiles)


def _finish(base: dict[str, Any], computed: dict[str, Any], n_days: int, profiles) -> dict[str, Any]:
    base.update({k: v for k, v in computed.items() if k in base})
    if base["payback_years"] is not None:
        base["payback_years"] = round(base["payback_years"], 1)
    if base["recommended_kwp"] is not None:
        base["recommended_kwp"] = round(base["recommended_kwp"], 2)
    base["status"] = "ok"
    base["note"] = f"Dihitung dari {n_days} hari data lapangan ({profiles[0][0]} s/d {profiles[-1][0]})."
    return base


def _start_compute(umkm_id: int, key: tuple, profiles, umkm_info: dict[str, Any], monthly_cost: float) -> asyncio.Future:
    """
    Single-flight per (UMKM, kunci data): perhitungan yang sama tidak pernah
    berjalan ganda, dan memakai executor khusus berukuran kecil sehingga
    permintaan beruntun tidak menumpuk thread.
    """
    loop = asyncio.get_running_loop()
    running = _inflight.get(umkm_id)
    if running is not None:
        r_key, r_fut = running
        if r_key == key and not r_fut.done() and getattr(r_fut, "_loop", loop) is loop:
            return r_fut
    fut = loop.run_in_executor(_get_executor(), lambda: compute_sizing(profiles, umkm_info, monthly_cost))
    _inflight[umkm_id] = (key, fut)

    def _done(f: asyncio.Future) -> None:
        cur = _inflight.get(umkm_id)
        if cur is not None and cur[1] is f:
            _inflight.pop(umkm_id, None)
        if f.cancelled() or f.exception() is not None:
            return
        _computed[umkm_id] = (key, dict(f.result()))

    fut.add_done_callback(_done)
    return fut

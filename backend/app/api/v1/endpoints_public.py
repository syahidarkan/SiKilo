"""
Endpoint publik (tanpa login) untuk simulator di landing page WASKITA.

``POST /api/v1/public/estimate`` menerima profil usaha sederhana (daya PLN
tersambung + jenis mesin fleksibel dari katalog tetap) lalu menjalankan
mesin perhitungan yang sama dengan ``/sizing/compare``: cuaca NASA POWER,
tarif PLN dari ``app.core.tariff``, dan perbandingan ukuran PLTS dengan
jadwal kebiasaan lama vs jadwal agen.

Karena tanpa autentikasi:
- input dibatasi ke katalog mesin & rentang daya yang tetap (tidak ada
  angka bebas yang bisa membuat komputasi berat),
- hasil di-cache per kombinasi input,
- ada pembatas laju sederhana per alamat IP.
Semua angka adalah ESTIMASI dari profil mesin tipikal, bukan hasil ukur.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import OrderedDict, deque
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.tariff import tariff_idr_per_kwh
from app.schemas.dispatch import MachineJob
from app.schemas.sizing import CompareRequest
from app.sizing.compare import compare_sizing_with_agent

router = APIRouter(prefix="/public", tags=["Publik (landing page)"])

MachineKey = Literal["setrika_uap", "kompresor_angin", "oven_pemanas", "mesin_cuci_dryer"]

# Profil mesin tipikal UMKM (ASUMSI, bukan hasil ukur). Kebiasaan lama:
# mesin dinyalakan pagi lalu dibiarkan menyala tanpa beban sebagian waktu.
MACHINE_CATALOG: dict[str, dict] = {
    "setrika_uap": {
        "label": "Setrika Uap", "appliance_class": 3, "power_w": 1500.0,
        "daily_runtime_minutes": 300, "habit_start_hour": 8,
        "min_continuous_minutes": 60, "idle_minutes_habit": 60,
    },
    "kompresor_angin": {
        "label": "Kompresor Angin", "appliance_class": 2, "power_w": 1100.0,
        "daily_runtime_minutes": 180, "habit_start_hour": 8,
        "min_continuous_minutes": 30, "idle_minutes_habit": 45,
    },
    "oven_pemanas": {
        "label": "Oven Pemanas", "appliance_class": 3, "power_w": 2000.0,
        "daily_runtime_minutes": 120, "habit_start_hour": 9,
        "min_continuous_minutes": 60, "idle_minutes_habit": 30,
    },
    "mesin_cuci_dryer": {
        "label": "Mesin Cuci & Dryer", "appliance_class": 4, "power_w": 1200.0,
        "daily_runtime_minutes": 240, "habit_start_hour": 8,
        "min_continuous_minutes": 45, "idle_minutes_habit": 30,
    },
}

ALLOWED_VA = (900, 1300, 2200, 3500, 4400, 5500, 6600, 7700, 11000, 13200, 16500, 23000)
TARGET_SAVINGS_PCT = 30.0
_CACHE_MAX = 256
_RATE_LIMIT = 12          # permintaan
_RATE_WINDOW_S = 60.0     # per jendela waktu per IP
_TIME_BUDGET_S = 20.0


class EstimateRequest(BaseModel):
    connected_power_va: int = Field(..., description=f"Salah satu dari {ALLOWED_VA}")
    machines: List[MachineKey] = Field(default_factory=list, max_length=4)

    @field_validator("connected_power_va")
    @classmethod
    def _snap_va(cls, v: int) -> int:
        if v <= 0 or v > 200_000:
            raise ValueError("Daya tersambung harus 1–200.000 VA")
        return min(ALLOWED_VA, key=lambda a: abs(a - v))

    @field_validator("machines")
    @classmethod
    def _unique(cls, v: List[str]) -> List[str]:
        return sorted(set(v))


class EstimatePoint(BaseModel):
    kwp: float
    habit_savings_idr_per_month: float
    agent_savings_idr_per_month: float


class EstimateResponse(BaseModel):
    connected_power_va: int
    machines: List[str]
    recommended_kwp: Optional[float] = Field(None, description="kWp yang disarankan dengan jadwal agen")
    kwp_without_agent: Optional[float] = Field(None, description="kWp untuk hemat yang sama tanpa jadwal agen")
    kwp_reduction_pct: Optional[float] = None
    monthly_bill_now_idr: float
    monthly_savings_idr: float
    savings_pct: float
    capex_idr: float
    payback_years: Optional[float]
    target_savings_pct: float
    target_reached: bool
    tariff_idr_per_kwh: float
    tariff_group: str
    pv_source: str
    headline: str
    curve: List[EstimatePoint]
    assumptions: List[str]
    compute_time_s: float


_cache: "OrderedDict[tuple, EstimateResponse]" = OrderedDict()
_cache_lock = threading.Lock()
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _hits_lock:
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > _RATE_WINDOW_S:
            q.popleft()
        if len(q) >= _RATE_LIMIT:
            return True
        q.append(now)
        if len(_hits) > 10_000:  # cegah kebocoran memori
            for k in list(_hits)[:5_000]:
                _hits.pop(k, None)
        return False


def _build_jobs(va: int, machines: List[str]) -> tuple[list[MachineJob], float]:
    """Mesin fleksibel dari katalog + beban usaha umum (tidak fleksibel) sesuai daya."""
    # Beban dasar 24 jam (lampu, freezer, router) & beban usaha jam kerja, keduanya
    # proporsional terhadap daya tersambung dan dibatasi wajar.
    baseload_w = float(min(max(0.06 * va, 150.0), 2500.0))
    general_w = float(min(max(0.15 * va, 200.0), 5000.0))
    budget_w = 0.85 * va - baseload_w - general_w
    jobs = [
        MachineJob(
            machine_id="beban-usaha-umum", appliance_class=0, label="Peralatan usaha umum",
            power_w=general_w, daily_runtime_minutes=480, habit_start_hour=8,
            earliest_hour=7, deadline_hour=17, is_flexible=False,
        )
    ]
    chosen = [MACHINE_CATALOG[m] for m in machines]
    total = sum(c["power_w"] for c in chosen)
    scale = 1.0 if total <= 0 or total <= budget_w else max(budget_w, 0.0) / total
    for key, spec in zip(machines, chosen):
        power = spec["power_w"] * scale
        if power < 100.0:
            continue  # daya terlalu kecil untuk VA ini — mesin tidak realistis dimodelkan
        jobs.append(MachineJob(
            machine_id=key, earliest_hour=7, deadline_hour=17,
            **{**spec, "power_w": round(power, 1)},
        ))
    return jobs, baseload_w


def _estimate(req: EstimateRequest) -> EstimateResponse:
    jobs, baseload_w = _build_jobs(req.connected_power_va, req.machines)
    # Siapkan cuaca setahun dulu (lambat saat cache dingin) agar tidak memakan
    # jatah waktu perbandingan kWp.
    _warm_up()
    result = compare_sizing_with_agent(
        CompareRequest(
            jobs=jobs, baseload_w=baseload_w, connected_power_va=req.connected_power_va,
            target_savings_pct=TARGET_SAVINGS_PCT, solver="greedy",
        ),
        time_budget_s=_TIME_BUDGET_S,
    )
    ref_month = result.reference_annual_bill_idr / 12.0
    curve = [
        EstimatePoint(
            kwp=p.kwp,
            habit_savings_idr_per_month=round(p.habit_savings_idr_per_year / 12.0, 0),
            agent_savings_idr_per_month=round(p.agent_savings_idr_per_year / 12.0, 0),
        )
        for p in result.curve
    ]

    target_reached = result.min_kwp_agent is not None
    if target_reached:
        kwp = float(result.min_kwp_agent)
        monthly = result.target_monthly_savings_idr
    else:
        # Target tak tercapai dalam batas daya tersambung: pilih kWp > 0 dengan manfaat
        # bersih tahunan terbesar (hemat − CAPEX teranualisasi). Bila tak ada yang
        # positif, PLTS belum layak untuk profil ini.
        r, n = settings.discount_rate, settings.panel_lifetime_years
        crf = r / (1.0 - (1.0 + r) ** (-n)) if r > 0 else 1.0 / n
        cands = [p for p in result.curve if p.kwp > 0]
        best = max(
            cands,
            key=lambda p: p.agent_savings_idr_per_year - p.kwp * settings.capex_per_kwp_idr * crf,
            default=None,
        )
        if best is not None and best.agent_savings_idr_per_year - best.kwp * settings.capex_per_kwp_idr * crf > 0:
            kwp = float(best.kwp)
            monthly = best.agent_savings_idr_per_year / 12.0
        else:
            kwp = 0.0
            monthly = result.curve[0].agent_savings_idr_per_year / 12.0 if result.curve else 0.0

    capex = kwp * settings.capex_per_kwp_idr
    payback = round(capex / (monthly * 12.0), 1) if monthly > 0 and kwp > 0 else None
    savings_pct = 100.0 * monthly / ref_month if ref_month > 0 else 0.0

    if kwp <= 0:
        headline = "Dengan profil ini, PLTS atap belum memberi penghematan berarti."
    elif result.agent_reduces_panel and result.kwp_reduction_pct:
        headline = (
            f"Dengan jadwal agen, PLTS {kwp:.1f} kWp cukup — sekitar {result.kwp_reduction_pct:.0f}% "
            f"lebih kecil daripada tanpa pengaturan jadwal untuk hemat yang sama."
        )
    else:
        headline = f"PLTS sekitar {kwp:.1f} kWp memberi penghematan terbaik untuk profil ini."

    assumptions = [
        f"Tarif PLN {settings.tariff_group} Rp{tariff_idr_per_kwh(12):,.2f}/kWh".replace(",", "#").replace(".", ",").replace("#", "."),
        f"Biaya PLTS Rp{settings.capex_per_kwp_idr:,.0f}/kWp terpasang".replace(",", "."),
        "Ekspor listrik ke PLN tidak dihitung (Permen ESDM No. 2/2024)",
        f"Profil mesin tipikal & {settings.sizing_operating_days_per_week} hari kerja/minggu — ganti dengan data terukur kotak sensor",
        f"Cuaca: {'NASA POWER' if 'nasa' in result.pv_source else 'clear-sky terkoreksi'} untuk Sukoharjo",
    ]
    return EstimateResponse(
        connected_power_va=req.connected_power_va,
        machines=list(req.machines),
        recommended_kwp=round(kwp, 2) if kwp > 0 else None,
        kwp_without_agent=result.min_kwp_habit,
        kwp_reduction_pct=result.kwp_reduction_pct,
        monthly_bill_now_idr=round(ref_month, 0),
        monthly_savings_idr=round(monthly, 0),
        savings_pct=round(savings_pct, 1),
        capex_idr=round(capex, 0),
        payback_years=payback,
        target_savings_pct=TARGET_SAVINGS_PCT,
        target_reached=target_reached,
        tariff_idr_per_kwh=tariff_idr_per_kwh(12),
        tariff_group=settings.tariff_group,
        pv_source=result.pv_source,
        headline=headline,
        curve=curve,
        assumptions=assumptions,
        compute_time_s=result.compute_time_s,
    )


def _warm_up() -> None:
    """Hitung hari representatif (cuaca setahun) di latar belakang agar permintaan pertama cepat."""
    try:
        from app.sizing.annual import default_reference_year, representative_days, resolve_location

        lat, lon = resolve_location(None, None)
        representative_days(default_reference_year(), lat, lon)
    except Exception:  # noqa: BLE001 — pemanasan bersifat opsional
        pass


if settings.environment != "test" and "pytest" not in sys.modules:
    threading.Thread(target=_warm_up, name="waskita-public-warmup", daemon=True).start()


@router.post("/estimate", response_model=EstimateResponse)
async def public_estimate(req: EstimateRequest, request: Request) -> EstimateResponse:
    """Estimasi ukuran PLTS & penghematan untuk simulator landing page (tanpa login)."""
    key = (req.connected_power_va, tuple(req.machines))
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache.move_to_end(key)
            return cached

    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak permintaan, coba lagi sebentar lagi.",
        )
    try:
        resp = await run_in_threadpool(_estimate, req)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    with _cache_lock:
        _cache[key] = resp
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)
    return resp


@router.get("/catalog")
async def public_catalog() -> dict:
    """Katalog mesin & daya yang didukung simulator publik."""
    return {
        "machines": {k: {"label": v["label"], "power_w": v["power_w"]} for k, v in MACHINE_CATALOG.items()},
        "connected_power_va": list(ALLOWED_VA),
        "target_savings_pct": TARGET_SAVINGS_PCT,
    }

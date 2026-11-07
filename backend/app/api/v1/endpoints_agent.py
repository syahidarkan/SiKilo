"""
Endpoint layanan "Hemat" WASKITA: brief WhatsApp, nota mingguan, rapor kelayakan.

Semua endpoint butuh login. Akses data UMKM:
- role ``umkm``: hanya UMKM miliknya (``umkm_id`` boleh dikosongkan).
- ``admin``: UMKM mana pun (``umkm_id`` wajib).
- rapor per UMKM juga terbuka untuk ``bank``/``installer`` bila UMKM memberi
  persetujuan berbagi data (``consent_share_data``).
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.database import get_db
from app.models import UMKM, Role, User
from app.services import jobs
from app.services.scorecard_generator import generate_bankability_scorecard, render_scorecard_pdf
from app.services.whatsapp_agent import MAX_MESSAGE_CHARS
from app.services_data.ledger import resolve_umkm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent & Reports"])

OWNER_ROLES = (Role.UMKM.value, Role.ADMIN.value)
REPORT_SHARE_ROLES = (Role.BANK.value, Role.INSTALLER.value)


async def _owned_umkm(db: AsyncSession, user: User, umkm_id: Optional[int]) -> UMKM:
    """UMKM milik user (role umkm) atau sembarang UMKM (admin)."""
    return await resolve_umkm(db, user, umkm_id, share_roles=())


# ── WhatsApp: brief harian ─────────────────────────────────────────────────
@router.get("/whatsapp/daily-brief")
async def get_whatsapp_brief(
    umkm_id: Optional[int] = Query(default=None, description="Wajib untuk admin; role umkm memakai UMKM-nya"),
    target_date: Optional[date] = Query(default=None, description="Default: besok (WIB)"),
    solver: Literal["auto", "ortools", "ppo", "greedy"] = Query(default="auto"),
    save_plan: bool = Query(default=False, description="Simpan rencana ke DailyPlan"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*OWNER_ROLES)),
) -> dict[str, Any]:
    """Rencana nyata dari profil mesin UMKM → pesan WhatsApp (tidak dikirim)."""
    umkm = await _owned_umkm(db, user, umkm_id)
    target = target_date or (jobs.local_today() + timedelta(days=1))
    try:
        if save_plan:
            out = await jobs.run_daily_brief_for_umkm(db, umkm, target, send=False, solver=solver, source="manual")
            message, extra, plan_id = out.message, out.extra, out.plan_id
        else:
            plan = await jobs.plan_for_umkm(db, umkm, target, solver)
            from app.services.whatsapp_agent import generate_daily_brief

            message = generate_daily_brief(plan, umkm.name, target)
            extra = {
                "cost_idr": round(float(plan.cost_idr), 0),
                "baseline_cost_idr": round(float(plan.baseline_cost_idr), 0),
                "savings_idr": round(float(plan.savings_idr), 0),
                "savings_pct": round(float(plan.savings_pct), 1),
                "solver_used": str(plan.solver_used),
                "deadlines_met": bool(plan.deadlines_met),
                "notes": [str(n) for n in (plan.notes or [])],
            }
            plan_id = None
    except jobs.NoMachineProfiles:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "UMKM ini belum punya profil mesin. Isi profil mesin dulu agar jadwal bisa disusun.",
        )
    except TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Penyusunan jadwal terlalu lama; coba solver 'greedy'.")
    extra.pop("target_date", None)
    return {
        "umkm_id": umkm.id,
        "target_date": target.isoformat(),
        "message": message,
        "char_count": len(message),
        "max_chars": MAX_MESSAGE_CHARS,
        "plan_id": plan_id,
        "plan": extra,
        "phone_whatsapp_set": bool(umkm.phone_whatsapp),
    }


# ── WhatsApp: kirim sekarang ───────────────────────────────────────────────
class SendNowRequest(BaseModel):
    umkm_id: Optional[int] = Field(default=None, description="Wajib untuk admin")
    kind: Literal["daily", "weekly"] = "daily"
    target_date: Optional[date] = Field(default=None, description="daily: tanggal rencana (default besok); weekly: akhir minggu (default kemarin)")
    solver: Literal["auto", "ortools", "ppo", "greedy"] = "auto"


@router.post("/whatsapp/send-now")
async def send_now(
    req: Optional[SendNowRequest] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*OWNER_ROLES)),
) -> dict[str, Any]:
    """Kirim brief harian / nota mingguan sekarang juga (dicatat di MessageLog)."""
    req = req or SendNowRequest()
    umkm = await _owned_umkm(db, user, req.umkm_id)
    if not umkm.phone_whatsapp:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nomor WhatsApp UMKM belum diisi.")
    try:
        if req.kind == "daily":
            out = await jobs.run_daily_brief_for_umkm(
                db, umkm, req.target_date, send=True, solver=req.solver, source="manual"
            )
        else:
            out = await jobs.run_weekly_nota_for_umkm(db, umkm, req.target_date, send=True)
    except jobs.NoMachineProfiles:
        raise HTTPException(status.HTTP_409_CONFLICT, "UMKM ini belum punya profil mesin.")
    except TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Penyusunan jadwal terlalu lama; coba solver 'greedy'.")
    return {"kind": req.kind, **out.as_dict()}


# ── Nota mingguan ──────────────────────────────────────────────────────────
@router.get("/reports/weekly-nota")
async def weekly_nota(
    umkm_id: Optional[int] = Query(default=None),
    week_end: Optional[date] = Query(default=None, description="Hari terakhir periode (default kemarin, WIB)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*OWNER_ROLES)),
) -> dict[str, Any]:
    umkm = await _owned_umkm(db, user, umkm_id)
    message, usage, (start, end) = await jobs.build_weekly_nota(db, umkm, week_end)
    return {
        "umkm_id": umkm.id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "message": message,
        "char_count": len(message),
        "usage": [
            {
                "label": u.label,
                "kwh": round(u.kwh, 3),
                "cost_idr": round(u.cost_idr, 0),
                "prev_kwh": round(u.prev_kwh, 3),
                "prev_cost_idr": round(u.prev_cost_idr, 0),
                "off_hours_kwh": round(u.off_hours_kwh, 3),
                "off_hours_hours": u.off_hours_hours,
            }
            for u in usage
        ],
        "data_source": "EnergyLedger (estimasi NILM dari perangkat WASKITA)",
    }


# ── Rapor kelayakan ────────────────────────────────────────────────────────
class MachineUsageIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    kwh: float = Field(..., ge=0)
    cost_idr: float = Field(default=0.0, ge=0)


class ScorecardRequest(BaseModel):
    """Rapor dari angka yang diberikan pemanggil (tanpa membaca DB)."""

    umkm_name: str = Field(..., min_length=1, max_length=160)
    umkm_address: str = Field(default="", max_length=255)
    umkm_type: str = Field(default="UMKM", max_length=80)
    avg_monthly_bill_idr: float = Field(..., ge=0, description="Biaya listrik rata-rata per bulan (Rp)")
    sizing: dict[str, Any] = Field(..., description="SizingResult (pola pakai saat ini)")
    sizing_after_agent: Optional[dict[str, Any]] = Field(default=None, description="SizingResult bila beban mengikuti jadwal agen")
    agent_compare: Optional[dict[str, Any]] = Field(default=None, description="CompareResult dari /sizing/compare")
    audit_period_days: int = Field(default=30, ge=0, le=400)
    audit_period_start: Optional[date] = None
    audit_period_end: Optional[date] = None
    machine_usage: List[MachineUsageIn] = Field(default_factory=list)
    load_data_source: Literal["terukur", "simulasi", "input_pengguna"] = "input_pengguna"


_REQUIRED_SIZING = ("recommended_kwp", "capex_idr", "annual_savings_idr", "npv_idr", "payback_period_years")


def _scorecard_from_request(req: ScorecardRequest) -> dict[str, Any]:
    missing = [k for k in _REQUIRED_SIZING if k not in req.sizing]
    if missing:
        raise HTTPException(422, f"sizing tidak lengkap; field wajib: {', '.join(missing)}")
    return generate_bankability_scorecard(
        umkm_name=req.umkm_name,
        umkm_address=req.umkm_address,
        umkm_type=req.umkm_type,
        sizing=req.sizing,
        avg_monthly_pln_bill_idr=req.avg_monthly_bill_idr,
        audit_period_days=req.audit_period_days,
        sizing_after_agent=req.sizing_after_agent,
        agent_compare=req.agent_compare,
        machine_usage=[m.model_dump() for m in req.machine_usage],
        audit_period_start=req.audit_period_start,
        audit_period_end=req.audit_period_end,
        load_data_source=req.load_data_source,
        bill_source="terukur" if req.load_data_source == "terukur" else "input_pengguna",
    )


def _pdf_response(card: dict[str, Any]) -> Response:
    pdf = render_scorecard_pdf(card)
    name = re.sub(r"[^A-Za-z0-9]+", "-", str(card.get("umkm_profile", {}).get("name") or "umkm")).strip("-")[:40]
    filename = f"rapor-waskita-{name or 'umkm'}-{card.get('report_meta', {}).get('prepared_date', '')}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/reports/bankability-scorecard")
async def post_bankability_scorecard(
    req: ScorecardRequest,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Rapor kelayakan (JSON) dari hasil sizing yang dikirim pemanggil."""
    return _scorecard_from_request(req)


@router.post("/reports/bankability-scorecard.pdf", response_class=Response)
async def post_bankability_scorecard_pdf(
    req: ScorecardRequest,
    user: User = Depends(get_current_user),
) -> Response:
    """Rapor kelayakan (PDF) dari hasil sizing yang dikirim pemanggil."""
    return _pdf_response(_scorecard_from_request(req))


async def _scorecard_for_umkm(db: AsyncSession, user: User, umkm_id: Optional[int]) -> dict[str, Any]:
    from app.services import scorecard_data

    umkm = await resolve_umkm(db, user, umkm_id, share_roles=REPORT_SHARE_ROLES)
    try:
        return await scorecard_data.build_scorecard_for_umkm(db, umkm)
    except scorecard_data.InsufficientData as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except TimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Perhitungan sizing terlalu lama; coba lagi nanti.")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Rapor UMKM %s gagal.", umkm.id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"Rapor gagal dihitung: {type(exc).__name__}")


@router.get("/reports/bankability-scorecard")
async def get_bankability_scorecard(
    umkm_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Rapor kelayakan (JSON) dari data perangkat UMKM di basis data."""
    return await _scorecard_for_umkm(db, user, umkm_id)


@router.get("/reports/bankability-scorecard.pdf", response_class=Response)
async def get_bankability_scorecard_pdf(
    umkm_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Rapor kelayakan (PDF) dari data perangkat UMKM di basis data."""
    return _pdf_response(await _scorecard_for_umkm(db, user, umkm_id))

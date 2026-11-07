"""
Dashboard multi-peran WASKITA.

- ``GET  /dashboard/umkm``          — umkm (miliknya) / admin (``umkm_id``).
- ``GET  /dashboard/disperinaker``  — disperinaker / admin: agregat UMKM yang consent.
- ``GET  /dashboard/leads``         — installer (ditugaskan + terbuka), umkm (miliknya), admin (semua).
- ``POST /dashboard/leads``         — umkm ("saya tertarik PLTS") / admin.
- ``PATCH /dashboard/leads/{id}``   — installer / admin (umkm hanya boleh membatalkan).
- ``GET  /dashboard/bank``          — bank / admin: rapor ringkas UMKM yang consent (read-only).
- ``GET  /dashboard/kpi``           — semua role; cakupan data menyesuaikan role.

Privasi: data per UMKM hanya tampil untuk pihak ketiga bila
``UMKM.consent_share_data`` = True. UMKM yang tidak consent hanya dihitung
dalam jumlah total (tanpa nama/energi). Pengecualian: lead yang DIAJUKAN
UMKM sendiri — nama, alamat, dan WhatsApp dibagikan ke installer agar bisa
dihubungi.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models import UMKM, DailyPlan, Device, Lead, Role, User
from app.models.types import utcnow
from app.schemas.dashboard import (
    ApplianceEnergy,
    BankDashboard,
    BankUMKMItem,
    DeviceSummary,
    DisperinakerDashboard,
    EnergyPeriod,
    KecamatanStat,
    KPIBoard,
    KPIMetric,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    PlanSummary,
    RaporSummary,
    UMKMAggregateItem,
    UMKMDashboard,
    UMKMProfileOut,
)
from app.schemas.telemetry import local_tz
from app.services_data import kpi, rapor
from app.services_data.ledger import resolve_umkm, top_appliances, totals_by_umkm

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

OPEN_LEAD_STATUSES = ("new", "contacted", "surveyed")


def _today() -> date:
    return datetime.now(local_tz()).date()


async def _period(db: AsyncSession, umkm_id: int, start: date, end: date) -> EnergyPeriod:
    t = (await totals_by_umkm(db, [umkm_id], start, end)).get(umkm_id, {})
    return EnergyPeriod(
        start=start,
        end=end,
        kwh=round(t.get("kwh", 0.0), 3),
        cost_idr=round(t.get("cost_idr", 0.0), 0),
        days_with_data=int(t.get("days", 0)),
    )


def _is_online(last_seen: Optional[datetime]) -> bool:
    if last_seen is None:
        return False
    return (datetime.now(timezone.utc) - last_seen).total_seconds() <= settings.device_online_window_s


def _lead_out(lead: Lead, umkm: Optional[UMKM], *, with_contact: bool) -> LeadOut:
    return LeadOut(
        id=lead.id,
        umkm_id=lead.umkm_id,
        umkm_name=umkm.name if umkm else None,
        umkm_type=umkm.umkm_type if umkm else None,
        kecamatan=umkm.kecamatan if umkm else None,
        address=umkm.address if (umkm and with_contact) else None,
        phone_whatsapp=umkm.phone_whatsapp if (umkm and with_contact) else None,
        pv_kwp=umkm.pv_kwp if umkm else None,
        installer_user_id=lead.installer_user_id,
        status=lead.status,  # type: ignore[arg-type]
        recommended_kwp=round(lead.recommended_kwp or 0.0, 2),
        notes=lead.notes,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
    )


async def _consent_umkm(db: AsyncSession) -> list[UMKM]:
    result = await db.execute(select(UMKM).where(UMKM.consent_share_data.is_(True)).order_by(UMKM.id))
    return list(result.scalars())


# ── UMKM ────────────────────────────────────────────────────────────────────
@router.get("/umkm", response_model=UMKMDashboard)
async def umkm_dashboard(
    umkm_id: Optional[int] = Query(None, description="Wajib untuk admin"),
    include_rapor: bool = Query(False, description="Sertakan ringkasan kelayakan PLTS (perhitungan pertama bisa belasan detik; lalu di-cache)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin")),
) -> UMKMDashboard:
    umkm = await resolve_umkm(db, user, umkm_id, share_roles=())
    today = _today()
    p_today = await _period(db, umkm.id, today, today)
    p7 = await _period(db, umkm.id, today - timedelta(days=6), today)
    p30 = await _period(db, umkm.id, today - timedelta(days=29), today)
    top = await top_appliances(db, umkm.id, today - timedelta(days=29), today, limit=8)

    devices = (await db.execute(select(Device).where(Device.umkm_id == umkm.id).order_by(Device.id))).scalars().all()
    plans = await kpi.latest_plans(db, [umkm.id], today - timedelta(days=29), today)
    plans.sort(key=lambda p: (p.day, p.created_at))
    latest = plans[-1] if plans else None
    leads = (
        await db.execute(select(Lead).where(Lead.umkm_id == umkm.id).order_by(Lead.created_at.desc()))
    ).scalars().all()

    rapor_out = RaporSummary(**(await rapor.rapor_summary(db, umkm, today))) if include_rapor else None
    notes = [
        "kWh & Rp per mesin = estimasi disagregasi NILM; hanya jam yang sudah selesai.",
        "Penghematan rencana agen = estimasi tiruan digital, bukan hasil ukur meter.",
    ]
    if not devices:
        notes.append("Belum ada perangkat ukur terdaftar untuk UMKM ini.")
    return UMKMDashboard(
        generated_at=utcnow(),
        umkm=UMKMProfileOut.model_validate(umkm),
        today=p_today,
        last_7_days=p7,
        last_30_days=p30,
        top_appliances=[ApplianceEnergy(**t) for t in top],
        devices=[
            DeviceSummary(
                device_id=d.device_id,
                firmware_version=d.firmware_version,
                last_seen=d.last_seen,
                online=_is_online(d.last_seen),
            )
            for d in devices
        ],
        latest_plan=PlanSummary.model_validate(latest) if latest else None,
        plans_30d={
            "n_days": len(plans),
            "avg_savings_pct": round(sum(p.savings_pct for p in plans) / len(plans), 2) if plans else None,
            "total_savings_idr": round(sum(p.savings_idr for p in plans), 0) if plans else None,
            "deadlines_met_pct": round(100.0 * sum(p.deadlines_met for p in plans) / len(plans), 1) if plans else None,
        },
        leads=[_lead_out(lead, umkm, with_contact=True) for lead in leads],
        rapor=rapor_out,
        notes=notes,
    )


# ── Disperinaker ────────────────────────────────────────────────────────────
@router.get("/disperinaker", response_model=DisperinakerDashboard)
async def disperinaker_dashboard(
    days: int = Query(30, ge=1, le=366),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("disperinaker", "admin")),
) -> DisperinakerDashboard:
    end = _today()
    start = end - timedelta(days=days - 1)
    n_total = int(await db.scalar(select(func.count(UMKM.id))) or 0)
    consent = await _consent_umkm(db)
    ids = [u.id for u in consent]
    totals = await totals_by_umkm(db, ids, start, end)
    plans = await kpi.latest_plans(db, ids, start, end)

    plan_by_umkm: dict[int, list[DailyPlan]] = defaultdict(list)
    for p in plans:
        plan_by_umkm[p.umkm_id].append(p)
    potential: dict[int, float] = {
        uid: 30.0 * sum(p.savings_idr for p in ps) / len(ps) for uid, ps in plan_by_umkm.items() if ps
    }

    leads = (await db.execute(select(Lead).where(Lead.umkm_id.in_(ids or [-1])))).scalars().all()
    lead_counts: dict[str, int] = defaultdict(int)
    for lead in leads:
        lead_counts[lead.status] += 1

    kec: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    items: list[UMKMAggregateItem] = []
    min_days = settings.sizing_min_data_days
    for u in consent:
        t = totals.get(u.id, {"kwh": 0.0, "cost_idr": 0.0, "days": 0})
        name = u.kecamatan.strip() or "Tidak diisi"
        kec[name]["n_umkm"] += 1
        kec[name]["kwh"] += t["kwh"]
        kec[name]["cost_idr"] += t["cost_idr"]
        kec[name]["potential"] += potential.get(u.id, 0.0)
        has_pv = (u.pv_kwp or 0.0) > 0
        items.append(
            UMKMAggregateItem(
                umkm_id=u.id,
                name=u.name,
                umkm_type=u.umkm_type,
                kecamatan=u.kecamatan,
                kwh=round(t["kwh"], 3),
                cost_idr=round(t["cost_idr"], 0),
                days_with_data=int(t["days"]),
                has_pv=has_pv,
                ready_for_pv=(not has_pv) and int(t["days"]) >= min_days,
            )
        )
    items.sort(key=lambda i: -i.kwh)

    return DisperinakerDashboard(
        generated_at=utcnow(),
        start=start,
        end=end,
        n_umkm_total=n_total,
        n_umkm_consent=len(consent),
        n_umkm_with_data=sum(1 for u in ids if totals.get(u, {}).get("days", 0) > 0),
        total_kwh=round(sum(t["kwh"] for t in totals.values()), 3),
        total_cost_idr=round(sum(t["cost_idr"] for t in totals.values()), 0),
        recorded_plan_savings_idr=round(sum(p.savings_idr for p in plans), 0),
        potential_savings_idr_per_month=round(sum(potential.values()), 0),
        kecamatan=sorted(
            (
                KecamatanStat(
                    kecamatan=k,
                    n_umkm=int(v["n_umkm"]),
                    kwh=round(v["kwh"], 3),
                    cost_idr=round(v["cost_idr"], 0),
                    potential_savings_idr_per_month=round(v["potential"], 0),
                )
                for k, v in kec.items()
            ),
            key=lambda s: -s.kwh,
        ),
        plts={
            "n_with_pv": sum(1 for i in items if i.has_pv),
            "n_ready_for_pv": sum(1 for i in items if i.ready_for_pv),
            "ready_definition": f"belum ber-PLTS dan punya ≥ {min_days} hari data dalam periode",
            "leads_by_status": dict(lead_counts),
            "total_pv_kwp": round(sum(u.pv_kwp or 0.0 for u in consent), 2),
        },
        umkm=items,
        notes=[
            "Hanya UMKM yang memberi persetujuan berbagi data yang dirinci; sisanya hanya dihitung di n_umkm_total.",
            "Potensi hemat = rata-rata penghematan harian rencana agen × 30 (estimasi tiruan digital).",
            "kWh per UMKM berasal dari buku energi perangkat WASKITA, bukan tagihan PLN.",
        ],
    )


# ── Lead (rujukan PLTS) ─────────────────────────────────────────────────────
async def _recommended_kwp(db: AsyncSession, umkm: UMKM) -> tuple[float, str]:
    summary = await rapor.rapor_summary(db, umkm, _today())
    if summary["status"] == "ok" and summary.get("recommended_kwp"):
        return float(summary["recommended_kwp"]), summary["note"]
    return 0.0, summary.get("note") or "Rekomendasi kWp belum tersedia."


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    req: LeadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin")),
) -> LeadOut:
    """UMKM menyatakan tertarik PLTS (atau admin membuat rujukan)."""
    is_admin = user.role == Role.ADMIN.value
    if not is_admin and (req.installer_user_id is not None or req.recommended_kwp is not None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "installer_user_id dan recommended_kwp hanya untuk admin")
    umkm = await resolve_umkm(db, user, req.umkm_id, share_roles=())

    open_lead = await db.scalar(
        select(Lead.id).where(Lead.umkm_id == umkm.id, Lead.status.in_(OPEN_LEAD_STATUSES)).limit(1)
    )
    if open_lead is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"UMKM ini masih punya rujukan aktif (id {open_lead})")

    if req.installer_user_id is not None:
        inst = await db.get(User, req.installer_user_id)
        if inst is None or inst.role != Role.INSTALLER.value or not inst.is_active:
            raise HTTPException(422, "installer_user_id bukan installer aktif")

    notes = req.notes
    if req.recommended_kwp is not None:
        kwp = req.recommended_kwp
    else:
        kwp, kwp_note = await _recommended_kwp(db, umkm)
        notes = "\n".join(filter(None, [notes, f"[WASKITA] {kwp_note}"]))
    lead = Lead(
        umkm_id=umkm.id,
        installer_user_id=req.installer_user_id,
        status="new",
        recommended_kwp=kwp,
        notes=notes,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead, umkm, with_contact=True)


@router.get("/leads", response_model=list[LeadOut])
async def list_leads(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("installer", "umkm", "admin")),
) -> list[LeadOut]:
    stmt = select(Lead, UMKM).join(UMKM, UMKM.id == Lead.umkm_id)
    if user.role == Role.INSTALLER.value:
        stmt = stmt.where(
            or_(
                Lead.installer_user_id == user.id,
                (Lead.installer_user_id.is_(None)) & (Lead.status == "new"),
            )
        )
    elif user.role == Role.UMKM.value:
        stmt = stmt.where(Lead.umkm_id == (user.umkm_id if user.umkm_id is not None else -1))
    if status_filter:
        stmt = stmt.where(Lead.status == status_filter)
    stmt = stmt.order_by(Lead.updated_at.desc(), Lead.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).all()
    return [_lead_out(lead, umkm, with_contact=True) for lead, umkm in rows]


@router.patch("/leads/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: int,
    req: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("installer", "umkm", "admin")),
) -> LeadOut:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rujukan tidak ditemukan")
    umkm = await db.get(UMKM, lead.umkm_id)

    if user.role == Role.UMKM.value:
        if lead.umkm_id != user.umkm_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Rujukan tidak ditemukan")
        if req.claim or req.installer_user_id is not None or req.unassign or req.recompute_kwp:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Pemilik UMKM hanya dapat membatalkan rujukan atau menambah catatan")
        if req.status is not None and req.status != "lost":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Pemilik UMKM hanya dapat mengubah status menjadi 'lost' (batal)")
    elif user.role == Role.INSTALLER.value:
        if req.installer_user_id is not None or req.unassign:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Penugasan installer hanya oleh admin")
        if lead.installer_user_id is None:
            if lead.status != "new":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Rujukan tidak ditemukan")
            lead.installer_user_id = user.id  # perubahan apa pun = mengambil lead
        elif lead.installer_user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Rujukan ini ditangani installer lain")
    else:  # admin
        if req.unassign:
            lead.installer_user_id = None
        elif req.installer_user_id is not None:
            inst = await db.get(User, req.installer_user_id)
            if inst is None or inst.role != Role.INSTALLER.value or not inst.is_active:
                raise HTTPException(422, "installer_user_id bukan installer aktif")
            lead.installer_user_id = inst.id

    if req.status is not None:
        lead.status = req.status
    if req.notes is not None:
        lead.notes = req.notes
    if req.recompute_kwp and umkm is not None:
        kwp, _note = await _recommended_kwp(db, umkm)
        if kwp > 0:
            lead.recommended_kwp = kwp
    lead.updated_at = utcnow()
    await db.commit()
    await db.refresh(lead)
    return _lead_out(lead, umkm, with_contact=True)


# ── Bank / koperasi ─────────────────────────────────────────────────────────
@router.get("/bank", response_model=BankDashboard)
async def bank_dashboard(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles("bank", "admin")),
) -> BankDashboard:
    consent = await _consent_umkm(db)
    today = _today()
    items: list[BankUMKMItem] = []
    for u in consent[offset: offset + limit]:
        summary = await rapor.rapor_summary(db, u, today)
        items.append(
            BankUMKMItem(
                umkm_id=u.id,
                name=u.name,
                umkm_type=u.umkm_type,
                kecamatan=u.kecamatan,
                pv_kwp=u.pv_kwp or 0.0,
                rapor=RaporSummary(**summary),
            )
        )
    return BankDashboard(
        generated_at=utcnow(),
        total=len(consent),
        items=items,
        notes=[
            "Hanya UMKM yang memberi persetujuan berbagi data.",
            "Read-only. Skor & PBP adalah perkiraan otomatis dari data perangkat (30 hari terakhir), "
            "belum divalidasi auditor energi.",
        ],
    )


# ── KPI board ───────────────────────────────────────────────────────────────
@router.get("/kpi", response_model=KPIBoard)
async def kpi_board(
    days: int = Query(30, ge=1, le=366),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KPIBoard:
    """Papan indikator: akurasi NILM, selisih tagihan simulator, penghematan, ketepatan pesanan, perangkat online."""
    if user.role == Role.ADMIN.value:
        ids: Optional[list[int]] = None
        scope = "semua UMKM"
    elif user.role == Role.UMKM.value:
        ids = [user.umkm_id] if user.umkm_id is not None else []
        scope = "UMKM Anda"
    else:
        ids = [u.id for u in await _consent_umkm(db)]
        scope = "UMKM yang memberi persetujuan berbagi data"
    end = _today()
    start = end - timedelta(days=days - 1)
    plans = await kpi.latest_plans(db, ids, start, end)
    metrics: list[dict[str, Any]] = [
        kpi.nilm_accuracy_metric(),
        kpi.twin_bill_error_metric(),
        *kpi.plan_metrics(plans, f"{start} s/d {end}"),
        await kpi.devices_metric(db, ids),
    ]
    return KPIBoard(
        generated_at=utcnow(),
        scope=scope,
        period_days=days,
        metrics=[KPIMetric(**m) for m in metrics],
    )

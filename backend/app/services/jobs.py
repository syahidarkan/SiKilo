"""
Logika job layanan "Hemat" WASKITA (dipanggil penjadwal, endpoint manual, dan tes).

Job harian (``run_daily_briefs``)
    Untuk tiap UMKM yang punya nomor WhatsApp DAN minimal satu ``MachineProfile``:
    ``plan_day`` untuk BESOK (pakai ``pv_kwp`` & ``battery_kwh`` UMKM) → simpan
    ``DailyPlan`` → susun brief → kirim → simpan ``MessageLog``.
Job mingguan (``run_weekly_notas``)
    Nota mingguan dari ``EnergyLedger`` (7 hari terakhir yang sudah lengkap vs
    7 hari sebelumnya) → kirim → ``MessageLog``.

Setiap UMKM diproses dengan sesi DB sendiri; kegagalan satu UMKM tidak
menghentikan yang lain.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import UMKM, DailyPlan, EnergyLedger, MachineProfile, MessageLog
from app.services.whatsapp_agent import (
    BASELOAD_LABEL,
    MachineWeekUsage,
    generate_daily_brief,
    generate_weekly_nota,
)
from app.services.whatsapp_sender import SendResult, send_whatsapp

logger = logging.getLogger(__name__)

PLAN_TIMEOUT_S = 120.0


class NoMachineProfiles(Exception):
    """UMKM belum punya profil mesin sehingga jadwal tidak bisa disusun."""


# ── Waktu lokal ────────────────────────────────────────────────────────────
def local_tz():
    from app.schemas.telemetry import local_tz as _tz

    return _tz()


def local_now() -> datetime:
    return datetime.now(local_tz())


def local_today() -> date:
    return local_now().date()


# ── Profil mesin → MachineJob ──────────────────────────────────────────────
async def load_machine_profiles(db: AsyncSession, umkm_id: int) -> list[MachineProfile]:
    result = await db.execute(
        select(MachineProfile).where(MachineProfile.umkm_id == umkm_id).order_by(MachineProfile.id)
    )
    return list(result.scalars().all())


def profiles_to_jobs(profiles: list[MachineProfile]) -> tuple[list[Any], list[str]]:
    """Ubah ``MachineProfile`` → ``MachineJob``; profil tidak valid dilewati dengan catatan."""
    from app.schemas.dispatch import MachineJob

    jobs: list[Any] = []
    notes: list[str] = []
    for p in profiles:
        try:
            jobs.append(
                MachineJob(
                    machine_id=p.machine_id,
                    appliance_class=p.appliance_class,
                    label=p.label,
                    power_w=p.power_w,
                    daily_runtime_minutes=p.daily_runtime_minutes,
                    earliest_hour=p.earliest_hour,
                    deadline_hour=p.deadline_hour,
                    habit_start_hour=p.habit_start_hour,
                    is_flexible=p.is_flexible,
                    min_continuous_minutes=max(15, int(p.min_continuous_minutes or 15)),
                )
            )
        except Exception as exc:  # noqa: BLE001 - pydantic ValidationError dll.
            notes.append(f"Profil mesin {p.machine_id} dilewati: {exc.__class__.__name__}")
    return jobs, notes


def build_battery(battery_kwh: float):
    if not battery_kwh or battery_kwh <= 0:
        return None
    from app.digital_twin.battery import Battery

    return Battery.from_kwh(float(battery_kwh))


async def plan_for_umkm(
    db: AsyncSession, umkm: UMKM, target_date: date, solver: Optional[str] = None
):
    """``plan_day`` untuk UMKM (di thread terpisah). Melempar ``NoMachineProfiles`` bila kosong."""
    from app.agent.planner import plan_day

    profiles = await load_machine_profiles(db, umkm.id)
    jobs, notes = profiles_to_jobs(profiles)
    if not jobs:
        raise NoMachineProfiles(f"UMKM {umkm.id} belum punya profil mesin yang valid")
    kwp = float(umkm.pv_kwp or 0.0)
    battery = build_battery(float(umkm.battery_kwh or 0.0))
    plan = await asyncio.wait_for(
        asyncio.to_thread(
            plan_day,
            jobs,
            target_date,
            kwp=kwp,
            battery=battery,
            solver=solver or settings.scheduler_solver,
        ),
        timeout=PLAN_TIMEOUT_S,
    )
    if notes:
        try:
            plan.notes = list(getattr(plan, "notes", []) or []) + notes
        except Exception:  # noqa: BLE001
            pass
    return plan


def plan_payload(plan: Any, umkm: UMKM, source: str) -> dict[str, Any]:
    """Ringkasan rencana yang ringkas untuk ``DailyPlan.payload_json`` (JSON-safe)."""
    import numpy as np

    from app.services.whatsapp_agent import brief_data

    d = brief_data(plan)
    schedule = np.asarray(plan.schedule)
    return {
        "source": source,
        "kwp": float(umkm.pv_kwp or 0.0),
        "battery_kwh": float(umkm.battery_kwh or 0.0),
        "pv_source": str(getattr(plan, "pv_source", "none")),
        "machines": [
            {
                "machine_id": m.machine_id,
                "label": m.label,
                "blocks": [list(b) for b in m.blocks],
                "scheduled_minutes": int(schedule[:, i].sum()) * 15 if schedule.ndim == 2 else 0,
                "deadline_met": m.deadline_met,
            }
            for i, m in enumerate(d.machines)
        ],
        "grid_kwh": round(float(getattr(plan, "grid_kwh", 0.0) or 0.0), 3),
        "pv_used_kwh": round(float(getattr(plan, "pv_used_kwh", 0.0) or 0.0), 3),
        "curtail_kwh": round(float(getattr(plan, "curtail_kwh", 0.0) or 0.0), 3),
        "baseline_grid_kwh": round(float(getattr(plan, "baseline_grid_kwh", 0.0) or 0.0), 3),
        "idle_savings_idr": round(float(getattr(plan, "idle_savings_idr", 0.0) or 0.0), 0),
        "shifting_savings_idr": round(float(getattr(plan, "shifting_savings_idr", 0.0) or 0.0), 0),
        "violations": [str(v) for v in (getattr(plan, "violations", None) or [])],
        "notes": [str(n) for n in (getattr(plan, "notes", None) or [])],
    }


async def save_daily_plan(db: AsyncSession, umkm: UMKM, target_date: date, plan: Any, source: str) -> DailyPlan:
    row = DailyPlan(
        umkm_id=umkm.id,
        day=target_date,
        solver=str(plan.solver_used)[:32],
        cost_idr=round(float(plan.cost_idr), 2),
        baseline_cost_idr=round(float(plan.baseline_cost_idr), 2),
        savings_idr=round(float(plan.savings_idr), 2),
        savings_pct=round(float(plan.savings_pct), 2),
        deadlines_met=bool(plan.deadlines_met),
        payload_json=plan_payload(plan, umkm, source),
    )
    db.add(row)
    await db.flush()
    return row


async def send_and_log(db: AsyncSession, umkm: UMKM, kind: str, body: str) -> tuple[SendResult, MessageLog]:
    result = await send_whatsapp(umkm.phone_whatsapp, body)
    log = MessageLog(
        umkm_id=umkm.id,
        kind=kind,
        provider=result.provider,
        status=result.status,
        body=body,
        error=result.error,
    )
    db.add(log)
    await db.flush()
    return result, log


# ── Brief harian ───────────────────────────────────────────────────────────
@dataclass
class JobOutcome:
    umkm_id: int
    status: str  # sent | failed | skipped | no_profiles | error | not_sent
    message: str = ""
    error: Optional[str] = None
    plan_id: Optional[int] = None
    message_log_id: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "umkm_id": self.umkm_id,
            "status": self.status,
            "message": self.message,
            "error": self.error,
            "plan_id": self.plan_id,
            "message_log_id": self.message_log_id,
            **self.extra,
        }


async def run_daily_brief_for_umkm(
    db: AsyncSession,
    umkm: UMKM,
    target_date: Optional[date] = None,
    *,
    send: bool = True,
    solver: Optional[str] = None,
    source: str = "scheduler",
) -> JobOutcome:
    """Rencanakan, simpan ``DailyPlan``, (opsional) kirim brief + ``MessageLog``. Commit di akhir."""
    target_date = target_date or (local_today() + timedelta(days=1))
    plan = await plan_for_umkm(db, umkm, target_date, solver)
    row = await save_daily_plan(db, umkm, target_date, plan, source)
    body = generate_daily_brief(plan, umkm.name, target_date)
    outcome = JobOutcome(umkm_id=umkm.id, status="not_sent", message=body, plan_id=row.id)
    outcome.extra = {
        "target_date": target_date.isoformat(),
        "cost_idr": round(float(plan.cost_idr), 0),
        "baseline_cost_idr": round(float(plan.baseline_cost_idr), 0),
        "savings_idr": round(float(plan.savings_idr), 0),
        "savings_pct": round(float(plan.savings_pct), 1),
        "solver_used": str(plan.solver_used),
        "deadlines_met": bool(plan.deadlines_met),
        "notes": [str(n) for n in (plan.notes or [])],
    }
    if send:
        result, log = await send_and_log(db, umkm, "daily", body)
        outcome.status = result.status
        outcome.error = result.error
        outcome.message_log_id = log.id
    await db.commit()
    return outcome


async def eligible_umkm_ids(db: AsyncSession) -> list[int]:
    """UMKM yang punya nomor WhatsApp dan minimal satu profil mesin."""
    has_profile = select(MachineProfile.id).where(MachineProfile.umkm_id == UMKM.id).exists()
    result = await db.execute(
        select(UMKM.id)
        .where(and_(UMKM.phone_whatsapp.is_not(None), UMKM.phone_whatsapp != "", has_profile))
        .order_by(UMKM.id)
    )
    return [int(x) for x in result.scalars().all()]


async def umkm_with_phone_ids(db: AsyncSession) -> list[int]:
    result = await db.execute(
        select(UMKM.id).where(and_(UMKM.phone_whatsapp.is_not(None), UMKM.phone_whatsapp != "")).order_by(UMKM.id)
    )
    return [int(x) for x in result.scalars().all()]


def _default_session_factory() -> Callable[[], Any]:
    from app.core.database import AsyncSessionLocal

    return AsyncSessionLocal


async def run_daily_briefs(
    target_date: Optional[date] = None,
    *,
    session_factory: Optional[Callable[[], Any]] = None,
    solver: Optional[str] = None,
    send: bool = True,
) -> dict[str, Any]:
    """Job harian penjadwal: brief untuk BESOK ke semua UMKM yang memenuhi syarat."""
    factory = session_factory or _default_session_factory()
    target_date = target_date or (local_today() + timedelta(days=1))
    async with factory() as db:
        ids = await eligible_umkm_ids(db)
    outcomes: list[dict[str, Any]] = []
    for umkm_id in ids:
        async with factory() as db:
            umkm = await db.get(UMKM, umkm_id)
            if umkm is None:
                continue
            try:
                out = await run_daily_brief_for_umkm(
                    db, umkm, target_date, send=send, solver=solver, source="scheduler"
                )
            except NoMachineProfiles as exc:
                await db.rollback()
                out = JobOutcome(umkm_id=umkm_id, status="no_profiles", error=str(exc))
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                logger.exception("Brief harian UMKM %s gagal.", umkm_id)
                out = JobOutcome(umkm_id=umkm_id, status="error", error=f"{type(exc).__name__}: {exc}"[:300])
        outcomes.append(out.as_dict())
    summary = _summarize(outcomes)
    summary["target_date"] = target_date.isoformat()
    logger.info("Job brief harian %s: %s", target_date, summary["counts"])
    return summary


# ── Nota mingguan ──────────────────────────────────────────────────────────
def week_bounds(week_end: Optional[date] = None) -> tuple[date, date, date, date]:
    """(awal, akhir) minggu ini & minggu lalu. Default akhir = kemarin (hari lengkap terakhir)."""
    end = week_end or (local_today() - timedelta(days=1))
    start = end - timedelta(days=6)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    return start, end, prev_start, prev_end


def _is_off_hours(hour: int) -> bool:
    return hour < settings.work_start_hour or hour >= settings.work_end_hour


async def weekly_usage(db: AsyncSession, umkm_id: int, week_end: Optional[date] = None) -> list[MachineWeekUsage]:
    """Agregasi ``EnergyLedger`` per label untuk minggu ini vs minggu lalu."""
    start, end, prev_start, prev_end = week_bounds(week_end)
    result = await db.execute(
        select(
            EnergyLedger.appliance_label,
            EnergyLedger.day,
            EnergyLedger.hour,
            func.sum(EnergyLedger.kwh),
            func.sum(EnergyLedger.cost_idr),
        )
        .where(EnergyLedger.umkm_id == umkm_id, EnergyLedger.day >= prev_start, EnergyLedger.day <= end)
        .group_by(EnergyLedger.appliance_label, EnergyLedger.day, EnergyLedger.hour)
    )
    usage: dict[str, MachineWeekUsage] = {}
    off_hours_seen: dict[str, set[tuple[date, int]]] = {}
    for label, d, hour, kwh, cost in result.all():
        u = usage.setdefault(label, MachineWeekUsage(label=label))
        kwh_f, cost_f = float(kwh or 0.0), float(cost or 0.0)
        if start <= d <= end:
            u.kwh += kwh_f
            u.cost_idr += cost_f
            if label != BASELOAD_LABEL and _is_off_hours(int(hour)) and kwh_f > 0.01:
                u.off_hours_kwh += kwh_f
                u.off_hours_cost_idr += cost_f
                off_hours_seen.setdefault(label, set()).add((d, int(hour)))
        else:
            u.prev_kwh += kwh_f
            u.prev_cost_idr += cost_f
    for label, seen in off_hours_seen.items():
        usage[label].off_hours_hours = len(seen)
    return sorted(usage.values(), key=lambda u: u.cost_idr, reverse=True)


async def build_weekly_nota(
    db: AsyncSession, umkm: UMKM, week_end: Optional[date] = None
) -> tuple[str, list[MachineWeekUsage], tuple[date, date]]:
    start, end, _, _ = week_bounds(week_end)
    usage = await weekly_usage(db, umkm.id, end)
    return generate_weekly_nota(umkm.name, start, end, usage), usage, (start, end)


async def run_weekly_nota_for_umkm(
    db: AsyncSession, umkm: UMKM, week_end: Optional[date] = None, *, send: bool = True
) -> JobOutcome:
    body, usage, (start, end) = await build_weekly_nota(db, umkm, week_end)
    outcome = JobOutcome(
        umkm_id=umkm.id,
        status="not_sent",
        message=body,
        extra={"week_start": start.isoformat(), "week_end": end.isoformat()},
    )
    if send:
        result, log = await send_and_log(db, umkm, "weekly", body)
        outcome.status = result.status
        outcome.error = result.error
        outcome.message_log_id = log.id
    await db.commit()
    return outcome


async def run_weekly_notas(
    week_end: Optional[date] = None,
    *,
    session_factory: Optional[Callable[[], Any]] = None,
    send: bool = True,
) -> dict[str, Any]:
    """Job mingguan penjadwal: nota mingguan ke semua UMKM yang punya nomor WhatsApp."""
    factory = session_factory or _default_session_factory()
    async with factory() as db:
        ids = await umkm_with_phone_ids(db)
    outcomes: list[dict[str, Any]] = []
    for umkm_id in ids:
        async with factory() as db:
            umkm = await db.get(UMKM, umkm_id)
            if umkm is None:
                continue
            try:
                out = await run_weekly_nota_for_umkm(db, umkm, week_end, send=send)
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                logger.exception("Nota mingguan UMKM %s gagal.", umkm_id)
                out = JobOutcome(umkm_id=umkm_id, status="error", error=f"{type(exc).__name__}: {exc}"[:300])
        outcomes.append(out.as_dict())
    summary = _summarize(outcomes)
    _, end, _, _ = week_bounds(week_end)
    summary["week_end"] = end.isoformat()
    logger.info("Job nota mingguan %s: %s", end, summary["counts"])
    return summary


def _summarize(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o["status"]] = counts.get(o["status"], 0) + 1
    return {"processed": len(outcomes), "counts": counts, "results": outcomes}


__all__ = [
    "JobOutcome",
    "NoMachineProfiles",
    "build_weekly_nota",
    "eligible_umkm_ids",
    "local_today",
    "plan_for_umkm",
    "profiles_to_jobs",
    "run_daily_brief_for_umkm",
    "run_daily_briefs",
    "run_weekly_nota_for_umkm",
    "run_weekly_notas",
    "week_bounds",
    "weekly_usage",
]

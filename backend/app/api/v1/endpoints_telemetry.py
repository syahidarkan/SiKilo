"""
Telemetri lapangan WASKITA.

Firmware (header ``X-Device-Key``):
- ``POST /telemetry/ingest``        — satu sampel.
- ``POST /telemetry/ingest-batch``  — ≤ 500 sampel (buffer offline), diurutkan menurut waktu.

Dashboard (JWT):
- ``GET /telemetry/ledger``             — kWh & Rp per mesin per jam/hari.
- ``GET /telemetry/appliances/status``  — status ON/OFF terakhir per mesin.
- ``GET /telemetry/records``            — sampel mentah tersimpan (untuk grafik).

Akses data UMKM: pemilik (role umkm), admin, atau disperinaker/installer/bank
bila UMKM memberi persetujuan berbagi data (``consent_share_data``).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_device, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import ApplianceEvent, Device, TelemetryRecord, User
from app.nilm.classifier import APPLIANCE_LABELS
from app.nilm.profiles import BASELOAD_LABEL
from app.schemas.telemetry import (
    ApplianceStatus,
    ApplianceStatusResponse,
    LedgerResponse,
    TelemetryBatch,
    TelemetryBatchResponse,
    TelemetryPayload,
    TelemetryRecordOut,
    TelemetryResponse,
    local_tz,
)
from app.services_data.ingest import IngestResult, ingest_service, summarize_active
from app.services_data.ledger import check_range, query_ledger, resolve_umkm

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])

_LABEL_TO_CLASS = {label: cls for cls, label in APPLIANCE_LABELS.items()}


def _ensure_same_device(device: Device, device_id: str) -> None:
    if device_id != device.device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="device_id pada data tidak cocok dengan API key perangkat",
        )


def _single_response(res: IngestResult, payload: TelemetryPayload) -> TelemetryResponse:
    if res.processed == 0:
        return TelemetryResponse(
            device_id=res.device_id,
            timestamp=payload.timestamp,
            p_active=payload.p_active,
            detected_event=False,
            duplicate=True,
            message="Sampel dilewati: timestamp tidak lebih baru dari sampel terakhir (duplikat/kiriman ulang)",
        )
    upd = res.last_update
    body = dict(
        device_id=res.device_id,
        timestamp=res.last_ts,
        p_active=payload.p_active,
        detected_event=bool(res.events),
        active_appliances={k: round(v, 1) for k, v in (upd.active if upd else {}).items()},
        baseload_w=round(upd.baseload_w, 1) if upd else 0.0,
        stored=res.last_stored,
        ledger_rows_written=res.ledger_rows_written,
        message="OK – tidak ada transien",
    )
    if res.events:
        ev = res.events[-1]
        body.update(
            event_type=ev["event_type"],
            delta_p=ev["delta_p"],
            appliance_class=ev["appliance_class"],
            appliance_label=ev["appliance_label"],
            confidence=ev["confidence"],
            source=ev["source"],
            message=f"Event {ev['event_type']}: {ev['appliance_label']} (ΔP={ev['delta_p']:+.1f} W, sumber={ev['source']})",
        )
    return TelemetryResponse(**body)


@router.post("/ingest", response_model=TelemetryResponse)
async def ingest_telemetry(
    payload: TelemetryPayload,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
) -> TelemetryResponse:
    """Terima satu sampel dari perangkat, jalankan NILM, simpan, dan perbarui buku energi."""
    _ensure_same_device(device, payload.device_id)
    res = await ingest_service.ingest(db, device, [payload])
    return _single_response(res, payload)


@router.post("/ingest-batch", response_model=TelemetryBatchResponse)
async def ingest_telemetry_batch(
    batch: TelemetryBatch,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
) -> TelemetryBatchResponse:
    """Kirim buffer offline (maks. 500 sampel). Sampel diurutkan menurut waktu di server."""
    _ensure_same_device(device, batch.device_id)
    res = await ingest_service.ingest(db, device, batch.samples)
    ts_sorted = sorted(s.timestamp for s in batch.samples)
    return TelemetryBatchResponse(
        device_id=res.device_id,
        received=res.received,
        processed=res.processed,
        skipped_duplicates=res.duplicates,
        stored_records=res.stored_records,
        events=len(res.events),
        ledger_rows_written=res.ledger_rows_written,
        first_timestamp=ts_sorted[0],
        last_timestamp=ts_sorted[-1],
        message=f"{res.processed} sampel diproses, {res.duplicates} duplikat dilewati",
    )


def _today_local() -> date:
    return datetime.now(local_tz()).date()


@router.get("/ledger", response_model=LedgerResponse)
async def get_ledger(
    umkm_id: Optional[int] = Query(None, description="Wajib untuk selain role umkm"),
    start: Optional[date] = Query(None, description="Tanggal awal (lokal), default 6 hari lalu"),
    end: Optional[date] = Query(None, description="Tanggal akhir (lokal, inklusif), default hari ini"),
    granularity: Literal["hour", "day"] = Query("hour"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LedgerResponse:
    """Buku energi: kWh & Rp per mesin per jam (atau per hari)."""
    umkm = await resolve_umkm(db, user, umkm_id)
    end = end or _today_local()
    start = start or (end - timedelta(days=6))
    check_range(start, end)
    data = await query_ledger(db, umkm.id, start, end, granularity)
    return LedgerResponse(
        umkm_id=umkm.id,
        start=start,
        end=end,
        granularity=granularity,
        tariff_scheme=settings.tariff_scheme,
        tariff_group=umkm.tariff_group,
        note=(
            "Energi per mesin hasil disagregasi NILM (estimasi, bukan meter per mesin). "
            "Hanya jam yang sudah selesai yang tercatat; jam berjalan menyusul. "
            f"Biaya memakai tarif {settings.tariff_scheme} golongan {settings.tariff_group}."
        ),
        **data,
    )


@router.get("/appliances/status", response_model=ApplianceStatusResponse)
async def get_appliance_status(
    umkm_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplianceStatusResponse:
    """Status ON/OFF terakhir per mesin: dari disaggregator live bila ada, selain itu event tersimpan."""
    umkm = await resolve_umkm(db, user, umkm_id)

    # Event terakhir per label.
    sub = (
        select(ApplianceEvent.label, func.max(ApplianceEvent.ts).label("last_ts"))
        .where(ApplianceEvent.umkm_id == umkm.id)
        .group_by(ApplianceEvent.label)
        .subquery()
    )
    result = await db.execute(
        select(ApplianceEvent)
        .join(sub, (ApplianceEvent.label == sub.c.label) & (ApplianceEvent.ts == sub.c.last_ts))
        .where(ApplianceEvent.umkm_id == umkm.id)
        .order_by(ApplianceEvent.id)
    )
    last_event: dict[str, ApplianceEvent] = {}
    for ev in result.scalars():
        last_event[ev.label] = ev  # id terbesar menang bila ts sama

    live_states = ingest_service.live_states_for_umkm(umkm.id)
    live = bool(live_states)
    active = summarize_active(live_states) if live else {}

    out: list[ApplianceStatus] = []
    labels = sorted(set(last_event) | {k for k in active if k != BASELOAD_LABEL})
    for label in labels:
        ev = last_event.get(label)
        cls = ev.appliance_class if ev is not None else _LABEL_TO_CLASS.get(label, -1)
        if live:
            watt = active.get(label, (0.0, None))[0]
            out.append(
                ApplianceStatus(
                    appliance_class=cls,
                    label=label,
                    state="ON" if watt > 0 else "OFF",
                    p_estimate_w=round(watt, 1),
                    last_seen=ev.ts if ev is not None else None,
                    source="live",
                )
            )
        elif ev is not None:
            out.append(
                ApplianceStatus(
                    appliance_class=cls,
                    label=label,
                    state="ON" if ev.event_type == "ON" else "OFF",
                    p_estimate_w=round(abs(ev.delta_p), 1) if ev.event_type == "ON" else 0.0,
                    last_seen=ev.ts,
                    source="event",
                )
            )
    return ApplianceStatusResponse(
        umkm_id=umkm.id, generated_at=datetime.now(timezone.utc), live=live, appliances=out
    )


@router.get("/records", response_model=list[TelemetryRecordOut])
async def get_records(
    umkm_id: Optional[int] = Query(None),
    device_id: Optional[str] = Query(None),
    minutes: int = Query(60, ge=1, le=60 * 24 * 7, description="Rentang ke belakang dari sekarang"),
    limit: int = Query(1000, ge=1, le=10000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TelemetryRecordOut]:
    """Sampel mentah tersimpan (sudah di-downsample) untuk grafik daya."""
    umkm = await resolve_umkm(db, user, umkm_id)
    dev_ids = (await db.execute(select(Device.device_id).where(Device.umkm_id == umkm.id))).scalars().all()
    if device_id is not None:
        if device_id not in dev_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perangkat tidak ditemukan di UMKM ini")
        dev_ids = [device_id]
    if not dev_ids:
        return []
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    result = await db.execute(
        select(TelemetryRecord)
        .where(TelemetryRecord.device_id.in_(dev_ids), TelemetryRecord.ts >= since)
        .order_by(TelemetryRecord.ts.desc())
        .limit(limit)
    )
    rows = list(result.scalars())[::-1]
    return [
        TelemetryRecordOut(
            device_id=r.device_id, ts=r.ts, v_rms=r.v_rms, i_rms=r.i_rms,
            p_active=r.p_active, q_reactive=r.q_reactive, frequency=r.frequency,
        )
        for r in rows
    ]

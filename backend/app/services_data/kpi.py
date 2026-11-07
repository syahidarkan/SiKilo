"""
Metrik papan indikator (KPI board) WASKITA.

Setiap metrik selalu menyertakan ``source`` (dari mana angkanya) dan
``status``:
- ``ok`` / ``di_bawah_target`` — ada data dan dibandingkan dengan target;
- ``info``          — ada data, tanpa target;
- ``belum_ada_data`` — file evaluasi tidak ada / kosong / rusak, atau belum ada baris DB.

Angka dari data sintetis tetap ditampilkan TETAPI ``validation`` menyatakan
"belum divalidasi" sesuai isi file evaluasinya.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import DailyPlan, Device

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
NOT_VALIDATED = "belum divalidasi"


def resolve_path(raw: str) -> Path:
    """Path relatif dicari di direktori kerja dulu, lalu di folder backend."""
    p = Path(raw)
    if p.is_absolute():
        return p
    cwd_path = Path.cwd() / p
    return cwd_path if cwd_path.exists() else BACKEND_DIR / p


def load_json(raw_path: str) -> tuple[Optional[dict[str, Any]], str]:
    """(isi, keterangan). isi None bila file tidak ada / kosong / rusak."""
    path = resolve_path(raw_path)
    if not path.exists():
        return None, f"file {raw_path} tidak ditemukan"
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None, f"file {raw_path} kosong"
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        return None, f"file {raw_path} tidak dapat dibaca ({type(exc).__name__})"
    if not isinstance(data, dict) or not data:
        return None, f"file {raw_path} kosong"
    return data, f"file {raw_path}"


def _metric(
    key: str,
    name: str,
    *,
    value: Optional[float] = None,
    unit: str = "",
    target: Optional[float] = None,
    higher_is_better: bool = True,
    source: str,
    validation: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    updated_at: Optional[str] = None,
) -> dict[str, Any]:
    if value is None:
        status = "belum_ada_data"
    elif target is None:
        status = "info"
    else:
        ok = value >= target if higher_is_better else value <= target
        status = "ok" if ok else "di_bawah_target"
    return {
        "key": key,
        "name": name,
        "value": None if value is None else round(float(value), 2),
        "unit": unit,
        "target": target,
        "target_direction": "min" if higher_is_better else "max",
        "status": status,
        "source": source,
        "validation": validation,
        "detail": detail or {},
        "updated_at": updated_at,
    }


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


# ── Metrik dari file evaluasi ───────────────────────────────────────────────
def nilm_accuracy_metric(path: Optional[str] = None) -> dict[str, Any]:
    path = path or settings.nilm_metrics_path
    data, src = load_json(path)
    if data is None:
        return _metric("nilm_accuracy", "Akurasi energi NILM per mesin", unit="%", source=src,
                       validation=NOT_VALIDATED,
                       detail={"cara": "jalankan scripts/evaluate_nilm.py dengan data smart plug"})
    overall = data.get("overall") or {}
    acc = _num(overall.get("energy_estimated_accuracy"))
    threshold = _num((data.get("target") or {}).get("threshold"))
    data_source = data.get("data_source", "tidak diketahui")
    validation = data.get("validation_status") or (
        NOT_VALIDATED if data_source != "field" else "data lapangan"
    )
    return _metric(
        "nilm_accuracy",
        "Akurasi energi NILM per mesin",
        value=None if acc is None else acc * 100.0,
        unit="%",
        target=None if threshold is None else threshold * 100.0,
        source=f"{src} (data: {data_source})",
        validation=validation,
        detail={
            "macro_f1_appliances": _num(overall.get("macro_f1_appliances")),
            "event_accuracy": _num(overall.get("event_accuracy")),
            "detection_recall": _num(overall.get("detection_recall")),
            "n_appliances_meeting_target": overall.get("n_appliances_meeting_80pct_energy"),
            "n_appliances": overall.get("n_appliances"),
            "n_days": (data.get("inputs") or {}).get("n_days"),
            "classifier": (data.get("classifier") or {}).get("source"),
        },
        updated_at=data.get("generated_at"),
    )


def twin_bill_error_metric(path: Optional[str] = None) -> dict[str, Any]:
    path = path or settings.twin_validation_path
    data, src = load_json(path)
    if data is None:
        return _metric("twin_bill_error", "Selisih tagihan simulator vs nyata", unit="%",
                       higher_is_better=False, source=src, validation=NOT_VALIDATED,
                       detail={"cara": "jalankan scripts/validate_twin.py dengan tagihan PLN / data meter"})
    err = _num(data.get("bill_error_pct"))
    target = _num(data.get("target_bill_error_pct"))
    data_source = data.get("source", "tidak diketahui")
    validation = data.get("catatan") or (NOT_VALIDATED if data_source in ("example", "synthetic") else None)
    return _metric(
        "twin_bill_error",
        "Selisih tagihan simulator vs nyata",
        value=None if err is None else abs(err),
        unit="%",
        target=target if target is not None else 10.0,
        higher_is_better=False,
        source=f"{src} (data: {data_source})",
        validation=validation,
        detail={
            "energy_error_pct": _num(data.get("energy_error_pct")),
            "n_days": data.get("n_days"),
            "profile": data.get("profile"),
        },
        updated_at=data.get("generated_at"),
    )


# ── Metrik dari database ────────────────────────────────────────────────────
async def latest_plans(
    db: AsyncSession, umkm_ids: Optional[Sequence[int]], start: date, end: date
) -> list[DailyPlan]:
    """Rencana terakhir per (UMKM, hari) dalam rentang tanggal."""
    stmt = select(DailyPlan).where(DailyPlan.day >= start, DailyPlan.day <= end)
    if umkm_ids is not None:
        if not umkm_ids:
            return []
        stmt = stmt.where(DailyPlan.umkm_id.in_(list(umkm_ids)))
    result = await db.execute(stmt.order_by(DailyPlan.created_at, DailyPlan.id))
    latest: dict[tuple[int, date], DailyPlan] = {}
    for plan in result.scalars():
        latest[(plan.umkm_id, plan.day)] = plan
    return list(latest.values())


def plan_metrics(plans: Sequence[DailyPlan], period: str) -> list[dict[str, Any]]:
    src = f"tabel DailyPlan ({period}; rencana terakhir per UMKM per hari)"
    n = len(plans)
    savings = _metric(
        "avg_savings_pct",
        "Rata-rata penghematan rencana agen vs kebiasaan lama",
        value=(sum(p.savings_pct for p in plans) / n) if n else None,
        unit="%",
        source=src,
        validation="estimasi tiruan digital, bukan penghematan terukur di meter",
        detail={
            "n_plans": n,
            "n_umkm": len({p.umkm_id for p in plans}),
            "total_savings_idr": round(sum(p.savings_idr for p in plans), 0) if n else None,
        },
    )
    on_time = _metric(
        "orders_on_time_pct",
        "Pesanan tepat waktu (semua tenggat mesin terpenuhi)",
        value=(100.0 * sum(1 for p in plans if p.deadlines_met) / n) if n else None,
        unit="%",
        target=95.0,
        source=src,
        validation="dari rencana agen; belum dicocokkan dengan catatan produksi nyata",
        detail={"n_plans": n, "n_deadlines_met": sum(1 for p in plans if p.deadlines_met)},
    )
    return [savings, on_time]


async def devices_metric(db: AsyncSession, umkm_ids: Optional[Sequence[int]]) -> dict[str, Any]:
    window = settings.device_online_window_s
    since = datetime.now(timezone.utc) - timedelta(seconds=window)
    total_stmt = select(func.count(Device.id))
    online_stmt = select(func.count(Device.id)).where(Device.last_seen.is_not(None), Device.last_seen >= since)
    if umkm_ids is not None:
        ids = list(umkm_ids) or [-1]
        total_stmt = total_stmt.where(Device.umkm_id.in_(ids))
        online_stmt = online_stmt.where(Device.umkm_id.in_(ids))
    total = int(await db.scalar(total_stmt) or 0)
    online = int(await db.scalar(online_stmt) or 0)
    return _metric(
        "devices_online",
        "Perangkat ukur online",
        value=float(online) if total else None,
        unit="perangkat",
        source=f"tabel Device (last_seen ≤ {window} detik lalu)",
        detail={"online": online, "total": total, "online_window_s": window},
    )

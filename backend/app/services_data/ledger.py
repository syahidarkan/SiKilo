"""
Buku energi per mesin per jam (EnergyLedger) + aturan akses data UMKM.

- ``upsert_ledger`` MENAMBAHKAN kWh & Rp ke baris (umkm, hari, jam, label)
  secara atomik (``INSERT … ON CONFLICT DO UPDATE``) sehingga beberapa
  perangkat di satu UMKM dan data terlambat tetap terjumlah benar.
- Biaya = kWh × ``tariff_idr_per_kwh(jam)`` dari ``app.core.tariff``.
- Hari & jam di ledger adalah waktu LOKAL (settings.site_timezone).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tariff import tariff_idr_per_kwh
from app.models import UMKM, EnergyLedger, Lead, Role, User
from app.nilm.disaggregator import HourlyEnergy
from app.nilm.profiles import BASELOAD_LABEL

# Pihak ketiga yang boleh membaca data energi rinci (per jam / per mesin /
# sampel mentah) UMKM yang memberi ``consent_share_data``. Disperinaker TIDAK
# termasuk: dinas hanya melihat ringkasan agregat lewat /dashboard/disperinaker
# dan hanya untuk UMKM yang memberi ``consent_share_gov``.
SHARE_ROLES: tuple[str, ...] = (Role.INSTALLER.value, Role.BANK.value)


async def installer_umkm_ids(db: AsyncSession, user: User) -> set[int]:
    """UMKM yang ditangani installer ini (lead ditugaskan/diambil, status bukan 'lost')."""
    result = await db.execute(
        select(Lead.umkm_id).where(Lead.installer_user_id == user.id, Lead.status != "lost")
    )
    return {int(x) for x in result.scalars().all()}


async def ensure_installer_assigned(db: AsyncSession, user: User, umkm_id: int) -> None:
    """403 bila ``user`` installer tetapi tidak ditugaskan ke UMKM ini. Admin selalu lolos."""
    if user.role == Role.ADMIN.value:
        return
    if user.role != Role.INSTALLER.value or umkm_id not in await installer_umkm_ids(db, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Installer hanya dapat mengelola UMKM yang rujukannya ditugaskan kepadanya",
        )


# ── Akses ───────────────────────────────────────────────────────────────────
async def resolve_umkm(
    db: AsyncSession,
    user: User,
    umkm_id: Optional[int],
    share_roles: Iterable[str] = SHARE_ROLES,
) -> UMKM:
    """
    UMKM yang boleh dibaca ``user``:
    - role ``umkm``: hanya miliknya (umkm_id boleh kosong → miliknya).
    - ``admin``: UMKM mana pun (umkm_id wajib).
    - role di ``share_roles``: hanya UMKM yang ``consent_share_data`` = True.
    """
    if user.role == Role.UMKM.value:
        if user.umkm_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Akun ini belum terhubung ke UMKM")
        if umkm_id is not None and umkm_id != user.umkm_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki akses ke UMKM ini")
        umkm_id = user.umkm_id
    elif user.role != Role.ADMIN.value and user.role not in set(share_roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Anda tidak memiliki akses ke fitur ini")
    if umkm_id is None:
        raise HTTPException(422, "Parameter umkm_id wajib diisi")
    umkm = await db.get(UMKM, umkm_id)
    if umkm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "UMKM tidak ditemukan")
    if user.role in set(share_roles) and user.role not in (Role.UMKM.value, Role.ADMIN.value):
        if not umkm.consent_share_data:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "UMKM ini belum memberi persetujuan berbagi data"
            )
    return umkm


def check_range(start: date, end: date, max_days: int = 366) -> None:
    if end < start:
        raise HTTPException(422, "Tanggal akhir harus ≥ tanggal awal")
    if (end - start).days + 1 > max_days:
        raise HTTPException(422, f"Rentang maksimal {max_days} hari")


# ── Tulis ───────────────────────────────────────────────────────────────────
def aggregate_entries(entries: Iterable[HourlyEnergy]) -> dict[tuple[date, int, str], float]:
    """
    Jumlahkan energi per (hari, jam, label). Baris 0 kWh untuk label beban
    dasar TETAP ditulis sebagai penanda cakupan data: jam tanpa konsumsi
    (mis. listrik dimatikan malam hari) tetap dihitung "tercatat" sehingga
    hari itu bisa lengkap untuk sizing/rapor.
    """
    out: dict[tuple[date, int, str], float] = defaultdict(float)
    for e in entries:
        label = e.appliance_label[:80]
        if e.kwh < 0 or (e.kwh == 0 and label != BASELOAD_LABEL):
            continue
        out[(e.day, int(e.hour), label)] += max(float(e.kwh), 0.0)
    return dict(out)


async def upsert_ledger(db: AsyncSession, umkm_id: int, entries: Iterable[HourlyEnergy]) -> int:
    """Tambahkan energi ke ledger. Tidak commit. Return jumlah baris (kunci) yang disentuh."""
    agg = aggregate_entries(entries)
    if not agg:
        return 0
    dialect = db.bind.dialect.name if db.bind is not None else ""
    rows = [
        {
            "umkm_id": umkm_id,
            "day": day,
            "hour": hour,
            "appliance_label": label,
            "kwh": kwh,
            "cost_idr": kwh * tariff_idr_per_kwh(hour),
        }
        for (day, hour, label), kwh in sorted(agg.items())
    ]
    if dialect in ("sqlite", "postgresql"):
        if dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        for row in rows:
            stmt = dialect_insert(EnergyLedger).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["umkm_id", "day", "hour", "appliance_label"],
                set_={
                    "kwh": EnergyLedger.kwh + stmt.excluded.kwh,
                    "cost_idr": EnergyLedger.cost_idr + stmt.excluded.cost_idr,
                },
            )
            await db.execute(stmt)
        return len(rows)

    # Dialek lain: baca-lalu-tulis (tidak atomik antarproses).
    for row in rows:
        existing = await db.scalar(
            select(EnergyLedger).where(
                EnergyLedger.umkm_id == umkm_id,
                EnergyLedger.day == row["day"],
                EnergyLedger.hour == row["hour"],
                EnergyLedger.appliance_label == row["appliance_label"],
            )
        )
        if existing is None:
            db.add(EnergyLedger(**row))
        else:
            existing.kwh += row["kwh"]
            existing.cost_idr += row["cost_idr"]
    return len(rows)


# ── Baca ────────────────────────────────────────────────────────────────────
async def query_ledger(
    db: AsyncSession, umkm_id: int, start: date, end: date, granularity: str = "hour"
) -> dict[str, Any]:
    result = await db.execute(
        select(EnergyLedger)
        .where(EnergyLedger.umkm_id == umkm_id, EnergyLedger.day >= start, EnergyLedger.day <= end)
        .order_by(EnergyLedger.day, EnergyLedger.hour, EnergyLedger.appliance_label)
    )
    entries = result.scalars().all()

    per_label: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    rows: list[dict[str, Any]]
    if granularity == "day":
        by_day: dict[tuple[date, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for e in entries:
            acc = by_day[(e.day, e.appliance_label)]
            acc[0] += e.kwh
            acc[1] += e.cost_idr
        rows = [
            {"day": d, "hour": None, "appliance_label": label, "kwh": round(v[0], 4), "cost_idr": round(v[1], 2)}
            for (d, label), v in sorted(by_day.items())
        ]
    else:
        rows = [
            {
                "day": e.day,
                "hour": e.hour,
                "appliance_label": e.appliance_label,
                "kwh": round(e.kwh, 4),
                "cost_idr": round(e.cost_idr, 2),
            }
            for e in entries
        ]
    for e in entries:
        acc = per_label[e.appliance_label]
        acc[0] += e.kwh
        acc[1] += e.cost_idr
    total_kwh = sum(v[0] for v in per_label.values())
    total_cost = sum(v[1] for v in per_label.values())
    per_appliance = sorted(
        (
            {
                "appliance_label": label,
                "kwh": round(v[0], 4),
                "cost_idr": round(v[1], 2),
                "share_pct": round(100.0 * v[0] / total_kwh, 2) if total_kwh > 0 else 0.0,
            }
            for label, v in per_label.items()
        ),
        key=lambda r: -r["kwh"],
    )
    return {
        "rows": rows,
        "per_appliance": per_appliance,
        "total_kwh": round(total_kwh, 4),
        "total_cost_idr": round(total_cost, 2),
    }


async def totals_by_umkm(
    db: AsyncSession, umkm_ids: Sequence[int], start: date, end: date
) -> dict[int, dict[str, float]]:
    """{umkm_id: {"kwh", "cost_idr", "days"}} untuk rentang tanggal."""
    if not umkm_ids:
        return {}
    result = await db.execute(
        select(
            EnergyLedger.umkm_id,
            func.sum(EnergyLedger.kwh),
            func.sum(EnergyLedger.cost_idr),
            func.count(func.distinct(EnergyLedger.day)),
        )
        .where(EnergyLedger.umkm_id.in_(list(umkm_ids)), EnergyLedger.day >= start, EnergyLedger.day <= end)
        .group_by(EnergyLedger.umkm_id)
    )
    return {
        int(uid): {"kwh": float(kwh or 0.0), "cost_idr": float(cost or 0.0), "days": int(days or 0)}
        for uid, kwh, cost, days in result.all()
    }


async def top_appliances(
    db: AsyncSession, umkm_id: int, start: date, end: date, limit: int = 5
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(EnergyLedger.appliance_label, func.sum(EnergyLedger.kwh), func.sum(EnergyLedger.cost_idr))
        .where(EnergyLedger.umkm_id == umkm_id, EnergyLedger.day >= start, EnergyLedger.day <= end)
        .group_by(EnergyLedger.appliance_label)
        .order_by(func.sum(EnergyLedger.kwh).desc())
        .limit(limit)
    )
    return [
        {"appliance_label": label, "kwh": round(float(kwh or 0), 4), "cost_idr": round(float(cost or 0), 2)}
        for label, kwh, cost in result.all()
    ]


async def hourly_profiles(
    db: AsyncSession, umkm_id: int, start: date, end: date, min_hours: int = 20
) -> list[tuple[date, list[float]]]:
    """Profil kWh per jam (24 nilai) untuk hari yang tercatat ≥ ``min_hours`` jam."""
    result = await db.execute(
        select(EnergyLedger.day, EnergyLedger.hour, func.sum(EnergyLedger.kwh))
        .where(EnergyLedger.umkm_id == umkm_id, EnergyLedger.day >= start, EnergyLedger.day <= end)
        .group_by(EnergyLedger.day, EnergyLedger.hour)
    )
    days: dict[date, list[float]] = {}
    seen: dict[date, int] = defaultdict(int)
    for d, hour, kwh in result.all():
        prof = days.setdefault(d, [0.0] * 24)
        if 0 <= int(hour) < 24:
            prof[int(hour)] += float(kwh or 0.0)
            seen[d] += 1
    return [(d, prof) for d, prof in sorted(days.items()) if seen[d] >= min_hours]

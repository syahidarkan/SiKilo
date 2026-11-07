from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base
from app.models.types import BigIntPK, UTCDateTime, utcnow


class EnergyLedger(Base):
    """Buku besar energi per jam per peralatan (hasil disagregasi NILM)."""

    __tablename__ = "energy_ledger"
    __table_args__ = (
        UniqueConstraint("umkm_id", "day", "hour", "appliance_label", name="uq_energy_ledger_slot"),
        Index("ix_energy_ledger_umkm_day", "umkm_id", "day"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    hour: Mapped[int] = mapped_column(Integer)  # 0–23
    appliance_label: Mapped[str] = mapped_column(String(80))
    kwh: Mapped[float] = mapped_column(Float, default=0.0)
    cost_idr: Mapped[float] = mapped_column(Float, default=0.0)


class MachineProfile(Base):
    """Profil mesin UMKM yang dipakai agen penjadwal (padanan MachineJob)."""

    __tablename__ = "machine_profiles"
    __table_args__ = (UniqueConstraint("umkm_id", "machine_id", name="uq_machine_profile_umkm_machine"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"), index=True)
    machine_id: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(80))
    appliance_class: Mapped[int] = mapped_column(Integer)
    power_w: Mapped[float] = mapped_column(Float)
    daily_runtime_minutes: Mapped[int] = mapped_column(Integer)
    earliest_hour: Mapped[int] = mapped_column(Integer, default=lambda: settings.work_start_hour)
    deadline_hour: Mapped[int] = mapped_column(Integer, default=lambda: settings.work_end_hour)
    habit_start_hour: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_flexible: Mapped[bool] = mapped_column(Boolean, default=True)
    min_continuous_minutes: Mapped[int] = mapped_column(Integer, default=15)


class DailyPlan(Base):
    """Rencana jadwal harian yang dihasilkan agen (boleh lebih dari satu per hari)."""

    __tablename__ = "daily_plans"
    __table_args__ = (Index("ix_daily_plans_umkm_day", "umkm_id", "day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    solver: Mapped[str] = mapped_column(String(32))
    cost_idr: Mapped[float] = mapped_column(Float)
    baseline_cost_idr: Mapped[float] = mapped_column(Float)
    savings_idr: Mapped[float] = mapped_column(Float)
    savings_pct: Mapped[float] = mapped_column(Float)
    deadlines_met: Mapped[bool] = mapped_column(Boolean, default=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

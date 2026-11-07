from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import BigIntPK, UTCDateTime


class TelemetryRecord(Base):
    """Sampel mentah telemetri (disimpan jarang, lihat settings.telemetry_raw_keep_every_s)."""

    __tablename__ = "telemetry_records"
    __table_args__ = (Index("ix_telemetry_device_ts", "device_id", "ts"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE", onupdate="CASCADE")
    )
    ts: Mapped[datetime] = mapped_column(UTCDateTime())
    v_rms: Mapped[float] = mapped_column(Float)
    i_rms: Mapped[float] = mapped_column(Float)
    p_active: Mapped[float] = mapped_column(Float)
    q_reactive: Mapped[float] = mapped_column(Float)
    frequency: Mapped[float] = mapped_column(Float)


class ApplianceEvent(Base):
    """Kejadian ON/OFF peralatan hasil NILM."""

    __tablename__ = "appliance_events"
    __table_args__ = (Index("ix_appliance_events_umkm_ts", "umkm_id", "ts"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"))
    device_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        index=True,
    )
    ts: Mapped[datetime] = mapped_column(UTCDateTime())
    event_type: Mapped[str] = mapped_column(String(8))  # "ON" | "OFF"
    appliance_class: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(80))
    delta_p: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(32))  # mis. "lgbm" | "rule"

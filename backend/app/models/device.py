from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UTCDateTime, utcnow


class Device(Base):
    """Perangkat ukur (ESP32) yang terpasang di satu UMKM."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"), index=True)
    # SHA-256 hex dari API key; key asli hanya ditampilkan sekali.
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Device {self.device_id} umkm={self.umkm_id}>"

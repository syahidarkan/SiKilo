from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UTCDateTime, utcnow

LEAD_STATUSES = ("new", "contacted", "surveyed", "installed", "lost")


class Lead(Base):
    """Prospek pemasangan PLTS untuk installer."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"), index=True)
    installer_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    recommended_kwp: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # True bila lead DIAJUKAN pemilik UMKM sendiri (bukan dibuat admin);
    # menentukan apakah kontak boleh dibagikan ke installer.
    requested_by_umkm: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)

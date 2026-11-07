from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UTCDateTime, utcnow

MESSAGE_KINDS = ("daily", "weekly")
MESSAGE_STATUSES = ("sent", "failed", "skipped")


class MessageLog(Base):
    """Log pesan WhatsApp yang dikirim (atau gagal/dilewati) ke UMKM."""

    __tablename__ = "message_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    umkm_id: Mapped[int] = mapped_column(ForeignKey("umkm.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # daily | weekly
    provider: Mapped[str] = mapped_column(String(16))  # none | fonnte | meta
    status: Mapped[str] = mapped_column(String(16))  # sent | failed | skipped
    body: Mapped[str] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

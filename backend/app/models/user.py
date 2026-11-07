from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.umkm import UMKM


class Role(StrEnum):
    UMKM = "umkm"
    DISPERINAKER = "disperinaker"
    INSTALLER = "installer"
    BANK = "bank"
    ADMIN = "admin"


ROLES: tuple[str, ...] = tuple(r.value for r in Role)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(128), default="")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), index=True, default=Role.UMKM.value)
    umkm_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("umkm.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    # Dimuat eager (selectin) agar aman diakses di konteks async.
    umkm: Mapped[Optional["UMKM"]] = relationship(lazy="selectin")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} role={self.role}>"

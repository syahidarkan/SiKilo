from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.core.database import Base
from app.models.types import UTCDateTime, utcnow


class UMKM(Base):
    __tablename__ = "umkm"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    umkm_type: Mapped[str] = mapped_column(String(80), default="UMKM Umum")
    address: Mapped[str] = mapped_column(String(255), default="")
    kecamatan: Mapped[str] = mapped_column(String(80), default="", index=True)
    # Nomor WhatsApp dinormalisasi ke format 62xxxxxxxxxx.
    phone_whatsapp: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Daya tersambung PLN (VA), mis. 2200, 5500, 23000.
    connected_power_va: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tariff_group: Mapped[str] = mapped_column(String(16), default=lambda: settings.tariff_group)
    pv_kwp: Mapped[float] = mapped_column(Float, default=0.0)
    battery_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    # Persetujuan eksplisit pemilik agar data energinya boleh dilihat pihak
    # ketiga (bank/installer). Default False.
    consent_share_data: Mapped[bool] = mapped_column(Boolean, default=False)
    # Persetujuan terpisah agar nama & data energi agregat UMKM tampil ke
    # Disperinaker (pemerintah). Default False.
    consent_share_gov: Mapped[bool] = mapped_column(Boolean, default=False)
    # Waktu terakhir persetujuan berubah (jejak audit UU PDP).
    consent_updated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    # Nomor WA hanya dipakai mengirim setelah diverifikasi dengan kode OTP.
    phone_verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    phone_otp_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    phone_otp_expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    phone_otp_sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    phone_otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Pemilik berhenti berlangganan pesan WhatsApp terjadwal.
    whatsapp_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UMKM {self.id} {self.name!r}>"

"""
Skema profil UMKM & profil mesin (``/api/v1/umkm``).

Profil mesin adalah padanan ``MachineJob`` yang disimpan di basis data dan
dipakai agen penjadwal untuk brief WhatsApp harian, ``DailyPlan``, dan
perbandingan kWp di rapor.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.config import settings
from app.schemas.auth import CONSENT_SHARE_DATA_TEXT, CONSENT_SHARE_GOV_TEXT, normalize_whatsapp

_MACHINE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class UMKMUpdate(BaseModel):
    """
    Perubahan profil UMKM. Field yang tidak dikirim tidak diubah.

    - Pemilik (role umkm) & admin: semua field.
    - Installer yang ditugaskan (lead aktif): hanya ``pv_kwp``, ``battery_kwh``,
      ``connected_power_va`` (data teknis hasil survei/pemasangan).
    Mengganti ``phone_whatsapp`` membatalkan verifikasi nomor (perlu OTP lagi).
    """

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=2, max_length=160)
    umkm_type: Optional[str] = Field(None, max_length=80)
    address: Optional[str] = Field(None, max_length=255)
    kecamatan: Optional[str] = Field(None, max_length=80)
    phone_whatsapp: Optional[str] = Field(None, description="Kosongkan ('') untuk menghapus nomor")
    connected_power_va: Optional[int] = Field(None, gt=0, le=10_000_000)
    pv_kwp: Optional[float] = Field(None, ge=0, le=1000)
    battery_kwh: Optional[float] = Field(None, ge=0, le=1000)
    consent_share_data: Optional[bool] = Field(None, description=CONSENT_SHARE_DATA_TEXT)
    consent_share_gov: Optional[bool] = Field(None, description=CONSENT_SHARE_GOV_TEXT)
    whatsapp_opt_out: Optional[bool] = Field(None, description="True = berhenti menerima pesan WhatsApp terjadwal")

    @field_validator("phone_whatsapp")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not v.strip():
            return ""
        return normalize_whatsapp(v)


TECH_FIELDS = frozenset({"pv_kwp", "battery_kwh", "connected_power_va"})


class PhoneVerifyRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")


class MachineProfileBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)
    appliance_class: int = Field(default=0, ge=0, le=1000)
    power_w: float = Field(..., gt=0, le=100_000, description="Daya nominal saat bekerja (Watt)")
    daily_runtime_minutes: int = Field(..., ge=0, le=1440)
    earliest_hour: int = Field(default_factory=lambda: settings.work_start_hour, ge=0, le=23)
    deadline_hour: int = Field(default_factory=lambda: settings.work_end_hour, ge=1, le=24)
    habit_start_hour: Optional[int] = Field(None, ge=0, le=23)
    is_flexible: bool = True
    min_continuous_minutes: int = Field(default=15, ge=15, le=1440)
    idle_minutes_habit: int = Field(
        default=0, ge=0, le=1440, description="Menit mesin dibiarkan menyala tanpa beban per hari (kebiasaan lama)"
    )
    idle_power_w: Optional[float] = Field(
        None, ge=0, le=100_000, description="Daya idle (kosong = default_idle_power_frac × power_w; asumsi)"
    )
    cooldown_minutes: Optional[int] = Field(None, ge=0, le=240)

    @model_validator(mode="after")
    def _check_window(self) -> "MachineProfileBase":
        if self.deadline_hour <= self.earliest_hour:
            raise ValueError("deadline_hour harus lebih besar dari earliest_hour")
        window = (self.deadline_hour - self.earliest_hour) * 60
        if self.daily_runtime_minutes > window:
            raise ValueError(f"runtime {self.daily_runtime_minutes} menit melebihi jendela kerja ({window} menit)")
        return self


class MachineProfileCreate(MachineProfileBase):
    machine_id: str = Field(..., description="ID unik per UMKM (huruf, angka, titik, garis bawah, strip)")

    @field_validator("machine_id")
    @classmethod
    def _mid(cls, v: str) -> str:
        v = v.strip()
        if not _MACHINE_ID_RE.match(v):
            raise ValueError("machine_id 1–64 karakter: huruf, angka, titik, garis bawah, strip")
        return v


class MachineProfileUpdate(BaseModel):
    """Perubahan sebagian; validasi jendela kerja dilakukan pada hasil gabungan."""

    model_config = ConfigDict(extra="forbid")

    label: Optional[str] = Field(None, min_length=1, max_length=80)
    appliance_class: Optional[int] = Field(None, ge=0, le=1000)
    power_w: Optional[float] = Field(None, gt=0, le=100_000)
    daily_runtime_minutes: Optional[int] = Field(None, ge=0, le=1440)
    earliest_hour: Optional[int] = Field(None, ge=0, le=23)
    deadline_hour: Optional[int] = Field(None, ge=1, le=24)
    habit_start_hour: Optional[int] = Field(None, ge=0, le=23)
    is_flexible: Optional[bool] = None
    min_continuous_minutes: Optional[int] = Field(None, ge=15, le=1440)
    idle_minutes_habit: Optional[int] = Field(None, ge=0, le=1440)
    idle_power_w: Optional[float] = Field(None, ge=0, le=100_000)
    cooldown_minutes: Optional[int] = Field(None, ge=0, le=240)


class MachineProfileOut(MachineProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    umkm_id: int
    machine_id: str

    @model_validator(mode="after")
    def _check_window(self) -> "MachineProfileOut":  # data lama boleh tampil apa adanya
        return self


class MachineSuggestion(BaseModel):
    machine_id: str
    label: str
    appliance_class: int
    power_w: float
    daily_runtime_minutes: int
    habit_start_hour: Optional[int]
    idle_minutes_habit: int
    days_with_data: int
    already_profiled: bool
    basis: str


class MachineSuggestionResponse(BaseModel):
    umkm_id: int
    start: str
    end: str
    suggestions: list[MachineSuggestion]
    note: str


class PhoneOTPResponse(BaseModel):
    status: str
    provider: str
    expires_at: Optional[datetime] = None
    detail: str
    # Hanya di luar production DAN bila WHATSAPP_PROVIDER=none (tidak ada saluran kirim).
    dev_code: Optional[str] = None

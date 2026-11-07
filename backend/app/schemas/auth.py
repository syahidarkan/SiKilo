from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.auth import BCRYPT_MAX_BYTES, PASSWORD_MIN_LENGTH, password_problem

RoleName = Literal["umkm", "disperinaker", "installer", "bank", "admin"]

_USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,64}$")
_PHONE_RE = re.compile(r"^62\d{8,13}$")


def normalize_whatsapp(value: Optional[str]) -> Optional[str]:
    """Normalisasi nomor WA Indonesia ke format 62xxxxxxxxxx."""
    if value is None:
        return None
    digits = re.sub(r"[\s\-().]", "", value)
    if not digits:
        return None
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not _PHONE_RE.match(digits):
        raise ValueError("Nomor WhatsApp tidak valid (contoh: 081234567890 atau +6281234567890)")
    return digits


class _PasswordMixin(BaseModel):
    password: str = Field(
        ...,
        description=f"Minimal {PASSWORD_MIN_LENGTH} karakter, maksimal {BCRYPT_MAX_BYTES} byte UTF-8.",
    )

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        problem = password_problem(v)
        if problem:
            raise ValueError(problem)
        return v


class _UsernameMixin(BaseModel):
    username: str = Field(..., description="3–64 karakter: huruf kecil, angka, titik, garis bawah, strip.")

    @field_validator("username")
    @classmethod
    def _check_username(cls, v: str) -> str:
        v = v.strip().lower()
        if not _USERNAME_RE.match(v):
            raise ValueError("Username 3–64 karakter, hanya huruf, angka, titik, garis bawah, atau strip")
        return v


class UMKMCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160, examples=["Konveksi Bu Sari"])
    umkm_type: str = Field("UMKM Umum", max_length=80, examples=["Konveksi & Laundry"])
    address: str = Field("", max_length=255)
    kecamatan: str = Field("", max_length=80, examples=["Grogol"])
    phone_whatsapp: Optional[str] = Field(None, examples=["081234567890"])
    connected_power_va: Optional[int] = Field(None, gt=0, le=10_000_000, examples=[5500])
    consent_share_data: bool = Field(
        False, description="Setuju data energi dibagikan ke bank/installer mitra untuk penawaran PLTS & kredit hijau."
    )

    @field_validator("phone_whatsapp")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_whatsapp(v)


class RegisterRequest(_UsernameMixin, _PasswordMixin):
    """Pendaftaran publik: selalu membuat user role ``umkm`` + record UMKM."""

    full_name: str = Field(..., min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    umkm_name: str = Field(..., min_length=2, max_length=160)
    umkm_type: str = Field("UMKM Umum", max_length=80)
    address: str = Field("", max_length=255)
    kecamatan: str = Field("", max_length=80)
    phone_whatsapp: Optional[str] = None
    connected_power_va: Optional[int] = Field(None, gt=0, le=10_000_000)
    consent_share_data: bool = False

    @field_validator("phone_whatsapp")
    @classmethod
    def _phone(cls, v: Optional[str]) -> Optional[str]:
        return normalize_whatsapp(v)

    def to_umkm(self) -> UMKMCreate:
        return UMKMCreate(
            name=self.umkm_name,
            umkm_type=self.umkm_type,
            address=self.address,
            kecamatan=self.kecamatan,
            phone_whatsapp=self.phone_whatsapp,
            connected_power_va=self.connected_power_va,
            consent_share_data=self.consent_share_data,
        )


class AdminUserCreate(_UsernameMixin, _PasswordMixin):
    """Pembuatan user oleh admin (semua role)."""

    full_name: str = Field(..., min_length=1, max_length=128)
    email: Optional[EmailStr] = None
    role: RoleName
    umkm_id: Optional[int] = Field(None, description="Untuk role umkm: tautkan ke UMKM yang sudah ada.")
    umkm: Optional[UMKMCreate] = Field(None, description="Untuk role umkm: buat UMKM baru.")

    @model_validator(mode="after")
    def _check_umkm(self) -> "AdminUserCreate":
        if self.role == "umkm":
            if (self.umkm_id is None) == (self.umkm is None):
                raise ValueError("Role umkm wajib mengisi salah satu: umkm_id atau umkm")
        elif self.umkm_id is not None or self.umkm is not None:
            raise ValueError("umkm_id/umkm hanya untuk role umkm")
        return self


class UMKMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    umkm_type: str
    address: str
    kecamatan: str
    phone_whatsapp: Optional[str] = None
    connected_power_va: Optional[int] = None
    tariff_group: str
    pv_kwp: float
    battery_kwh: float
    consent_share_data: bool
    created_at: datetime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: Optional[str] = None
    role: RoleName
    umkm_id: Optional[int] = None
    is_active: bool
    created_at: datetime
    umkm: Optional[UMKMOut] = None
    # Kompatibilitas dashboard lama (static/index.html).
    umkm_name: Optional[str] = None
    umkm_type: Optional[str] = None

    @model_validator(mode="after")
    def _flatten_umkm(self) -> "UserOut":
        if self.umkm is not None:
            self.umkm_name = self.umkm_name or self.umkm.name
            self.umkm_type = self.umkm_type or self.umkm.umkm_type
        return self


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Masa berlaku token (detik)")
    user: UserOut


class UserStatusUpdate(BaseModel):
    is_active: bool

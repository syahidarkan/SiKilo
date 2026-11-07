"""Skema dashboard multi-peran WASKITA (umkm, disperinaker, installer, bank, admin)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

LeadStatus = Literal["new", "contacted", "surveyed", "installed", "lost"]
MetricStatus = Literal["ok", "di_bawah_target", "info", "belum_ada_data"]


class EnergyPeriod(BaseModel):
    start: date
    end: date
    kwh: float
    cost_idr: float
    days_with_data: int


class UMKMProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    umkm_type: str
    address: str
    kecamatan: str
    tariff_group: str
    connected_power_va: Optional[int] = None
    pv_kwp: float
    battery_kwh: float
    consent_share_data: bool


class PlanSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    solver: str
    cost_idr: float
    baseline_cost_idr: float
    savings_idr: float
    savings_pct: float
    deadlines_met: bool


class DeviceSummary(BaseModel):
    device_id: str
    firmware_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    online: bool


class ApplianceEnergy(BaseModel):
    appliance_label: str
    kwh: float
    cost_idr: float


class RaporSummary(BaseModel):
    status: Literal["ok", "belum_ada_data", "gagal"]
    data_days: int
    min_data_days: int
    monthly_kwh: Optional[float] = None
    monthly_cost_idr: Optional[float] = None
    recommended_kwp: Optional[float] = None
    payback_years: Optional[float] = None
    score: Optional[float] = None
    risk_category: Optional[str] = None
    annual_savings_idr: Optional[float] = None
    note: str = ""
    validation: str = ""


class LeadOut(BaseModel):
    id: int
    umkm_id: int
    umkm_name: Optional[str] = None
    umkm_type: Optional[str] = None
    kecamatan: Optional[str] = None
    address: Optional[str] = None
    phone_whatsapp: Optional[str] = None
    pv_kwp: Optional[float] = None
    installer_user_id: Optional[int] = None
    status: LeadStatus
    recommended_kwp: float
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LeadCreate(BaseModel):
    umkm_id: Optional[int] = Field(None, gt=0, description="Wajib untuk admin; role umkm memakai UMKM-nya")
    notes: Optional[str] = Field(None, max_length=2000)
    installer_user_id: Optional[int] = Field(None, gt=0, description="Khusus admin")
    recommended_kwp: Optional[float] = Field(None, ge=0, le=1000, description="Khusus admin; kosong = dihitung")


class LeadUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    notes: Optional[str] = Field(None, max_length=2000)
    claim: bool = Field(False, description="Installer mengambil lead yang belum ditugaskan")
    installer_user_id: Optional[int] = Field(None, gt=0, description="Khusus admin")
    unassign: bool = Field(False, description="Khusus admin: lepas penugasan installer")
    recompute_kwp: bool = Field(False, description="Hitung ulang rekomendasi kWp dari data terbaru")


class UMKMDashboard(BaseModel):
    generated_at: datetime
    umkm: UMKMProfileOut
    today: EnergyPeriod
    last_7_days: EnergyPeriod
    last_30_days: EnergyPeriod
    top_appliances: list[ApplianceEnergy]
    devices: list[DeviceSummary]
    latest_plan: Optional[PlanSummary] = None
    plans_30d: dict[str, Any]
    leads: list[LeadOut]
    rapor: Optional[RaporSummary] = None
    notes: list[str]


class KecamatanStat(BaseModel):
    kecamatan: str
    n_umkm: int
    kwh: float
    cost_idr: float
    potential_savings_idr_per_month: float


class UMKMAggregateItem(BaseModel):
    umkm_id: int
    name: str
    umkm_type: str
    kecamatan: str
    kwh: float
    cost_idr: float
    days_with_data: int
    has_pv: bool
    ready_for_pv: bool


class DisperinakerDashboard(BaseModel):
    generated_at: datetime
    start: date
    end: date
    n_umkm_total: int
    n_umkm_consent: int
    n_umkm_with_data: int
    total_kwh: float
    total_cost_idr: float
    recorded_plan_savings_idr: float
    potential_savings_idr_per_month: float
    kecamatan: list[KecamatanStat]
    plts: dict[str, Any]
    umkm: list[UMKMAggregateItem]
    notes: list[str]


class BankUMKMItem(BaseModel):
    umkm_id: int
    name: str
    umkm_type: str
    kecamatan: str
    pv_kwp: float
    rapor: RaporSummary


class BankDashboard(BaseModel):
    generated_at: datetime
    total: int
    items: list[BankUMKMItem]
    notes: list[str]


class KPIMetric(BaseModel):
    key: str
    name: str
    value: Optional[float] = None
    unit: str = ""
    target: Optional[float] = None
    target_direction: Literal["min", "max"] = "min"
    status: MetricStatus
    source: str
    validation: Optional[str] = None
    detail: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[str] = None


class KPIBoard(BaseModel):
    generated_at: datetime
    scope: str
    period_days: int
    metrics: list[KPIMetric]

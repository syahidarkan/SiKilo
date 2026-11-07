"""
Skema API sizing PLTS WASKITA (tahap "Punya PLTS").

- ``SizingRequest``/``SizingResult``: ukuran PLTS (dan baterai opsional) dari
  histori beban per jam, kriteria NPV maksimum di bawah aturan ekspor tidak
  dikreditkan (Permen ESDM No. 2/2024).
- ``CompareRequest``/``CompareResult``: ukuran PLTS minimum untuk mencapai
  target penghematan tagihan dengan jadwal kebiasaan lama vs jadwal agen.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.dispatch import MachineJob


class DailyLoadProfile(BaseModel):
    date: date
    hourly_kwh: List[float] = Field(..., min_length=24, max_length=24)

    @model_validator(mode="after")
    def _non_negative(self) -> "DailyLoadProfile":
        if any(v < 0 for v in self.hourly_kwh):
            raise ValueError(f"{self.date}: hourly_kwh tidak boleh negatif")
        return self


class SizingRequest(BaseModel):
    load_profiles: List[DailyLoadProfile] = Field(
        ..., min_length=1, max_length=400,
        description="Histori beban per jam (disarankan ≥ 30 hari; bulan berbeda dipakai per bulan)",
    )
    location_lat: Optional[float] = Field(default=None, ge=-90, le=90, description="Kosong = lokasi default")
    location_lon: Optional[float] = Field(default=None, ge=-180, le=180, description="Kosong = lokasi default")
    target_self_consumption_pct: float = Field(
        default=0.90, ge=0.5, le=1.0,
        description="Batas bawah rasio PV terpakai sendiri (0–1). Ekspor tidak dikreditkan.",
    )
    include_battery: bool = Field(default=False, description="Coba juga kapasitas baterai (lihat battery_options_kwh)")
    battery_options_kwh: Optional[List[float]] = Field(
        default=None, max_length=8,
        description="Kapasitas baterai yang dicoba (kWh); kosong = settings.sizing_battery_options_kwh",
    )
    connected_power_va: Optional[float] = Field(
        default=None, gt=0, le=10_000_000, description="Daya tersambung PLN (VA), membatasi kWp bila diisi"
    )
    reference_year: Optional[int] = Field(
        default=None, ge=2001, le=2100,
        description="Tahun cuaca acuan; kosong = tahun lengkap terakhir",
    )

    @model_validator(mode="after")
    def _check_battery_options(self) -> "SizingRequest":
        if self.battery_options_kwh is not None and any(b < 0 or b > 1000 for b in self.battery_options_kwh):
            raise ValueError("battery_options_kwh harus di rentang 0–1000 kWh")
        return self


class SizingCandidate(BaseModel):
    kwp: float
    battery_kwh: float
    self_consumption_rate_pct: float
    annual_generation_kwh: float
    annual_self_consumption_kwh: float
    annual_savings_idr: float
    capex_idr: float
    npv_idr: float
    feasible: bool = Field(..., description="Memenuhi target self-consumption & batas daya tersambung")


class RegulatoryChecks(BaseModel):
    """Pemeriksaan yang bisa dipertanggungjawabkan — BUKAN pernyataan kepatuhan."""

    connected_power_kva: Optional[float] = None
    kwp_within_connected_power: Optional[bool] = Field(
        None, description="None bila daya tersambung belum diketahui"
    )
    export_not_credited_modeled: bool = Field(
        True, description="Surplus PV dianggap terbuang (tidak mengurangi tagihan)"
    )
    application_window_note: str
    disclaimer: str
    notes: List[str] = Field(default_factory=list)


class SizingResult(BaseModel):
    recommended_kwp: float
    recommended_battery_kwh: float = 0.0
    kwp_for_target_sc: float = Field(
        0.0, description="kWp terbesar (tanpa baterai) yang masih memenuhi target self-consumption"
    )
    target_self_consumption_pct: float = 0.0
    target_sc_feasible: bool = True
    max_kwp_limit: Optional[float] = Field(None, description="Batas kWp dari daya tersambung (bila diisi)")
    annual_generation_kwh: float
    annual_self_consumption_kwh: float
    annual_curtailment_kwh: float
    self_consumption_rate_pct: float
    annual_load_kwh: float = 0.0
    solar_fraction_pct: float = Field(0.0, description="Porsi beban yang dipasok PV")
    annual_bill_before_idr: float = 0.0
    annual_bill_after_idr: float = 0.0
    pv_capex_idr: float = 0.0
    battery_capex_idr: float = 0.0
    capex_idr: float
    annual_opex_idr: float = 0.0
    annual_savings_idr: float = Field(..., description="Penghematan tagihan tahun pertama (sebelum OPEX)")
    lcoe_idr_per_kwh: float
    npv_idr: float
    payback_period_years: float = Field(..., description="PBP sederhana; 99.9 bila tidak balik modal")
    discounted_payback_years: Optional[float] = Field(None, description="None bila tidak balik modal dalam umur proyek")
    financially_viable: bool = True
    co2_avoided_kg_per_year: float
    permen_esdm_compliant: bool = Field(
        False,
        description=(
            "USANG, dipertahankan demi kompatibilitas: True hanya bila kWp ≤ daya tersambung yang diketahui. "
            "Bukan pernyataan kepatuhan — lihat regulatory_checks."
        ),
    )
    regulatory_checks: Optional[RegulatoryChecks] = None
    reference_year: int = 0
    pv_source: str = ""
    tariff_group: str = ""
    tariff_scheme: str = ""
    candidates: List[SizingCandidate] = Field(default_factory=list)
    assumptions: dict = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
    recommendation_note: str


# ── /sizing/compare ─────────────────────────────────────────────────────────


class CompareRequest(BaseModel):
    jobs: List[MachineJob] = Field(default_factory=list, description="Kosong = contoh mesin default")
    baseload_w: Optional[float] = Field(default=None, ge=0, le=100_000)
    connected_power_va: Optional[float] = Field(default=None, gt=0, le=10_000_000)
    target_savings_idr_per_month: Optional[float] = Field(default=None, gt=0)
    target_savings_pct: Optional[float] = Field(
        default=None, gt=0, lt=100, description="Persen dari tagihan energi sekarang (kebiasaan lama, tanpa PLTS)"
    )
    location_lat: Optional[float] = Field(default=None, ge=-90, le=90)
    location_lon: Optional[float] = Field(default=None, ge=-180, le=180)
    battery_kwh: float = Field(default=0.0, ge=0, le=1000)
    kwp_candidates: Optional[List[float]] = Field(
        default=None, max_length=16, description="Kandidat kWp; kosong = otomatis"
    )
    operating_days_per_week: Optional[int] = Field(
        default=None, ge=1, le=7, description="Kosong = settings.sizing_operating_days_per_week"
    )
    solver: Literal["greedy", "ortools"] = Field(
        default="greedy",
        description="greedy = cepat; ortools = OR-Tools dengan batas waktu kecil, diambil yang termurah dengan greedy",
    )
    reference_year: Optional[int] = Field(default=None, ge=2001, le=2100)

    @model_validator(mode="after")
    def _check(self) -> "CompareRequest":
        if (self.target_savings_idr_per_month is None) == (self.target_savings_pct is None):
            raise ValueError("Isi tepat satu: target_savings_idr_per_month atau target_savings_pct")
        ids = [j.machine_id for j in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("machine_id setiap mesin harus unik")
        if len(ids) > 30:
            raise ValueError("Maksimal 30 mesin per permintaan")
        if self.kwp_candidates is not None and any(k < 0 or k > 1000 for k in self.kwp_candidates):
            raise ValueError("kwp_candidates harus di rentang 0–1000")
        return self


class ComparePoint(BaseModel):
    kwp: float
    pv_capex_idr: float
    habit_annual_bill_idr: float
    habit_no_idle_annual_bill_idr: float
    agent_annual_bill_idr: float
    habit_savings_idr_per_year: float
    habit_no_idle_savings_idr_per_year: float
    agent_savings_idr_per_year: float
    habit_savings_pct: float
    agent_savings_pct: float
    habit_pv_used_kwh: float
    agent_pv_used_kwh: float
    pv_generated_kwh: float
    deadlines_met: bool = True


class CompareResult(BaseModel):
    reference_annual_bill_idr: float = Field(..., description="Tagihan energi setahun: kebiasaan lama, tanpa PLTS")
    target_annual_savings_idr: float
    target_monthly_savings_idr: float
    target_savings_pct: float
    min_kwp_habit: Optional[float] = Field(None, description="None = target tidak tercapai di rentang kandidat")
    min_kwp_habit_no_idle: Optional[float] = None
    min_kwp_agent: Optional[float] = None
    kwp_reduction: Optional[float] = None
    kwp_reduction_pct: Optional[float] = None
    capex_reduction_idr: Optional[float] = None
    agent_reduces_panel: bool = False
    headline: str
    curve: List[ComparePoint]
    kwp_candidates: List[float]
    max_kwp_limit: Optional[float] = None
    battery_kwh: float = 0.0
    operating_days_per_week: int = 7
    solver: str
    reference_year: int
    pv_source: str
    n_plans: int
    compute_time_s: float
    timed_out: bool = False
    notes: List[str] = Field(default_factory=list)

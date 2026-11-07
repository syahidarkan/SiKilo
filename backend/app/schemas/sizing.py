from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class DailyLoadProfile(BaseModel):
    date: date
    hourly_kwh: List[float] = Field(..., min_length=24, max_length=24)


class SizingRequest(BaseModel):
    load_profiles: List[DailyLoadProfile] = Field(..., description="Histori beban 30 hari")
    location_lat: float = Field(default=-7.68)
    location_lon: float = Field(default=110.83)
    target_self_consumption_pct: float = Field(default=0.98, ge=0.8, le=1.0)
    include_battery: bool = Field(default=False)


class SizingResult(BaseModel):
    recommended_kwp: float
    annual_generation_kwh: float
    annual_self_consumption_kwh: float
    annual_curtailment_kwh: float
    self_consumption_rate_pct: float
    capex_idr: float
    annual_savings_idr: float
    lcoe_idr_per_kwh: float
    npv_idr: float
    payback_period_years: float
    co2_avoided_kg_per_year: float
    permen_esdm_compliant: bool
    recommendation_note: str

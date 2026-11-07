from pydantic import BaseModel, Field
from datetime import date, time
from typing import List


class MachineJob(BaseModel):
    machine_id: str
    appliance_class: int
    label: str
    daily_runtime_minutes: int = Field(..., description="Menit operasi wajib per hari")
    deadline_hour: int = Field(default=17, description="Batas selesai sebelum jam berapa")
    power_w: float = Field(..., description="Konsumsi daya nominal (Watt)")
    is_flexible: bool = Field(default=True)


class DispatchRequest(BaseModel):
    target_date: date
    jobs: List[MachineJob]
    kwp_capacity: float = Field(default=0.0, description="Kapasitas PLTS terpasang (kWp), 0 jika belum ada")
    use_rl_agent: bool = Field(default=True)


class SlotSchedule(BaseModel):
    slot_index: int = Field(..., description="Index slot 15 menit (0-95)")
    time_label: str = Field(..., description="Label waktu, misal '10:00'")
    machine_id: str
    state: int = Field(..., description="1=ON, 0=OFF")
    p_load_w: float
    p_pv_w: float
    p_grid_w: float
    cost_idr: float


class DispatchResponse(BaseModel):
    target_date: date
    schedule: List[SlotSchedule]
    total_grid_kwh: float
    total_pv_kwh: float
    total_cost_idr: float
    baseline_cost_idr: float
    savings_idr: float
    savings_pct: float
    solver_used: str
    curtailment_kwh: float

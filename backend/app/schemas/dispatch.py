"""
Skema API penjadwal mesin WASKITA (tahap "Atur").

Satu hari = 96 slot × 15 menit. Jam kerja mesin ditulis sebagai jam bulat:
mesin boleh menyala pada slot ``[earliest_hour·4, deadline_hour·4)``.
"""
from __future__ import annotations

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.core.config import settings


class MachineJob(BaseModel):
    machine_id: str = Field(..., min_length=1, max_length=64)
    appliance_class: int = Field(default=0, ge=0)
    label: str = Field(..., min_length=1, max_length=120)
    power_w: float = Field(..., gt=0, le=100_000, description="Daya nominal saat bekerja (Watt)")
    daily_runtime_minutes: int = Field(..., ge=0, le=1440, description="Menit operasi wajib per hari")
    earliest_hour: int = Field(
        default_factory=lambda: settings.work_start_hour, ge=0, le=23,
        description="Jam paling awal mesin boleh menyala",
    )
    deadline_hour: int = Field(
        default_factory=lambda: settings.work_end_hour, ge=1, le=24,
        description="Pekerjaan harus selesai sebelum jam ini",
    )
    habit_start_hour: Optional[int] = Field(
        default=None, ge=0, le=23,
        description="Jam mulai menurut kebiasaan lama pemilik (kosong = default_habit_start_hour)",
    )
    min_continuous_minutes: int = Field(
        default=15, ge=15, le=1440, description="Sekali menyala, minimal jalan sekian menit berturut-turut"
    )
    cooldown_minutes: Optional[int] = Field(
        default=None, ge=0, le=240,
        description="Jeda minimal setelah dimatikan sebelum menyala lagi (kosong = default_cooldown_minutes)",
    )
    is_flexible: bool = Field(default=True, description="False = jadwal tetap mengikuti kebiasaan lama")
    idle_minutes_habit: int = Field(
        default=0, ge=0, le=1440,
        description="Menit mesin dibiarkan menyala tanpa beban (idle) dalam kebiasaan lama",
    )
    idle_power_w: Optional[float] = Field(
        default=None, ge=0, le=100_000,
        description="Daya saat idle (kosong = default_idle_power_frac × power_w)",
    )

    @model_validator(mode="after")
    def _check_window(self) -> "MachineJob":
        if self.deadline_hour <= self.earliest_hour:
            raise ValueError(
                f"{self.machine_id}: deadline_hour ({self.deadline_hour}) harus lebih besar dari "
                f"earliest_hour ({self.earliest_hour})"
            )
        window_min = (self.deadline_hour - self.earliest_hour) * 60
        if self.daily_runtime_minutes > window_min:
            raise ValueError(
                f"{self.machine_id}: runtime {self.daily_runtime_minutes} menit melebihi jendela kerja "
                f"{self.earliest_hour:02d}:00–{self.deadline_hour:02d}:00 ({window_min} menit)"
            )
        return self


class DispatchRequest(BaseModel):
    target_date: date
    jobs: List[MachineJob] = Field(default_factory=list, description="Kosong = contoh mesin default")
    kwp_capacity: float = Field(default=0.0, ge=0, le=1000, description="Kapasitas PLTS terpasang (kWp), 0 jika belum ada")
    battery_kwh: float = Field(default=0.0, ge=0, le=1000, description="Kapasitas baterai (kWh), 0 jika tidak ada")
    baseload_w: Optional[float] = Field(default=None, ge=0, le=100_000, description="Beban dasar (lampu, kipas, dll.)")
    solver: Literal["auto", "ortools", "ppo", "greedy"] = "auto"
    use_rl_agent: Optional[bool] = Field(
        default=None,
        description="Usang: True → solver 'auto', False → 'ortools'. Dipakai hanya bila diisi.",
    )
    apply_order_book: bool = Field(
        default=False, description="Skalakan runtime menurut pola pesanan mingguan/musiman (OrderBook)"
    )
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _unique_ids(self) -> "DispatchRequest":
        ids = [j.machine_id for j in self.jobs]
        if len(ids) != len(set(ids)):
            raise ValueError("machine_id setiap mesin harus unik")
        if len(ids) > 30:
            raise ValueError("Maksimal 30 mesin per permintaan")
        return self


class SlotSchedule(BaseModel):
    slot_index: int = Field(..., description="Index slot 15 menit (0-95)")
    time_label: str = Field(..., description="Label waktu, misal '10:00'")
    machines_on: List[str] = Field(default_factory=list, description="Semua mesin yang ON di slot ini")
    machine_id: str = Field(
        default="baseload",
        description="USANG: mesin pertama yang ON (atau 'baseload'); pakai machines_on",
    )
    state: int = Field(..., description="1 = ada mesin terjadwal ON, 0 = hanya beban dasar")
    p_load_w: float
    p_pv_w: float
    p_grid_w: float
    p_curtail_w: float = 0.0
    battery_soc_wh: Optional[float] = None
    baseline_load_w: float = 0.0
    tariff_idr_per_kwh: float = 0.0
    cost_idr: float


class TimeBlock(BaseModel):
    start: str
    end: str
    slots: int


class MachinePlan(BaseModel):
    machine_id: str
    label: str
    power_w: float
    is_flexible: bool
    runtime_minutes: int
    scheduled_minutes: int
    window: str = Field(..., description="Jendela kerja, misal '07:00–17:00'")
    blocks: List[TimeBlock] = Field(default_factory=list, description="Blok nyala hasil agen")
    habit_blocks: List[TimeBlock] = Field(default_factory=list, description="Blok nyala kebiasaan lama")
    idle_minutes_habit: int = 0
    deadline_met: bool
    on_slots: List[int] = Field(default_factory=list)


class SavingsBreakdown(BaseModel):
    idle_idr: float = Field(0.0, description="Hemat karena tidak ada mesin idle")
    shifting_idr: float = Field(0.0, description="Hemat/rugi karena geser jadwal (PV/baterai/tarif), boleh negatif")


class DispatchResponse(BaseModel):
    target_date: date
    schedule: List[SlotSchedule]
    total_grid_kwh: float
    total_pv_kwh: float = Field(..., description="Energi PV yang dipakai sendiri (termasuk lewat baterai)")
    total_cost_idr: float
    baseline_cost_idr: float
    savings_idr: float = Field(..., description="baseline − agen; boleh negatif")
    savings_pct: float
    solver_used: str
    curtailment_kwh: float
    deadlines_met: bool = True
    pv_source: str = "none"
    pv_generated_kwh: float = 0.0
    baseline_grid_kwh: float = 0.0
    machines: List[MachinePlan] = Field(default_factory=list)
    savings_breakdown: SavingsBreakdown = Field(default_factory=SavingsBreakdown)
    tariff_scheme: str = Field(default_factory=lambda: settings.tariff_scheme)
    notes: List[str] = Field(default_factory=list)


class DefaultJobsResponse(BaseModel):
    jobs: List[MachineJob]
    baseload_w: float
    work_start_hour: int
    work_end_hour: int
    default_habit_start_hour: int
    note: str

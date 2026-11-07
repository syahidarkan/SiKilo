from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TelemetryPayload(BaseModel):
    device_id: str = Field(..., examples=["ESP32-SKH-042"])
    timestamp: datetime
    v_rms: float = Field(..., ge=0.0, le=300.0, description="Tegangan RMS (Volt)")
    i_rms: float = Field(..., ge=0.0, le=200.0, description="Arus RMS (Ampere)")
    p_active: float = Field(..., ge=0.0, description="Daya aktif (Watt)")
    q_reactive: float = Field(..., description="Daya reaktif (VAR)")
    frequency: float = Field(..., ge=48.0, le=52.0, description="Frekuensi jaringan (Hz)")


class TelemetryResponse(BaseModel):
    device_id: str
    timestamp: datetime
    p_active: float
    detected_event: bool
    appliance_class: Optional[int] = None
    appliance_label: Optional[str] = None
    confidence: Optional[float] = None
    message: str


class ApplianceStatus(BaseModel):
    appliance_class: int
    label: str
    state: str  # "ON" | "OFF"
    p_estimate_w: float
    last_seen: datetime

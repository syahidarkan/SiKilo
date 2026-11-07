from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    device_id: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        examples=["ESP32-SKH-042"],
    )
    umkm_id: int = Field(..., gt=0)
    firmware_version: Optional[str] = Field(None, max_length=32, examples=["1.0.0"])


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    umkm_id: int
    firmware_version: Optional[str] = None
    last_seen: Optional[datetime] = None
    created_at: datetime


class DeviceWithKey(DeviceOut):
    api_key: str = Field(..., description="API key perangkat. HANYA ditampilkan sekali; simpan di firmware.")
    header_name: str = "X-Device-Key"

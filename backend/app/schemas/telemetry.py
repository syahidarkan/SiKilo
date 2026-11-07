"""
Skema telemetri WASKITA (firmware → API, API → dashboard).

Timestamp:
- Wajib ISO 8601. Bila tanpa zona waktu (naive) dianggap waktu lokal lokasi
  (``settings.site_timezone``, default Asia/Jakarta / WIB).
- Disimpan sebagai UTC; buku energi (ledger) memakai jam LOKAL.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo
from functools import lru_cache
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

MAX_BATCH_SAMPLES = 500


@lru_cache(maxsize=1)
def local_tz() -> tzinfo:
    """Zona waktu lokasi. Fallback UTC+7 bila basis data zona waktu tidak ada."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(settings.site_timezone)
    except Exception:  # noqa: BLE001 - mis. Windows tanpa paket tzdata
        return timezone(timedelta(hours=7), "WIB")


def to_local(ts: datetime) -> datetime:
    """Naive → dianggap waktu lokal; aware → dikonversi ke waktu lokal."""
    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        return ts.replace(tzinfo=local_tz())
    return ts.astimezone(local_tz())


def is_too_far_future(ts: datetime, now: Optional[datetime] = None) -> bool:
    """True bila ``ts`` lebih maju dari jam server + ``telemetry_max_future_skew_s``."""
    now = now or datetime.now(timezone.utc)
    return to_local(ts) > now + timedelta(seconds=settings.telemetry_max_future_skew_s)


def _check_timestamp(ts: datetime) -> datetime:
    ts = to_local(ts)
    if is_too_far_future(ts):
        raise ValueError("timestamp terlalu jauh di masa depan; periksa sinkronisasi jam (NTP) perangkat")
    return ts


class TelemetrySampleBase(BaseModel):
    """
    Satu sampel pengukuran panel TANPA cek jam masa depan (dipakai di batch:
    sampel bertimestamp masa depan dibuang per sampel di endpoint, bukan
    menolak seluruh batch).
    """

    timestamp: datetime = Field(..., description="ISO 8601; tanpa zona waktu dianggap WIB")
    v_rms: float = Field(..., ge=0.0, le=300.0, description="Tegangan RMS (Volt)")
    i_rms: float = Field(..., ge=0.0, le=200.0, description="Arus RMS (Ampere)")
    p_active: float = Field(..., ge=0.0, description="Daya aktif (Watt), ≥ 0")
    q_reactive: float = Field(..., description="Daya reaktif (VAR)")
    frequency: float = Field(..., ge=48.0, le=52.0, description="Frekuensi jaringan (Hz)")

    @field_validator("timestamp")
    @classmethod
    def _tz_local(cls, v: datetime) -> datetime:
        return to_local(v)


class TelemetrySampleIn(BaseModel):
    """Satu sampel pengukuran panel (tanpa device_id) dengan cek jam masa depan."""

    timestamp: datetime = Field(..., description="ISO 8601; tanpa zona waktu dianggap WIB")
    v_rms: float = Field(..., ge=0.0, le=300.0, description="Tegangan RMS (Volt)")
    i_rms: float = Field(..., ge=0.0, le=200.0, description="Arus RMS (Ampere)")
    p_active: float = Field(..., ge=0.0, description="Daya aktif (Watt), ≥ 0")
    q_reactive: float = Field(..., description="Daya reaktif (VAR)")
    frequency: float = Field(..., ge=48.0, le=52.0, description="Frekuensi jaringan (Hz)")

    @field_validator("timestamp")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        return _check_timestamp(v)


class TelemetryPayload(TelemetrySampleIn):
    device_id: str = Field(..., min_length=1, max_length=64, examples=["ESP32-SKH-042"])


class TelemetryBatch(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=64)
    samples: list[TelemetrySampleBase] = Field(..., min_length=1, max_length=MAX_BATCH_SAMPLES)


class TelemetryResponse(BaseModel):
    device_id: str
    timestamp: datetime
    p_active: float
    detected_event: bool
    event_type: Optional[str] = None
    delta_p: Optional[float] = None
    appliance_class: Optional[int] = None
    appliance_label: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None
    active_appliances: dict[str, float] = Field(default_factory=dict, description="label → watt estimasi")
    baseload_w: float = 0.0
    stored: bool = Field(False, description="Sampel mentah disimpan (downsampling)")
    duplicate: bool = Field(False, description="Timestamp ≤ sampel terakhir; diabaikan")
    ledger_rows_written: int = 0
    simulated: bool = False
    message: str


class TelemetryBatchResponse(BaseModel):
    device_id: str
    received: int
    processed: int
    skipped_duplicates: int
    rejected_future: int = Field(0, description="Sampel dibuang karena timestamp terlalu jauh di masa depan")
    stored_records: int
    events: int
    ledger_rows_written: int
    first_timestamp: datetime
    last_timestamp: datetime
    message: str


class ApplianceStatus(BaseModel):
    appliance_class: int
    label: str
    state: Literal["ON", "OFF"]
    p_estimate_w: float
    last_seen: Optional[datetime] = Field(None, description="Waktu event ON/OFF terakhir")
    source: Literal["live", "event"] = Field(
        ..., description="live = status disaggregator di memori; event = event tersimpan terakhir"
    )


class ApplianceStatusResponse(BaseModel):
    umkm_id: int
    generated_at: datetime
    live: bool = Field(..., description="Ada perangkat UMKM ini yang statusnya ada di memori server")
    appliances: list[ApplianceStatus]


class LedgerRow(BaseModel):
    day: date
    hour: Optional[int] = None
    appliance_label: str
    kwh: float
    cost_idr: float


class LedgerApplianceTotal(BaseModel):
    appliance_label: str
    kwh: float
    cost_idr: float
    share_pct: float


class LedgerResponse(BaseModel):
    umkm_id: int
    start: date
    end: date
    granularity: Literal["hour", "day"]
    tariff_scheme: str
    tariff_group: str
    total_kwh: float
    total_cost_idr: float
    per_appliance: list[LedgerApplianceTotal]
    rows: list[LedgerRow]
    note: str


class TelemetryRecordOut(BaseModel):
    device_id: str
    ts: datetime
    v_rms: float
    i_rms: float
    p_active: float
    q_reactive: float
    frequency: float

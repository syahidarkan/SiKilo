"""
Model SQLAlchemy 2.0 WASKITA (lihat docs/CONTRACTS.md §1).

Semua model diimpor di sini agar ``Base.metadata`` lengkap saat
``app.core.database.init_db()`` menjalankan create_all.

Catatan: kolom waktu memakai ``UTCDateTime`` (selalu tz-aware UTC, juga di
SQLite). Hanya ``User.umkm`` yang punya relationship (eager/selectin);
model lain direlasikan lewat kolom FK dan di-query eksplisit agar tidak
ada lazy-load tersembunyi di konteks async.
"""
from app.models.device import Device
from app.models.energy import DailyPlan, EnergyLedger, MachineProfile
from app.models.lead import LEAD_STATUSES, Lead
from app.models.messaging import MESSAGE_KINDS, MESSAGE_STATUSES, MessageLog
from app.models.telemetry import ApplianceEvent, TelemetryRecord
from app.models.types import UTCDateTime, utcnow
from app.models.umkm import UMKM
from app.models.user import ROLES, Role, User

__all__ = [
    "ApplianceEvent",
    "DailyPlan",
    "Device",
    "EnergyLedger",
    "LEAD_STATUSES",
    "Lead",
    "MESSAGE_KINDS",
    "MESSAGE_STATUSES",
    "MachineProfile",
    "MessageLog",
    "ROLES",
    "Role",
    "TelemetryRecord",
    "UMKM",
    "UTCDateTime",
    "User",
    "utcnow",
]

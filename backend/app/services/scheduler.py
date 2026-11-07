"""
Penjadwal latar WASKITA (APScheduler ``AsyncIOScheduler``, zona Asia/Jakarta).

- Job harian  : ``settings.whatsapp_send_hour:whatsapp_send_minute`` setiap hari →
  ``app.services.jobs.run_daily_briefs`` (jadwal mesin untuk BESOK).
- Job mingguan: jam yang sama pada ``settings.weekly_report_weekday``
  (0 = Senin … 6 = Minggu) → ``app.services.jobs.run_weekly_notas``.

``start_scheduler()`` adalah no-op bila ``settings.scheduler_enabled`` False.
Dipanggil dari lifespan FastAPI (``app/main.py``) sehingga event loop sudah
berjalan. Jalankan HANYA satu proses dengan penjadwal aktif (mis. satu worker
uvicorn) agar pesan tidak terkirim ganda.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

DAILY_JOB_ID = "waskita_daily_brief"
WEEKLY_JOB_ID = "waskita_weekly_nota"
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_scheduler: Optional[Any] = None


def _tz():
    from app.schemas.telemetry import local_tz

    return local_tz()


async def _daily_job() -> None:
    from app.services import jobs

    try:
        await jobs.run_daily_briefs()
    except Exception:  # noqa: BLE001
        logger.exception("Job brief harian gagal.")


async def _weekly_job() -> None:
    from app.services import jobs

    try:
        await jobs.run_weekly_notas()
    except Exception:  # noqa: BLE001
        logger.exception("Job nota mingguan gagal.")


def build_scheduler():
    """Buat ``AsyncIOScheduler`` beserta kedua job (belum dijalankan)."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    tz = _tz()
    hour = int(settings.whatsapp_send_hour) % 24
    minute = int(settings.whatsapp_send_minute) % 60
    weekday = _WEEKDAYS[int(settings.weekly_report_weekday) % 7]
    sched = AsyncIOScheduler(timezone=tz)
    common = {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600, "replace_existing": True}
    sched.add_job(_daily_job, CronTrigger(hour=hour, minute=minute, timezone=tz), id=DAILY_JOB_ID, **common)
    sched.add_job(
        _weekly_job,
        CronTrigger(day_of_week=weekday, hour=hour, minute=minute, timezone=tz),
        id=WEEKLY_JOB_ID,
        **common,
    )
    return sched


def start_scheduler():
    """Mulai penjadwal (butuh event loop berjalan). Kembalikan scheduler atau ``None``."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("Penjadwal WASKITA nonaktif (SCHEDULER_ENABLED=false).")
        return None
    if _scheduler is not None and getattr(_scheduler, "running", False):
        return _scheduler
    try:
        sched = build_scheduler()
        sched.start()
    except Exception:  # noqa: BLE001 - jangan gagalkan start aplikasi
        logger.exception("Penjadwal gagal dijalankan.")
        return None
    _scheduler = sched
    logger.info(
        "Penjadwal aktif: brief harian %02d:%02d, nota mingguan hari %s (zona %s); penyedia WA=%s.",
        settings.whatsapp_send_hour, settings.whatsapp_send_minute,
        _WEEKDAYS[int(settings.weekly_report_weekday) % 7], settings.site_timezone, settings.whatsapp_provider,
    )
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        if getattr(_scheduler, "running", False):
            _scheduler.shutdown(wait=False)
    finally:
        _scheduler = None


def get_scheduler():
    return _scheduler


__all__ = ["DAILY_JOB_ID", "WEEKLY_JOB_ID", "build_scheduler", "get_scheduler", "shutdown_scheduler", "start_scheduler"]

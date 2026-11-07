"""
Pemrosesan telemetri lapangan per perangkat.

Alur satu sampel (urut waktu, per perangkat diserialkan dengan lock):
1. Sampel dengan timestamp ≤ sampel terakhir yang sudah diproses dianggap
   duplikat / kiriman ulang → dilewati (firmware mengirim ulang bila respons hilang).
2. ``LoadDisaggregator.push`` (cache in-memory per perangkat) → event ON/OFF,
   klasifikasi, daya per mesin.
3. Sampel mentah disimpan ke ``TelemetryRecord`` bila: ≥ ``telemetry_raw_keep_every_s``
   sejak sampel tersimpan terakhir, ATAU jam lokal berganti, ATAU ada event.
4. Event mesin (kelas ≠ 0) disimpan ke ``ApplianceEvent``.
5. ``pop_hourly_energy()`` → ``EnergyLedger`` (biaya dari ``app.core.tariff``).
6. Commit; bila gagal, status disaggregator dikembalikan ke kondisi sebelum
   request (snapshot) sehingga firmware bisa mengirim ulang tanpa data ganda.

Rekonstruksi setelah server restart: saat perangkat pertama kali terlihat,
sampel tersimpan pada jam lokal yang sedang berjalan (jam sampel tersimpan
terakhir) diputar ulang ke disaggregator baru. Karena sampel pertama tiap jam
selalu disimpan, jam itu pasti belum pernah ditulis ke ledger → tidak ada
energi ganda. Energi jam tersebut menjadi PERKIRAAN (resolusi ~10 detik dari
sampel tersimpan, bukan 1 detik), dan status ON/OFF mesin bisa meleset
sampai event berikutnya.
"""
from __future__ import annotations

import asyncio
import copy
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ApplianceEvent, Device, MachineProfile, TelemetryRecord
from app.nilm.classifier import APPLIANCE_LABELS, ClassificationResult, NILMClassifier
from app.nilm.disaggregator import DisaggregationUpdate, HourlyEnergy, LoadDisaggregator
from app.nilm.event_detector import TelemetrySample, TransientEvent
from app.schemas.telemetry import TelemetrySampleIn, to_local
from app.services_data.ledger import upsert_ledger
from app.services_data.live import hub

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def shared_classifier() -> NILMClassifier:
    """Satu classifier (model LightGBM dimuat sekali) dipakai semua perangkat."""
    return NILMClassifier()


def new_disaggregator(max_instances: Optional[dict[str, int]] = None) -> LoadDisaggregator:
    return LoadDisaggregator(classifier=shared_classifier(), max_instances_per_label=max_instances or None)


def replay_max_gap_s() -> float:
    """Δt maksimum saat memutar ulang sampel tersimpan: 2× interval simpan (min. 20 s)."""
    return float(max(2 * max(settings.telemetry_raw_keep_every_s, 1), 20))


def to_nilm_sample(s: TelemetrySampleIn | Any, ts_local: Optional[datetime] = None) -> TelemetrySample:
    return TelemetrySample(
        timestamp=ts_local if ts_local is not None else to_local(s.timestamp),
        p_active=float(s.p_active),
        q_reactive=float(s.q_reactive),
        v_rms=float(s.v_rms),
        i_rms=float(s.i_rms),
        frequency=float(s.frequency),
    )


def build_message(
    *,
    device_id: str,
    umkm_id: Optional[int],
    sample: TelemetrySample,
    update: DisaggregationUpdate,
    simulated: bool,
) -> dict[str, Any]:
    """Pesan siaran/balasan WebSocket (kompatibel dengan dashboard statis lama)."""
    msg: dict[str, Any] = {
        "type": "telemetry",
        "simulated": simulated,
        "device_id": device_id,
        "umkm_id": umkm_id,
        "timestamp": sample.timestamp.isoformat(),
        "p_active": round(sample.p_active, 2),
        "q_reactive": round(sample.q_reactive, 2),
        "v_rms": round(sample.v_rms, 2),
        "i_rms": round(sample.i_rms, 3),
        "frequency": round(sample.frequency, 3),
        "active_appliances": {k: round(v, 1) for k, v in update.active.items()},
        "baseload_w": round(update.baseload_w, 1),
        "detected_event": update.event is not None and update.classification is not None,
    }
    if update.event is not None and update.classification is not None:
        msg.update(event_fields(update.event, update.classification))
    return msg


def event_fields(event: TransientEvent, result: ClassificationResult) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "event_timestamp": event.timestamp.isoformat(),
        "delta_p": round(event.delta_p, 1),
        "delta_q": round(event.delta_q, 1),
        "appliance_class": int(result.appliance_class),
        "appliance_label": result.label,
        "confidence": round(float(result.confidence), 3),
        "source": result.source,
    }


@dataclass
class DeviceState:
    device_id: str
    umkm_id: int
    disaggregator: LoadDisaggregator
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_ts: Optional[datetime] = None        # sampel terakhir yang diproses (lokal)
    last_kept_ts: Optional[datetime] = None   # sampel terakhir yang disimpan (lokal)
    pending_ledger: list[HourlyEnergy] = field(default_factory=list)
    replayed_records: int = 0
    last_update: Optional[DisaggregationUpdate] = None
    last_seen_utc: Optional[datetime] = None


@dataclass
class IngestResult:
    device_id: str
    umkm_id: int
    received: int = 0
    processed: int = 0
    duplicates: int = 0
    stored_records: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    ledger_rows_written: int = 0
    last_sample: Optional[TelemetrySample] = None
    last_update: Optional[DisaggregationUpdate] = None
    last_stored: bool = False
    first_ts: Optional[datetime] = None
    last_ts: Optional[datetime] = None


class IngestService:
    def __init__(self) -> None:
        self._states: dict[str, DeviceState] = {}
        self._init_lock: Optional[asyncio.Lock] = None
        self._init_loop: Optional[asyncio.AbstractEventLoop] = None

    # ── cache ───────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Hapus seluruh cache (tes / simulasi restart)."""
        self._states.clear()

    def forget(self, device_id: str) -> None:
        self._states.pop(device_id, None)

    async def refresh_machine_caps(self, db: AsyncSession, umkm_id: int) -> None:
        """Perbarui batas unit per label (dari MachineProfile) pada disaggregator yang sedang berjalan."""
        states = [st for st in self._states.values() if st.umkm_id == umkm_id]
        if not states:
            return
        caps = await self._machine_caps(db, umkm_id)
        for st in states:
            st.disaggregator.max_instances_per_label = caps or None

    def has_state(self, device_id: str) -> bool:
        return device_id in self._states

    def state(self, device_id: str) -> Optional[DeviceState]:
        return self._states.get(device_id)

    def live_states_for_umkm(self, umkm_id: int, max_age_s: Optional[float] = None) -> list[DeviceState]:
        max_age = settings.device_online_window_s if max_age_s is None else max_age_s
        now = datetime.now(timezone.utc)
        out = []
        for st in self._states.values():
            if st.umkm_id != umkm_id or st.last_seen_utc is None:
                continue
            if (now - st.last_seen_utc).total_seconds() <= max_age:
                out.append(st)
        return out

    def _lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._init_lock is None or self._init_loop is not loop:
            self._init_lock = asyncio.Lock()
            self._init_loop = loop
        return self._init_lock

    async def _machine_caps(self, db: AsyncSession, umkm_id: int) -> dict[str, int]:
        result = await db.execute(
            select(MachineProfile.appliance_class, func.count(MachineProfile.id))
            .where(MachineProfile.umkm_id == umkm_id)
            .group_by(MachineProfile.appliance_class)
        )
        caps: dict[str, int] = {}
        for cls, n in result.all():
            label = APPLIANCE_LABELS.get(int(cls))
            if label and int(cls) != 0:
                caps[label] = int(n)
        return caps

    async def get_state(self, db: AsyncSession, device: Device) -> DeviceState:
        st = self._states.get(device.device_id)
        if st is not None and st.umkm_id == device.umkm_id:
            return st
        async with self._lock():
            st = self._states.get(device.device_id)
            if st is not None and st.umkm_id == device.umkm_id:
                return st
            caps = await self._machine_caps(db, device.umkm_id)
            st = DeviceState(
                device_id=device.device_id,
                umkm_id=device.umkm_id,
                disaggregator=new_disaggregator(caps),
            )
            await self._reconstruct(db, st)
            self._states[device.device_id] = st
            return st

    async def _reconstruct(self, db: AsyncSession, st: DeviceState) -> None:
        last = await db.scalar(
            select(TelemetryRecord)
            .where(TelemetryRecord.device_id == st.device_id)
            .order_by(TelemetryRecord.ts.desc())
            .limit(1)
        )
        if last is None:
            return
        last_local = to_local(last.ts)
        hour_start = last_local.replace(minute=0, second=0, microsecond=0)
        result = await db.execute(
            select(TelemetryRecord)
            .where(
                TelemetryRecord.device_id == st.device_id,
                TelemetryRecord.ts >= hour_start.astimezone(timezone.utc),
            )
            .order_by(TelemetryRecord.ts)
        )
        n = 0
        # Sampel tersimpan berjarak ~telemetry_raw_keep_every_s (bisa sedikit lebih,
        # mis. 10–11 s). Selama replay, Δt maksimum dilonggarkan agar energi tidak
        # terpotong (tanpa ini jam replay kurang ±5 %); setelahnya dikembalikan.
        dis = st.disaggregator
        normal_gap = dis.max_gap_s
        dis.max_gap_s = max(normal_gap, replay_max_gap_s())
        try:
            for rec in result.scalars():
                local = to_local(rec.ts)
                dis.push(to_nilm_sample(rec, local))
                n += 1
        finally:
            dis.max_gap_s = normal_gap
        st.last_ts = last_local
        st.last_kept_ts = last_local
        st.replayed_records = n
        if n:
            logger.info("Disaggregator %s direkonstruksi dari %d sampel tersimpan.", st.device_id, n)

    # ── proses ──────────────────────────────────────────────────────────────
    @staticmethod
    def _should_keep(st: DeviceState, ts: datetime, has_event: bool) -> bool:
        if has_event or st.last_kept_ts is None:
            return True
        prev = st.last_kept_ts
        if (ts.date(), ts.hour) != (prev.date(), prev.hour):
            return True
        return (ts - prev).total_seconds() >= max(0, settings.telemetry_raw_keep_every_s)

    async def ingest(
        self, db: AsyncSession, device: Device, samples: Sequence[TelemetrySampleIn]
    ) -> IngestResult:
        st = await self.get_state(db, device)
        res = IngestResult(device_id=device.device_id, umkm_id=device.umkm_id, received=len(samples))
        ordered = sorted(((to_local(s.timestamp), s) for s in samples), key=lambda x: x[0])

        async with st.lock:
            dis = st.disaggregator
            snapshot = (
                copy.deepcopy(dis, memo={id(dis.classifier): dis.classifier}),
                st.last_ts,
                st.last_kept_ts,
                list(st.pending_ledger),
            )
            try:
                for ts, s in ordered:
                    if st.last_ts is not None and ts <= st.last_ts:
                        res.duplicates += 1
                        continue
                    sample = to_nilm_sample(s, ts)
                    update = dis.push(sample)
                    has_event = update.event is not None and update.classification is not None
                    keep = self._should_keep(st, ts, has_event)
                    if keep:
                        db.add(
                            TelemetryRecord(
                                device_id=device.device_id,
                                ts=ts,
                                v_rms=sample.v_rms,
                                i_rms=sample.i_rms,
                                p_active=sample.p_active,
                                q_reactive=sample.q_reactive,
                                frequency=sample.frequency,
                            )
                        )
                        st.last_kept_ts = ts
                        res.stored_records += 1
                    if has_event and update.classification.appliance_class != 0:
                        ev, cl = update.event, update.classification
                        db.add(
                            ApplianceEvent(
                                umkm_id=device.umkm_id,
                                device_id=device.device_id,
                                ts=ev.timestamp,
                                event_type=ev.event_type,
                                appliance_class=int(cl.appliance_class),
                                label=cl.label[:80],
                                delta_p=float(ev.delta_p),
                                confidence=float(cl.confidence),
                                source=str(cl.source)[:32],
                            )
                        )
                    if has_event:
                        res.events.append(event_fields(update.event, update.classification))
                    st.last_ts = ts
                    st.pending_ledger.extend(dis.pop_hourly_energy())
                    res.processed += 1
                    res.first_ts = res.first_ts or ts
                    res.last_ts = ts
                    res.last_sample = sample
                    res.last_update = update
                    res.last_stored = keep

                res.ledger_rows_written = await upsert_ledger(db, device.umkm_id, st.pending_ledger)
                await db.commit()
            except BaseException:
                st.disaggregator, st.last_ts, st.last_kept_ts, st.pending_ledger = snapshot
                try:
                    await db.rollback()
                except Exception:  # noqa: BLE001
                    logger.exception("Rollback gagal")
                raise
            st.pending_ledger.clear()
            if res.last_update is not None:
                st.last_update = res.last_update
            st.last_seen_utc = datetime.now(timezone.utc)

        self._broadcast(res)
        return res

    @staticmethod
    def _broadcast(res: IngestResult) -> None:
        if res.last_sample is None or res.last_update is None:
            return
        msg = build_message(
            device_id=res.device_id,
            umkm_id=res.umkm_id,
            sample=res.last_sample,
            update=res.last_update,
            simulated=False,
        )
        if res.processed > 1:
            msg["batch"] = {"processed": res.processed, "events": res.events[-20:]}
        try:
            hub.publish(res.umkm_id, msg)
        except Exception:  # noqa: BLE001
            logger.exception("Siaran live gagal (data tetap tersimpan)")


ingest_service = IngestService()


def summarize_active(states: Sequence[DeviceState]) -> dict[str, tuple[float, Optional[datetime]]]:
    """Gabungan mesin aktif dari beberapa perangkat: label → (watt, waktu sampel)."""
    out: dict[str, list] = defaultdict(lambda: [0.0, None])
    for st in states:
        if st.last_update is None:
            continue
        for label, w in st.last_update.active.items():
            acc = out[label]
            acc[0] += float(w)
            acc[1] = max(filter(None, [acc[1], st.last_ts]), default=None)
    return {k: (v[0], v[1]) for k, v in out.items()}

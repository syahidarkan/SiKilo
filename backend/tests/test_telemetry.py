"""Tes telemetri lapangan: ingest ber-auth, penyimpanan, ledger, status mesin, WebSocket."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.tariff import tariff_idr_per_kwh
from app.models import ApplianceEvent, EnergyLedger, TelemetryRecord
from app.nilm.disaggregator import HourlyEnergy
from app.schemas.telemetry import local_tz
from app.services_data.ingest import ingest_service
from app.services_data.ledger import aggregate_entries, upsert_ledger
from app.services_data.live import hub

WIB = local_tz()


def _sample(ts: datetime, p: float, q: float | None = None, with_id: str | None = None) -> dict:
    q = p * 0.1 if q is None else q
    body = {
        "timestamp": ts.isoformat(),
        "v_rms": 220.0,
        "i_rms": round(p / 220.0, 3),
        "p_active": p,
        "q_reactive": q,
        "frequency": 50.0,
    }
    if with_id:
        body["device_id"] = with_id
    return body


def _series(start: datetime, seconds: int, on_at: int | None = None, off_at: int | None = None,
            base_p: float = 300.0, step_p: float = 1200.0, step_q: float = 36.0) -> list[dict]:
    """Seri 1 Hz: baseload + satu beban resistif (mirip setrika) ON/OFF."""
    out = []
    for i in range(seconds):
        p, q = base_p, base_p * 0.3
        if on_at is not None and on_at <= i and (off_at is None or i < off_at):
            p += step_p
            q += step_q
        out.append(_sample(start + timedelta(seconds=i), p, q))
    return out


def _expected_kwh_by_hour(samples: list[dict]) -> dict[tuple[date, int], float]:
    out: dict[tuple[date, int], float] = {}
    prev = None
    for s in samples:
        ts = datetime.fromisoformat(s["timestamp"]).astimezone(WIB)
        if prev is not None:
            dt = min((ts - prev).total_seconds(), 10.0)
            key = (ts.date(), ts.hour)
            out[key] = out.get(key, 0.0) + s["p_active"] * dt / 3.6e6
        prev = ts
    return out


def _post_batches(client, dev, samples: list[dict], size: int = 500) -> list[dict]:
    out = []
    for i in range(0, len(samples), size):
        r = client.post(
            "/api/v1/telemetry/ingest-batch",
            json={"device_id": dev.device_id, "samples": samples[i:i + size]},
            headers=dev.headers,
        )
        assert r.status_code == 200, r.text
        out.append(r.json())
    return out


def _ledger_rows(db_call, umkm_id: int):
    async def q(s):
        res = await s.execute(select(EnergyLedger).where(EnergyLedger.umkm_id == umkm_id))
        return list(res.scalars())
    return db_call(q)


def _count(db_call, model, *where):
    async def q(s):
        return await s.scalar(select(func.count()).select_from(model).where(*where))
    return db_call(q)


# ── Auth & validasi ─────────────────────────────────────────────────────────
def test_ingest_requires_device_key(client, device):
    body = _sample(datetime(2026, 10, 1, 9, 0, tzinfo=WIB), 300.0, with_id=device.device_id)
    assert client.post("/api/v1/telemetry/ingest", json=body).status_code == 401
    r = client.post("/api/v1/telemetry/ingest", json=body, headers={"X-Device-Key": "salah"})
    assert r.status_code == 401


def test_ingest_rejects_mismatched_device_id(client, device):
    body = _sample(datetime(2026, 10, 1, 9, 0, tzinfo=WIB), 300.0, with_id="PERANGKAT-LAIN")
    r = client.post("/api/v1/telemetry/ingest", json=body, headers=device.headers)
    assert r.status_code == 403


def test_ingest_validation(client, device):
    ok = _sample(datetime(2026, 10, 1, 9, 0, tzinfo=WIB), 300.0, with_id=device.device_id)
    neg = dict(ok, p_active=-5.0)
    assert client.post("/api/v1/telemetry/ingest", json=neg, headers=device.headers).status_code == 422
    future = dict(ok, timestamp=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert client.post("/api/v1/telemetry/ingest", json=future, headers=device.headers).status_code == 422
    zero = dict(ok, p_active=0.0)
    assert client.post("/api/v1/telemetry/ingest", json=zero, headers=device.headers).status_code == 200


def test_naive_timestamp_is_wib_and_stored(client, device, db_call):
    body = _sample(datetime(2026, 10, 2, 10, 0, 0), 450.0, with_id=device.device_id)  # naive
    assert "+" not in body["timestamp"]
    r = client.post("/api/v1/telemetry/ingest", json=body, headers=device.headers)
    assert r.status_code == 200, r.text
    assert r.json()["stored"] is True

    async def q(s):
        return await s.scalar(select(TelemetryRecord).where(TelemetryRecord.device_id == device.device_id))
    rec = db_call(q)
    assert rec.ts == datetime(2026, 10, 2, 3, 0, 0, tzinfo=timezone.utc)
    assert rec.p_active == 450.0


def test_batch_limit_and_empty(client, device):
    start = datetime(2026, 10, 3, 8, 0, tzinfo=WIB)
    too_many = [_sample(start + timedelta(seconds=i), 300.0) for i in range(501)]
    r = client.post("/api/v1/telemetry/ingest-batch", json={"device_id": device.device_id, "samples": too_many},
                    headers=device.headers)
    assert r.status_code == 422
    r = client.post("/api/v1/telemetry/ingest-batch", json={"device_id": device.device_id, "samples": []},
                    headers=device.headers)
    assert r.status_code == 422


# ── Alur penuh: simpan, event, ledger ───────────────────────────────────────
def test_full_flow_ledger_events_and_downsampling(client, device, db_call):
    start = datetime(2026, 10, 5, 9, 50, 0, tzinfo=WIB)
    samples = _series(start, 11 * 60 + 30, on_at=120, off_at=420)  # 09:50:00 → 10:01:29
    # kirim dengan urutan acak di dalam batch → server mengurutkan
    first = samples[:500]
    first_shuffled = first[250:] + first[:250]
    r = client.post("/api/v1/telemetry/ingest-batch", json={"device_id": device.device_id, "samples": first_shuffled},
                    headers=device.headers)
    assert r.status_code == 200, r.text
    assert r.json()["processed"] == 500
    _post_batches(client, device, samples[500:])

    # Downsampling: kira-kira 1 per 10 detik (+ sampel event & awal jam).
    n_rec = _count(db_call, TelemetryRecord, TelemetryRecord.device_id == device.device_id)
    assert len(samples) // 10 <= n_rec <= len(samples) // 10 + 15

    # Event mesin tersimpan.
    n_ev = _count(db_call, ApplianceEvent, ApplianceEvent.umkm_id == device.umkm_id)
    assert n_ev >= 1

    # Jam 09 sudah selesai → masuk ledger; konservasi energi; biaya dari tariff.py.
    rows = [r for r in _ledger_rows(db_call, device.umkm_id) if r.hour == 9]
    assert rows, "ledger jam 09 harus terisi"
    expected = _expected_kwh_by_hour(samples)[(date(2026, 10, 5), 9)]
    total = sum(r.kwh for r in rows)
    assert total == pytest.approx(expected, rel=1e-6)
    for r in rows:
        assert r.cost_idr == pytest.approx(r.kwh * tariff_idr_per_kwh(9), rel=1e-9)
    labels = {r.appliance_label for r in rows}
    assert "Baseload / Background" in labels
    assert len(labels) >= 2, labels
    # Jam 10 belum selesai → belum ada di ledger.
    assert not [r for r in _ledger_rows(db_call, device.umkm_id) if r.hour == 10]

    # Kiriman ulang (duplikat) tidak mengubah ledger.
    resend = _post_batches(client, device, samples[:500])
    assert resend[0]["processed"] == 0 and resend[0]["skipped_duplicates"] == 500
    assert sum(r.kwh for r in _ledger_rows(db_call, device.umkm_id) if r.hour == 9) == pytest.approx(total)


def test_restart_reconstruction_no_double_count(client, device, db_call):
    start = datetime(2026, 10, 6, 13, 0, 0, tzinfo=WIB)
    samples = _series(start, 20 * 60, on_at=200, off_at=900)  # 13:00:00 → 13:19:59
    _post_batches(client, device, samples[:600])
    ingest_service.forget(device.device_id)  # simulasi server restart
    _post_batches(client, device, samples[600:])
    st = ingest_service.state(device.device_id)
    assert st is not None and st.replayed_records > 0
    # tutup jam 13
    nxt = _sample(datetime(2026, 10, 6, 14, 0, 1, tzinfo=WIB), 300.0, with_id=device.device_id)
    assert client.post("/api/v1/telemetry/ingest", json=nxt, headers=device.headers).status_code == 200

    total = sum(r.kwh for r in _ledger_rows(db_call, device.umkm_id) if r.day == date(2026, 10, 6) and r.hour == 13)
    expected = _expected_kwh_by_hour(samples)[(date(2026, 10, 6), 13)]
    # Rekonstruksi memakai sampel tersimpan (~10 s) → perkiraan, tetapi tidak ganda.
    assert total == pytest.approx(expected, rel=0.05)


def test_upsert_ledger_accumulates(client, umkm_user, db_call):
    d = date(2026, 9, 1)
    entries = [HourlyEnergy(d, 8, "Motor Jahit Induksi", 0.5), HourlyEnergy(d, 8, "Motor Jahit Induksi", 0.25)]
    assert aggregate_entries(entries)[(d, 8, "Motor Jahit Induksi")] == pytest.approx(0.75)

    async def write(s):
        n = await upsert_ledger(s, umkm_user.umkm_id, entries)
        await upsert_ledger(s, umkm_user.umkm_id, [HourlyEnergy(d, 8, "Motor Jahit Induksi", 0.25)])
        await s.commit()
        return n
    assert db_call(write) == 1
    rows = _ledger_rows(db_call, umkm_user.umkm_id)
    assert len(rows) == 1
    assert rows[0].kwh == pytest.approx(1.0)
    assert rows[0].cost_idr == pytest.approx(1.0 * tariff_idr_per_kwh(8))


# ── Ledger & status endpoint ────────────────────────────────────────────────
def _seed_ledger(db_call, umkm_id: int, day: date):
    async def write(s):
        await upsert_ledger(s, umkm_id, [
            HourlyEnergy(day, 9, "Setrika Pemanas Uap", 1.2),
            HourlyEnergy(day, 9, "Baseload / Background", 0.3),
            HourlyEnergy(day, 10, "Setrika Pemanas Uap", 0.6),
        ])
        await s.commit()
    db_call(write)


def test_ledger_endpoint_access_and_granularity(client, make_user, admin_headers, db_call):
    owner = make_user("umkm")
    other = make_user("umkm")
    private = make_user("umkm", consent_share_data=False)
    disp = make_user("disperinaker")
    day = date(2026, 9, 10)
    _seed_ledger(db_call, owner.umkm_id, day)
    _seed_ledger(db_call, private.umkm_id, day)
    params = {"start": day.isoformat(), "end": day.isoformat()}

    r = client.get("/api/v1/telemetry/ledger", params=params, headers=owner.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["umkm_id"] == owner.umkm_id
    assert body["total_kwh"] == pytest.approx(2.1)
    assert body["total_cost_idr"] == pytest.approx(
        1.5 * tariff_idr_per_kwh(9) + 0.6 * tariff_idr_per_kwh(10), rel=1e-6)
    assert len(body["rows"]) == 3 and body["rows"][0]["hour"] == 9
    top = body["per_appliance"][0]
    assert top["appliance_label"] == "Setrika Pemanas Uap" and top["kwh"] == pytest.approx(1.8)

    r = client.get("/api/v1/telemetry/ledger", params={**params, "granularity": "day"}, headers=owner.headers)
    rows = r.json()["rows"]
    assert {(x["appliance_label"], x["hour"]) for x in rows} == {("Setrika Pemanas Uap", None), ("Baseload / Background", None)}

    r = client.get("/api/v1/telemetry/ledger", params={**params, "umkm_id": owner.umkm_id}, headers=other.headers)
    assert r.status_code == 403
    assert client.get("/api/v1/telemetry/ledger", params=params, headers=admin_headers).status_code == 422
    r = client.get("/api/v1/telemetry/ledger", params={**params, "umkm_id": owner.umkm_id}, headers=admin_headers)
    assert r.status_code == 200
    # Disperinaker tidak membaca data rinci per UMKM (consent hanya mencakup bank/installer).
    r = client.get("/api/v1/telemetry/ledger", params={**params, "umkm_id": owner.umkm_id}, headers=disp.headers)
    assert r.status_code == 403
    r = client.get("/api/v1/telemetry/records", params={"umkm_id": owner.umkm_id}, headers=disp.headers)
    assert r.status_code == 403
    bank = make_user("bank")
    r = client.get("/api/v1/telemetry/ledger", params={**params, "umkm_id": owner.umkm_id}, headers=bank.headers)
    assert r.status_code == 200
    r = client.get("/api/v1/telemetry/ledger", params={**params, "umkm_id": private.umkm_id}, headers=bank.headers)
    assert r.status_code == 403
    bad = {"start": "2026-09-10", "end": "2026-09-01"}
    assert client.get("/api/v1/telemetry/ledger", params=bad, headers=owner.headers).status_code == 422


def test_appliance_status(client, device, db_call):
    owner = device.owner
    r = client.get("/api/v1/telemetry/appliances/status", headers=owner.headers)
    assert r.status_code == 200
    assert r.json()["appliances"] == []

    async def write(s):
        t0 = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)
        s.add_all([
            ApplianceEvent(umkm_id=device.umkm_id, device_id=device.device_id, ts=t0, event_type="ON",
                           appliance_class=3, label="Setrika Pemanas Uap", delta_p=1200, confidence=0.9, source="lgbm"),
            ApplianceEvent(umkm_id=device.umkm_id, device_id=device.device_id, ts=t0 + timedelta(minutes=5),
                           event_type="OFF", appliance_class=3, label="Setrika Pemanas Uap", delta_p=-1190,
                           confidence=0.9, source="lgbm"),
            ApplianceEvent(umkm_id=device.umkm_id, device_id=device.device_id, ts=t0 + timedelta(minutes=6),
                           event_type="ON", appliance_class=1, label="Motor Jahit Induksi", delta_p=300,
                           confidence=0.8, source="lgbm"),
        ])
        await s.commit()
    db_call(write)
    body = client.get("/api/v1/telemetry/appliances/status", headers=owner.headers).json()
    assert body["live"] is False
    states = {a["label"]: a for a in body["appliances"]}
    assert states["Setrika Pemanas Uap"]["state"] == "OFF"
    assert states["Motor Jahit Induksi"]["state"] == "ON"
    assert states["Motor Jahit Induksi"]["p_estimate_w"] == pytest.approx(300)


def test_records_endpoint(client, device):
    now = datetime.now(WIB).replace(microsecond=0) - timedelta(minutes=5)
    _post_batches(client, device, [_sample(now + timedelta(seconds=i), 300.0) for i in range(30)])
    r = client.get("/api/v1/telemetry/records", params={"minutes": 30}, headers=device.owner.headers)
    assert r.status_code == 200
    recs = r.json()
    assert 2 <= len(recs) <= 5
    assert all(x["device_id"] == device.device_id for x in recs)
    # live status setelah ingest baru
    body = client.get("/api/v1/telemetry/appliances/status", headers=device.owner.headers).json()
    assert body["live"] is True


# ── WebSocket ───────────────────────────────────────────────────────────────
def _ws_auth(ws, token: str) -> dict:
    ws.send_json({"type": "auth", "token": token})
    return ws.receive_json()


def test_ws_requires_token(client, umkm_user):
    # Pesan pertama bukan auth → ditolak.
    with client.websocket_connect("/ws/telemetry") as ws:
        ws.send_json({"type": "ping"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        with pytest.raises(Exception):
            ws.receive_json()
    with client.websocket_connect("/ws/telemetry") as ws:
        assert _ws_auth(ws, "palsu")["type"] == "error"
    # Token di query string tidak diterima lagi (URL tercatat di log akses).
    with client.websocket_connect(f"/ws/telemetry?token={umkm_user.token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error" and "query" in msg["detail"]


def test_ws_live_rejects_third_party_role(client, installer_user):
    with client.websocket_connect("/ws/telemetry") as ws:
        msg = _ws_auth(ws, installer_user.token)
        assert msg["type"] == "error"


def test_ws_closes_when_user_deactivated(client, make_user, admin_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ws_auth_recheck_s", 0.2)
    u = make_user("umkm")
    with client.websocket_connect("/ws/telemetry") as ws:
        assert _ws_auth(ws, u.token)["type"] == "hello"
        r = client.patch(f"/api/v1/auth/users/{u.id}/status", json={"is_active": False}, headers=admin_headers)
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "error" and "nonaktif" in msg["detail"]


def test_ws_simulator_not_stored(client, umkm_user, db_call):
    before = _count(db_call, TelemetryRecord)
    with client.websocket_connect("/ws/telemetry?mode=simulator") as ws:
        assert _ws_auth(ws, umkm_user.token)["type"] == "hello"
        t0 = datetime(2026, 10, 7, 9, 0, tzinfo=WIB)
        for i in range(5):
            ws.send_json(_sample(t0 + timedelta(seconds=i), 300.0, with_id="SIM-1"))
            msg = ws.receive_json()
            assert msg["simulated"] is True and msg["type"] == "telemetry"
        ws.send_text("bukan json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"
    assert _count(db_call, TelemetryRecord) == before


def test_ws_live_receives_broadcast(client, device):
    owner = device.owner
    subs_before = hub.subscriber_count
    with client.websocket_connect("/ws/telemetry") as ws:
        hello = _ws_auth(ws, owner.token)
        assert hello["type"] == "hello" and hello["umkm_id"] == owner.umkm_id
        body = _sample(datetime(2026, 10, 8, 9, 0, tzinfo=WIB), 555.0, with_id=device.device_id)
        assert client.post("/api/v1/telemetry/ingest", json=body, headers=device.headers).status_code == 200
        got = []
        for _ in range(3):
            ws.send_json({"type": "ping"})
            while True:
                m = ws.receive_json()
                if m["type"] == "pong":
                    break
                got.append(m)
            if got:
                break
        assert got, "siaran live tidak diterima"
        assert got[0]["simulated"] is False
        assert got[0]["device_id"] == device.device_id
        assert got[0]["p_active"] == pytest.approx(555.0)
    assert hub.subscriber_count == subs_before


# ── Batch: timestamp masa depan dibuang per sampel ─────────────────────────
def test_batch_drops_only_future_samples(client, device):
    base = datetime.now(WIB).replace(microsecond=0) - timedelta(minutes=30)
    samples = [_sample(base + timedelta(seconds=i), 300.0) for i in range(20)]
    future = datetime.now(timezone.utc) + timedelta(days=1)
    samples += [_sample(future + timedelta(seconds=i), 300.0) for i in range(3)]
    r = client.post(
        "/api/v1/telemetry/ingest-batch",
        json={"device_id": device.device_id, "samples": samples},
        headers=device.headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["received"] == 23
    assert body["rejected_future"] == 3
    assert body["processed"] == 20
    assert "masa depan" in body["message"]


# ── Cakupan ledger: jam tanpa konsumsi tetap tercatat ──────────────────────
def test_zero_consumption_hours_count_as_coverage(client, make_user, db_call):
    from app.services_data.ledger import aggregate_entries, hourly_profiles

    d = date(2026, 9, 20)
    agg = aggregate_entries([
        HourlyEnergy(d, 2, "Baseload / Background", 0.0),
        HourlyEnergy(d, 2, "Setrika Pemanas Uap", 0.0),
    ])
    assert agg == {(d, 2, "Baseload / Background"): 0.0}

    u = make_user("umkm")

    async def write(s):
        entries = [HourlyEnergy(d, h, "Baseload / Background", 0.0 if h < 6 else 0.4) for h in range(24)]
        await upsert_ledger(s, u.umkm_id, entries)
        await s.commit()
        return await hourly_profiles(s, u.umkm_id, d, d)

    profiles = db_call(write)
    assert len(profiles) == 1 and profiles[0][0] == d
    assert sum(profiles[0][1]) == pytest.approx(18 * 0.4)

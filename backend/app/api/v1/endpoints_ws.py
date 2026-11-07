"""
WebSocket ``/ws/telemetry`` — kanal LIVE dashboard WASKITA.

Sambung: ``ws://<host>/ws/telemetry?token=<JWT>&mode=live|simulator[&umkm_id=N]``

- ``mode=live`` (default): server menyiarkan hasil ingest perangkat
  (``type: "telemetry"``, ``simulated: false``) untuk UMKM pengguna.
  Role umkm → UMKM miliknya; admin → ``umkm_id`` tertentu atau semua bila kosong.
- ``mode=simulator``: tidak berlangganan siaran; hanya memproses sampel kiriman klien.
- Di mode mana pun klien boleh mengirim sampel JSON (field seperti
  ``TelemetryPayload``; ``device_id`` opsional). Sampel itu diproses NILM di
  disaggregator milik koneksi ini, dibalas dengan ``simulated: true``, dan
  TIDAK disimpan / tidak masuk ledger.
- ``{"type": "ping"}`` → ``{"type": "pong"}``.

Kode penutupan: 4401 token tidak ada/tidak valid, 4403 tidak berhak, 1009 pesan terlalu besar.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError
from pydantic import ValidationError

from app.core.auth import decode_access_token, get_user_by_username
from app.core.database import AsyncSessionLocal
from app.models import Role, User
from app.schemas.telemetry import TelemetrySampleIn, local_tz
from app.services_data.ingest import build_message, new_disaggregator, to_nilm_sample
from app.services_data.live import Subscription, hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["WebSocket"])

MAX_MESSAGE_BYTES = 8 * 1024
LIVE_ROLES = (Role.UMKM.value, Role.ADMIN.value)


async def _authenticate(token: Optional[str]) -> tuple[Optional[User], Optional[tuple[int, str]]]:
    if not token:
        return None, (4401, "Token wajib diisi (query ?token=)")
    try:
        payload = decode_access_token(token)
    except JWTError:
        return None, (4401, "Token tidak valid atau kedaluwarsa")
    username = payload.get("sub")
    if not username:
        return None, (4401, "Token tidak valid")
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, username)
    if user is None:
        return None, (4401, "Pengguna tidak ditemukan")
    if not user.is_active:
        return None, (4403, "Akun dinonaktifkan")
    return user, None


def _live_scope(user: User, umkm_id: Optional[int]) -> tuple[Optional[int], Optional[tuple[int, str]]]:
    """UMKM yang boleh disiarkan ke user ini (None = semua, khusus admin)."""
    if user.role == Role.ADMIN.value:
        return umkm_id, None
    if user.role == Role.UMKM.value:
        if user.umkm_id is None:
            return None, (4403, "Akun ini belum terhubung ke UMKM")
        if umkm_id is not None and umkm_id != user.umkm_id:
            return None, (4403, "Anda tidak memiliki akses ke UMKM ini")
        return user.umkm_id, None
    return None, (4403, "Kanal live hanya untuk pemilik UMKM dan admin; gunakan mode=simulator")


async def _reject(websocket: WebSocket, code: int, detail: str) -> None:
    try:
        await websocket.send_json({"type": "error", "detail": detail})
        await websocket.close(code=code)
    except Exception:  # noqa: BLE001
        pass


def _parse_int(raw: Optional[str]) -> Optional[int]:
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return -1


@router.websocket("/telemetry")
async def ws_telemetry(websocket: WebSocket) -> None:
    await websocket.accept()
    params = websocket.query_params
    mode = (params.get("mode") or "live").lower()
    if mode not in ("live", "simulator"):
        await _reject(websocket, 1008, "mode harus 'live' atau 'simulator'")
        return

    user, err = await _authenticate(params.get("token"))
    if err:
        await _reject(websocket, *err)
        return
    assert user is not None

    sub: Optional[Subscription] = None
    umkm_scope: Optional[int] = None
    if mode == "live":
        req_umkm = _parse_int(params.get("umkm_id"))
        umkm_scope, err = _live_scope(user, req_umkm)
        if err:
            await _reject(websocket, *err)
            return

    sim_disagg = None
    sender: Optional[asyncio.Task] = None
    try:
        if mode == "live":
            sub = hub.subscribe(umkm_scope)
            sender = asyncio.create_task(_pump(websocket, sub))
        await websocket.send_json(
            {
                "type": "hello",
                "mode": mode,
                "umkm_id": umkm_scope,
                "role": user.role,
                "server_time": datetime.now(local_tz()).isoformat(),
            }
        )
        while True:
            raw = await websocket.receive_text()
            if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
                await websocket.close(code=1009)
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "JSON tidak valid"})
                continue
            if not isinstance(data, dict):
                await websocket.send_json({"type": "error", "detail": "Pesan harus berupa objek JSON"})
                continue
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if "p_active" not in data:
                await websocket.send_json(
                    {"type": "error", "detail": "Pesan tidak dikenal; kirim sampel (p_active, …) atau ping"}
                )
                continue
            try:
                sample_in = TelemetrySampleIn.model_validate(data)
            except ValidationError as exc:
                await websocket.send_json(
                    {"type": "error", "detail": "Sampel tidak valid", "errors": _short_errors(exc)}
                )
                continue
            if sim_disagg is None:
                sim_disagg = new_disaggregator()
            sample = to_nilm_sample(sample_in)
            update = sim_disagg.push(sample)
            sim_disagg.pop_hourly_energy()  # buang; simulasi tidak disimpan
            await websocket.send_json(
                build_message(
                    device_id=str(data.get("device_id") or "SIMULATOR")[:64],
                    umkm_id=None,
                    sample=sample,
                    update=update,
                    simulated=True,
                )
            )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("Kesalahan WebSocket telemetri")
        try:
            await websocket.close(code=1011)
        except Exception:  # noqa: BLE001
            pass
    finally:
        hub.unsubscribe(sub)
        if sender is not None:
            sender.cancel()
            try:
                await sender
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


async def _pump(websocket: WebSocket, sub: Subscription) -> None:
    """Kirim pesan dari antrean langganan ke klien sampai koneksi ditutup."""
    while True:
        message: dict[str, Any] = await sub.queue.get()
        await websocket.send_json(message)


def _short_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()[:5]]

"""
Registrasi & manajemen perangkat ukur (ESP32).

- ``POST /devices``                       — admin/installer; mengembalikan API key SEKALI.
- ``GET  /devices``                       — admin (semua, filter ``umkm_id``), installer (hanya UMKM
  yang ditugaskan kepadanya), umkm (miliknya sendiri).
- ``POST /devices/{device_id}/rotate-key`` — admin/installer; key lama langsung tidak berlaku.

Installer hanya boleh mendaftarkan, melihat, dan memutar key perangkat milik
UMKM yang rujukannya (Lead) ditugaskan kepadanya dan statusnya bukan ``lost``.
Admin tidak dibatasi.
- ``GET  /devices/whoami``                — dipanggil firmware dengan ``X-Device-Key`` untuk cek key.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import generate_api_key, get_current_device, hash_api_key, require_roles
from app.core.database import get_db
from app.models import UMKM, Device, Role, User
from app.schemas.devices import DeviceCreate, DeviceOut, DeviceWithKey
from app.services_data.ledger import ensure_installer_assigned, installer_umkm_ids

router = APIRouter(prefix="/devices", tags=["Devices"])

_MANAGERS = ("admin", "installer")


def _with_key(device: Device, api_key: str) -> DeviceWithKey:
    return DeviceWithKey(**DeviceOut.model_validate(device).model_dump(), api_key=api_key)


async def _get_device_or_404(db: AsyncSession, device_id: str) -> Device:
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perangkat tidak ditemukan")
    return device


@router.post("", response_model=DeviceWithKey, status_code=status.HTTP_201_CREATED)
async def register_device(
    req: DeviceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*_MANAGERS)),
) -> DeviceWithKey:
    if await db.get(UMKM, req.umkm_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UMKM tidak ditemukan")
    await ensure_installer_assigned(db, user, req.umkm_id)
    existing = await db.execute(select(Device.id).where(Device.device_id == req.device_id))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device_id sudah terdaftar")

    api_key = generate_api_key()
    device = Device(
        device_id=req.device_id,
        umkm_id=req.umkm_id,
        api_key_hash=hash_api_key(api_key),
        firmware_version=req.firmware_version,
    )
    db.add(device)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device_id sudah terdaftar")
    await db.refresh(device)
    return _with_key(device, api_key)


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    umkm_id: Optional[int] = Query(None, description="Filter per UMKM (admin/installer)."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("admin", "installer", "umkm")),
) -> list[DeviceOut]:
    stmt = select(Device).order_by(Device.id)
    if user.role == Role.UMKM.value:
        if user.umkm_id is None or (umkm_id is not None and umkm_id != user.umkm_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Anda tidak memiliki akses ke UMKM ini")
        stmt = stmt.where(Device.umkm_id == user.umkm_id)
    elif user.role == Role.INSTALLER.value:
        allowed = await installer_umkm_ids(db, user)
        if umkm_id is not None:
            if umkm_id not in allowed:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="UMKM ini tidak ditugaskan kepada Anda")
            allowed = {umkm_id}
        stmt = stmt.where(Device.umkm_id.in_(sorted(allowed) or [-1]))
    elif umkm_id is not None:
        stmt = stmt.where(Device.umkm_id == umkm_id)
    result = await db.execute(stmt)
    return [DeviceOut.model_validate(d) for d in result.scalars().all()]


@router.get("/whoami", response_model=DeviceOut)
async def device_whoami(device: Device = Depends(get_current_device)) -> DeviceOut:
    return DeviceOut.model_validate(device)


@router.post("/{device_id}/rotate-key", response_model=DeviceWithKey)
async def rotate_device_key(
    device_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(*_MANAGERS)),
) -> DeviceWithKey:
    device = await _get_device_or_404(db, device_id)
    await ensure_installer_assigned(db, user, device.umkm_id)
    api_key = generate_api_key()
    device.api_key_hash = hash_api_key(api_key)
    await db.commit()
    await db.refresh(device)
    return _with_key(device, api_key)

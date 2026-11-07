"""
Profil UMKM, persetujuan berbagi data, verifikasi WhatsApp, dan profil mesin.

``{umkm_ref}`` = id UMKM, atau ``me`` untuk UMKM milik akun role ``umkm``.

- ``GET   /umkm/{ref}``                       — pemilik, admin, installer yang ditugaskan.
- ``PATCH /umkm/{ref}``                       — pemilik & admin (semua field);
  installer yang ditugaskan hanya ``pv_kwp``, ``battery_kwh``, ``connected_power_va``.
- ``POST  /umkm/me/phone/request-otp``        — kirim kode OTP ke nomor WA UMKM.
- ``POST  /umkm/me/phone/verify``             — verifikasi kode; nomor baru boleh dipakai mengirim.
- ``POST  /umkm/{id}/phone/mark-verified``    — admin (verifikasi di luar sistem).
- ``GET/POST /umkm/{ref}/machines``           — daftar/tambah profil mesin.
- ``PATCH/DELETE /umkm/{ref}/machines/{machine_id}``
- ``GET   /umkm/{ref}/machines/suggestions``  — usulan profil dari buku energi (NILM).

Profil mesin boleh dikelola pemilik, admin, dan installer yang ditugaskan
(lead aktif). Profil mesin dipakai brief WhatsApp, ``DailyPlan``, dan rapor.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_secret_key, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models import UMKM, EnergyLedger, MachineProfile, Role, User
from app.models.types import utcnow
from app.nilm.classifier import APPLIANCE_LABELS
from app.nilm.profiles import BASELOAD_LABEL
from app.schemas.auth import UMKMOut
from app.schemas.umkm import (
    TECH_FIELDS,
    MachineProfileBase,
    MachineProfileCreate,
    MachineProfileOut,
    MachineProfileUpdate,
    MachineSuggestion,
    MachineSuggestionResponse,
    PhoneOTPResponse,
    PhoneVerifyRequest,
    UMKMUpdate,
)
from app.services_data.ledger import ensure_installer_assigned, resolve_umkm

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/umkm", tags=["UMKM & Profil Mesin"])

_LABEL_TO_CLASS = {label: cls for cls, label in APPLIANCE_LABELS.items()}
MAX_MACHINES_PER_UMKM = 30


# ── akses ──────────────────────────────────────────────────────────────────
def _parse_ref(user: User, umkm_ref: str) -> Optional[int]:
    if umkm_ref == "me":
        if user.role != Role.UMKM.value:
            raise HTTPException(422, "'me' hanya untuk akun pemilik UMKM; isi id UMKM")
        return user.umkm_id
    try:
        return int(umkm_ref)
    except ValueError:
        raise HTTPException(422, "umkm harus berupa id angka atau 'me'")


async def _umkm_for(db: AsyncSession, user: User, umkm_ref: str, *, allow_installer: bool) -> UMKM:
    """Pemilik/admin lewat ``resolve_umkm``; installer hanya bila ditugaskan ke UMKM ini."""
    umkm_id = _parse_ref(user, umkm_ref)
    if user.role == Role.INSTALLER.value and allow_installer:
        if umkm_id is None:
            raise HTTPException(422, "Parameter umkm_id wajib diisi")
        await ensure_installer_assigned(db, user, umkm_id)
        umkm = await db.get(UMKM, umkm_id)
        if umkm is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "UMKM tidak ditemukan")
        return umkm
    return await resolve_umkm(db, user, umkm_id, share_roles=())


# ── profil UMKM ────────────────────────────────────────────────────────────
@router.get("/{umkm_ref}", response_model=UMKMOut)
async def get_umkm(
    umkm_ref: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> UMKMOut:
    return UMKMOut.model_validate(await _umkm_for(db, user, umkm_ref, allow_installer=True))


def _clear_phone_verification(umkm: UMKM) -> None:
    umkm.phone_verified_at = None
    umkm.phone_otp_hash = None
    umkm.phone_otp_expires_at = None
    umkm.phone_otp_sent_at = None
    umkm.phone_otp_attempts = 0


@router.patch("/{umkm_ref}", response_model=UMKMOut)
async def update_umkm(
    umkm_ref: str,
    req: UMKMUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> UMKMOut:
    data = req.model_dump(exclude_unset=True)
    if user.role == Role.INSTALLER.value:
        extra = sorted(set(data) - TECH_FIELDS)
        if extra:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Installer hanya dapat mengubah data teknis (pv_kwp, battery_kwh, connected_power_va); "
                f"ditolak: {', '.join(extra)}",
            )
    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)

    for key in ("name", "umkm_type", "address", "kecamatan"):
        if key in data and data[key] is not None:
            setattr(umkm, key, str(data[key]).strip())
    for key in ("connected_power_va", "pv_kwp", "battery_kwh"):
        if key in data:
            value = data[key]
            if value is None and key != "connected_power_va":
                continue
            setattr(umkm, key, value)
    if "whatsapp_opt_out" in data and data["whatsapp_opt_out"] is not None:
        umkm.whatsapp_opt_out = bool(data["whatsapp_opt_out"])
    if "phone_whatsapp" in data and data["phone_whatsapp"] is not None:
        new_phone = data["phone_whatsapp"] or None
        if new_phone != umkm.phone_whatsapp:
            umkm.phone_whatsapp = new_phone
            _clear_phone_verification(umkm)

    consent_changed = False
    withdrawn = False
    for key in ("consent_share_data", "consent_share_gov"):
        if key in data and data[key] is not None and bool(data[key]) != bool(getattr(umkm, key)):
            if not data[key]:
                withdrawn = True
            setattr(umkm, key, bool(data[key]))
            consent_changed = True
    if consent_changed:
        umkm.consent_updated_at = utcnow()
        logger.info("Persetujuan berbagi data UMKM %s diubah oleh user %s.", umkm.id, user.id)
    await db.commit()
    await db.refresh(umkm)
    # Rapor ter-cache tidak boleh lagi tersaji ke pihak ketiga setelah persetujuan dicabut.
    if withdrawn or {"connected_power_va"} & set(data):
        from app.services_data import rapor

        rapor.forget(umkm.id)
    return UMKMOut.model_validate(umkm)


# ── verifikasi nomor WhatsApp ──────────────────────────────────────────────
def _otp_hash(umkm_id: int, phone: str, code: str) -> str:
    key = get_secret_key().encode("utf-8")
    return hmac.new(key, f"{umkm_id}:{phone}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)


@router.post("/me/phone/request-otp", response_model=PhoneOTPResponse)
async def request_phone_otp(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm")),
) -> PhoneOTPResponse:
    from app.services.whatsapp_sender import send_whatsapp

    umkm = await resolve_umkm(db, user, None, share_roles=())
    if not umkm.phone_whatsapp:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nomor WhatsApp UMKM belum diisi.")
    if umkm.phone_verified_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nomor WhatsApp ini sudah terverifikasi.")
    now = datetime.now(timezone.utc)
    sent_at = _aware(umkm.phone_otp_sent_at)
    if sent_at is not None and (now - sent_at).total_seconds() < settings.whatsapp_otp_resend_interval_s:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Tunggu sebentar sebelum meminta kode baru.")
    provider = (settings.whatsapp_provider or "none").lower()
    if provider == "none" and settings.is_production:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Pengiriman WhatsApp belum dikonfigurasi server.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = now + timedelta(seconds=settings.whatsapp_otp_ttl_s)
    body = (
        f"Kode verifikasi WASKITA Anda: {code}\n"
        f"Berlaku {max(settings.whatsapp_otp_ttl_s // 60, 1)} menit. Jangan bagikan kode ini kepada siapa pun.\n"
        "Abaikan pesan ini bila Anda tidak mendaftar di WASKITA."
    )
    result = await send_whatsapp(umkm.phone_whatsapp, body)
    if result.status == "failed":
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Kode gagal dikirim: {result.error}")
    umkm.phone_otp_hash = _otp_hash(umkm.id, umkm.phone_whatsapp, code)
    umkm.phone_otp_expires_at = expires
    umkm.phone_otp_sent_at = now
    umkm.phone_otp_attempts = 0
    await db.commit()
    dev_code = code if (result.status == "skipped" and not settings.is_production) else None
    detail = (
        "Kode verifikasi dikirim ke WhatsApp UMKM."
        if result.status == "sent"
        else "WHATSAPP_PROVIDER=none: kode tidak dikirim; mode pengembangan menampilkan kode di respons."
    )
    return PhoneOTPResponse(
        status=result.status, provider=result.provider, expires_at=expires, detail=detail, dev_code=dev_code
    )


@router.post("/me/phone/verify", response_model=UMKMOut)
async def verify_phone(
    req: PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm")),
) -> UMKMOut:
    umkm = await resolve_umkm(db, user, None, share_roles=())
    if not umkm.phone_whatsapp or not umkm.phone_otp_hash:
        raise HTTPException(status.HTTP_409_CONFLICT, "Minta kode verifikasi terlebih dahulu.")
    expires = _aware(umkm.phone_otp_expires_at)
    if expires is None or datetime.now(timezone.utc) > expires:
        _clear_phone_verification(umkm)
        await db.commit()
        raise HTTPException(status.HTTP_410_GONE, "Kode sudah kedaluwarsa; minta kode baru.")
    if (umkm.phone_otp_attempts or 0) >= settings.whatsapp_otp_max_attempts:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Terlalu banyak percobaan; minta kode baru.")
    expected = umkm.phone_otp_hash
    if not hmac.compare_digest(expected, _otp_hash(umkm.id, umkm.phone_whatsapp, req.code)):
        umkm.phone_otp_attempts = (umkm.phone_otp_attempts or 0) + 1
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Kode verifikasi salah.")
    umkm.phone_verified_at = utcnow()
    umkm.phone_otp_hash = None
    umkm.phone_otp_expires_at = None
    umkm.phone_otp_attempts = 0
    await db.commit()
    await db.refresh(umkm)
    return UMKMOut.model_validate(umkm)


@router.post("/{umkm_id}/phone/mark-verified", response_model=UMKMOut)
async def admin_mark_phone_verified(
    umkm_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> UMKMOut:
    """Admin menandai nomor terverifikasi (mis. sudah dikonfirmasi langsung saat pemasangan)."""
    umkm = await db.get(UMKM, umkm_id)
    if umkm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "UMKM tidak ditemukan")
    if not umkm.phone_whatsapp:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nomor WhatsApp UMKM belum diisi.")
    umkm.phone_verified_at = utcnow()
    umkm.phone_otp_hash = None
    await db.commit()
    await db.refresh(umkm)
    return UMKMOut.model_validate(umkm)


# ── profil mesin ───────────────────────────────────────────────────────────
async def _machines(db: AsyncSession, umkm_id: int) -> list[MachineProfile]:
    result = await db.execute(
        select(MachineProfile).where(MachineProfile.umkm_id == umkm_id).order_by(MachineProfile.id)
    )
    return list(result.scalars().all())


async def _machine_or_404(db: AsyncSession, umkm_id: int, machine_id: str) -> MachineProfile:
    row = await db.scalar(
        select(MachineProfile).where(MachineProfile.umkm_id == umkm_id, MachineProfile.machine_id == machine_id)
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profil mesin tidak ditemukan")
    return row


async def _after_machine_change(db: AsyncSession, umkm_id: int) -> None:
    try:
        from app.services_data.ingest import ingest_service

        await ingest_service.refresh_machine_caps(db, umkm_id)
    except Exception:  # noqa: BLE001
        logger.exception("Gagal memperbarui batas unit mesin disaggregator UMKM %s.", umkm_id)


@router.get("/{umkm_ref}/machines", response_model=list[MachineProfileOut])
async def list_machines(
    umkm_ref: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> list[MachineProfileOut]:
    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)
    return [MachineProfileOut.model_validate(m) for m in await _machines(db, umkm.id)]


@router.post("/{umkm_ref}/machines", response_model=MachineProfileOut, status_code=status.HTTP_201_CREATED)
async def create_machine(
    umkm_ref: str,
    req: MachineProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> MachineProfileOut:
    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)
    existing = await _machines(db, umkm.id)
    if any(m.machine_id == req.machine_id for m in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, "machine_id sudah dipakai di UMKM ini")
    if len(existing) >= MAX_MACHINES_PER_UMKM:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Maksimal {MAX_MACHINES_PER_UMKM} profil mesin per UMKM")
    row = MachineProfile(umkm_id=umkm.id, **req.model_dump())
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "machine_id sudah dipakai di UMKM ini")
    await db.refresh(row)
    await _after_machine_change(db, umkm.id)
    return MachineProfileOut.model_validate(row)


@router.patch("/{umkm_ref}/machines/{machine_id}", response_model=MachineProfileOut)
async def update_machine(
    umkm_ref: str,
    machine_id: str,
    req: MachineProfileUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> MachineProfileOut:
    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)
    row = await _machine_or_404(db, umkm.id, machine_id)
    current = {k: getattr(row, k) for k in MachineProfileBase.model_fields}
    current.update(req.model_dump(exclude_unset=True))
    try:
        merged = MachineProfileBase(**current)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    for k, v in merged.model_dump().items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    await _after_machine_change(db, umkm.id)
    return MachineProfileOut.model_validate(row)


@router.delete("/{umkm_ref}/machines/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_machine(
    umkm_ref: str,
    machine_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> Response:
    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)
    row = await _machine_or_404(db, umkm.id, machine_id)
    await db.delete(row)
    await db.commit()
    await _after_machine_change(db, umkm.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _slug(label: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in label).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return (out or "mesin")[:56]


def suggest_from_ledger(
    rows: list[tuple[date, int, str, float]], existing_labels: set[str]
) -> list[MachineSuggestion]:
    """
    Usulan profil mesin dari kWh per jam per label (EnergyLedger, hasil NILM).

    - daya ≈ persentil-90 kWh per jam × 1000 (jam ketika mesin menyala penuh);
    - runtime/hari ≈ rata-rata kWh di jam kerja ÷ daya;
    - jam mulai kebiasaan ≈ median jam pertama menyala di jam kerja;
    - idle ≈ rata-rata kWh di luar jam kerja ÷ (default_idle_power_frac × daya).
    Semua PERKIRAAN; pemilik/installer wajib memeriksa sebelum disimpan.
    """
    per_label: dict[str, dict[date, dict[int, float]]] = defaultdict(lambda: defaultdict(dict))
    for d, h, label, kwh in rows:
        if label == BASELOAD_LABEL or kwh <= 0.01:
            continue
        per_label[label][d][int(h)] = per_label[label][d].get(int(h), 0.0) + float(kwh)
    start_h, end_h = settings.work_start_hour, settings.work_end_hour
    out: list[MachineSuggestion] = []
    for label, days in sorted(per_label.items()):
        hourly = sorted(v for hours in days.values() for v in hours.values())
        if not hourly:
            continue
        p90 = hourly[min(int(round(0.9 * (len(hourly) - 1))), len(hourly) - 1)]
        power_w = max(round(p90 * 1000.0, -1), 50.0)
        work_kwh = [sum(v for h, v in hours.items() if start_h <= h < end_h) for hours in days.values()]
        off_kwh = [sum(v for h, v in hours.items() if not (start_h <= h < end_h)) for hours in days.values()]
        firsts = [min(h for h in hours if start_h <= h < end_h) for hours in days.values()
                  if any(start_h <= h < end_h for h in hours)]
        window_min = (end_h - start_h) * 60
        runtime = int(min(round(statistics.mean(work_kwh) / power_w * 1000.0 * 60.0 / 15.0) * 15, window_min))
        idle_w = settings.default_idle_power_frac * power_w
        idle_min = int(min(round(statistics.mean(off_kwh) * 1000.0 / max(idle_w, 1.0) * 60.0 / 15.0) * 15, 240))
        out.append(
            MachineSuggestion(
                machine_id=_slug(label),
                label=label[:80],
                appliance_class=int(_LABEL_TO_CLASS.get(label, 0)),
                power_w=float(power_w),
                daily_runtime_minutes=max(runtime, 0),
                habit_start_hour=int(statistics.median(firsts)) if firsts else None,
                idle_minutes_habit=max(idle_min, 0),
                days_with_data=len(days),
                already_profiled=label in existing_labels,
                basis="perkiraan dari kWh per jam hasil NILM (belum divalidasi)",
            )
        )
    return out


@router.get("/{umkm_ref}/machines/suggestions", response_model=MachineSuggestionResponse)
async def machine_suggestions(
    umkm_ref: str,
    days: int = Query(14, ge=3, le=60),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("umkm", "admin", "installer")),
) -> MachineSuggestionResponse:
    """Usulan profil mesin dari buku energi; TIDAK disimpan otomatis."""
    from app.schemas.telemetry import local_tz

    umkm = await _umkm_for(db, user, umkm_ref, allow_installer=True)
    end = datetime.now(local_tz()).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    result = await db.execute(
        select(EnergyLedger.day, EnergyLedger.hour, EnergyLedger.appliance_label, EnergyLedger.kwh).where(
            EnergyLedger.umkm_id == umkm.id, EnergyLedger.day >= start, EnergyLedger.day <= end
        )
    )
    rows = [(d, h, label, float(k or 0.0)) for d, h, label, k in result.all()]
    existing = {m.label for m in await _machines(db, umkm.id)}
    return MachineSuggestionResponse(
        umkm_id=umkm.id,
        start=start.isoformat(),
        end=end.isoformat(),
        suggestions=suggest_from_ledger(rows, existing),
        note=(
            "Usulan dihitung dari energi per jam hasil disagregasi NILM (estimasi, bukan meter per mesin). "
            "Periksa daya, jam kerja, dan menit idle sebelum menyimpan lewat POST /umkm/{ref}/machines."
        ),
    )

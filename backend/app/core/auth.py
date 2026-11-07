"""
Autentikasi & otorisasi WASKITA.

Kontrak (docs/CONTRACTS.md §1):
- ``hash_password(plain)`` / ``verify_password(plain, hashed)`` — bcrypt langsung.
- ``create_access_token(data, expires_delta=None)`` — JWT HS256, ``sub`` = username.
- ``get_current_user`` — dependency FastAPI → ``User`` (aktif).
- ``require_roles(*roles)`` — dependency factory; TIDAK ada pengecualian
  otomatis untuk admin, sebutkan ``"admin"`` secara eksplisit bila perlu.
- ``get_current_device`` — dependency dari header ``X-Device-Key`` → ``Device``.

Tambahan:
- ``get_optional_user`` — seperti ``get_current_user`` tetapi ``None`` bila tanpa token.
- ``ensure_umkm_access(user, umkm_id, staff_roles=("admin",))`` — 403 bila user
  role ``umkm`` mengakses UMKM lain, atau role lain tidak ada di ``staff_roles``.
- ``generate_api_key()`` / ``hash_api_key(key)`` untuk perangkat.
- ``bootstrap_admin(db)`` — buat admin awal dari env (dipanggil di lifespan).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

import bcrypt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import ROLES, Device, Role, User

logger = logging.getLogger(__name__)

# bcrypt hanya memproses 72 byte pertama; lebih dari itu ditolak eksplisit.
BCRYPT_MAX_BYTES = 72
PASSWORD_MIN_LENGTH = 8
DEVICE_KEY_HEADER = "X-Device-Key"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Kunci rahasia JWT ───────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def get_secret_key() -> str:
    """
    Kunci penandatangan JWT dari ``settings.secret_key``.

    - production & kosong → RuntimeError (gagal start).
    - selain production & kosong → kunci acak per proses + warning
      (semua token hangus saat server restart).
    """
    key = settings.secret_key.strip()
    if key:
        if settings.is_production and len(key) < 32:
            logger.warning("SECRET_KEY kurang dari 32 karakter; gunakan kunci acak yang lebih panjang.")
        return key
    if settings.is_production:
        raise RuntimeError(
            "SECRET_KEY wajib diisi di production. Buat dengan: "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    logger.warning(
        "SECRET_KEY kosong: memakai kunci acak sementara. Token akan hangus saat "
        "server restart. Isi SECRET_KEY di .env untuk menghindarinya."
    )
    return secrets.token_urlsafe(48)


# ── Password ────────────────────────────────────────────────────────────────
def password_problem(plain: str) -> Optional[str]:
    """Kembalikan pesan kesalahan (Bahasa Indonesia) bila password tidak valid."""
    if len(plain) < PASSWORD_MIN_LENGTH:
        return f"Password minimal {PASSWORD_MIN_LENGTH} karakter."
    if len(plain.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return f"Password maksimal {BCRYPT_MAX_BYTES} byte (kurang lebih {BCRYPT_MAX_BYTES} huruf biasa)."
    return None


def hash_password(plain: str) -> str:
    raw = plain.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password melebihi {BCRYPT_MAX_BYTES} byte")
    return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    raw = plain.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES or not hashed:
        return False
    try:
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except ValueError:
        return False


# Hash dummy agar waktu respons login sama untuk username yang tidak ada.
_DUMMY_HASH = bcrypt.hashpw(b"waskita-dummy-password", bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode("ascii")


# ── JWT ─────────────────────────────────────────────────────────────────────
def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = dict(data)
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    to_encode.update({"exp": expire, "iat": now, "type": "access"})
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    return jwt.encode(to_encode, get_secret_key(), algorithm=settings.jwt_algorithm)


def create_user_token(user: User) -> str:
    return create_access_token({"sub": user.username, "role": user.role})


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, get_secret_key(), algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access":
        raise JWTError("jenis token salah")
    return payload


def _unauthorized(detail: str = "Tidak terautentikasi") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── User ────────────────────────────────────────────────────────────────────
def normalize_username(username: str) -> str:
    return username.strip().lower()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == normalize_username(username)))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, username: str, password: str) -> Optional[User]:
    user = await get_user_by_username(db, username)
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise _unauthorized("Token tidak valid atau kedaluwarsa")
    username = payload.get("sub")
    if not username:
        raise _unauthorized("Token tidak valid")
    user = await get_user_by_username(db, username)
    if user is None:
        raise _unauthorized("Pengguna tidak ditemukan")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Akun dinonaktifkan")
    return user


async def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise _unauthorized()
    return user


def require_roles(*roles: str) -> Callable[..., Any]:
    """
    Dependency factory: izinkan hanya role tertentu.

    Contoh: ``user: User = Depends(require_roles("admin", "installer"))``.
    Admin TIDAK otomatis lolos; tulis ``"admin"`` bila memang diizinkan.
    """
    unknown = set(roles) - set(ROLES)
    if unknown or not roles:
        raise ValueError(f"Role tidak dikenal: {sorted(unknown) or '(kosong)'}")
    allowed = frozenset(roles)

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Anda tidak memiliki akses ke fitur ini",
            )
        return user

    _dependency.__name__ = f"require_roles_{'_'.join(sorted(allowed))}"
    return _dependency


def ensure_umkm_access(user: User, umkm_id: int, staff_roles: Iterable[str] = (Role.ADMIN.value,)) -> None:
    """
    Pastikan ``user`` boleh mengakses data UMKM ``umkm_id``.

    - role ``umkm``: hanya UMKM miliknya sendiri.
    - role di ``staff_roles``: semua UMKM.
    - selain itu: 403. (Aturan persetujuan berbagi data untuk bank/installer
      diputuskan oleh endpoint pemanggil.)
    """
    if user.role == Role.UMKM.value:
        if user.umkm_id is not None and user.umkm_id == umkm_id:
            return
    elif user.role in set(staff_roles):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Anda tidak memiliki akses ke UMKM ini")


async def bootstrap_admin(db: AsyncSession) -> Optional[User]:
    """Buat akun admin awal bila BOOTSTRAP_ADMIN_USERNAME & _PASSWORD diisi."""
    username = normalize_username(settings.bootstrap_admin_username)
    password = settings.bootstrap_admin_password
    if not username and not password:
        return None
    if not username or not password:
        logger.warning("BOOTSTRAP_ADMIN_USERNAME dan BOOTSTRAP_ADMIN_PASSWORD harus diisi keduanya; admin awal tidak dibuat.")
        return None
    problem = password_problem(password)
    if problem:
        raise RuntimeError(f"BOOTSTRAP_ADMIN_PASSWORD tidak valid: {problem}")
    if settings.is_production and len(password) < 12:
        logger.warning("BOOTSTRAP_ADMIN_PASSWORD sebaiknya minimal 12 karakter di production.")

    existing = await get_user_by_username(db, username)
    if existing is not None:
        if existing.role != Role.ADMIN.value:
            logger.warning("Username bootstrap admin %r sudah dipakai user non-admin; dilewati.", username)
        return existing

    admin = User(
        username=username,
        hashed_password=hash_password(password),
        full_name="Administrator WASKITA",
        role=Role.ADMIN.value,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    logger.info("Akun admin awal %r dibuat.", username)
    return admin


# ── Perangkat (ESP32) ───────────────────────────────────────────────────────
def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """SHA-256 hex. Cukup untuk key acak 256-bit (bukan password manusia)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def get_current_device(
    x_device_key: Optional[str] = Header(default=None, alias=DEVICE_KEY_HEADER),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Autentikasi perangkat dari header ``X-Device-Key``; memperbarui ``last_seen``."""
    if not x_device_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Header {DEVICE_KEY_HEADER} wajib diisi")
    key_hash = hash_api_key(x_device_key.strip())
    result = await db.execute(select(Device).where(Device.api_key_hash == key_hash))
    device = result.scalar_one_or_none()
    if device is None or not hmac.compare_digest(device.api_key_hash, key_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key perangkat tidak valid")

    now = datetime.now(timezone.utc)
    interval = timedelta(seconds=max(0, settings.device_last_seen_update_interval_s))
    if device.last_seen is None or now - device.last_seen >= interval:
        device.last_seen = now
        await db.commit()
    return device

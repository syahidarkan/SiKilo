"""
Endpoint autentikasi WASKITA.

- ``POST /auth/login``      — OAuth2 password form → token JWT.
- ``POST /auth/register``   — pendaftaran publik, SELALU role ``umkm`` + record UMKM.
- ``GET  /auth/me``         — profil user yang sedang login.
- ``POST /auth/users``      — admin membuat user role apa pun.
- ``GET  /auth/users``      — admin melihat daftar user.
- ``PATCH /auth/users/{id}/status`` — admin mengaktifkan/menonaktifkan user.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    authenticate_user,
    create_user_token,
    get_current_user,
    get_user_by_username,
    hash_password,
    require_roles,
)
from app.core.config import settings
from app.core.database import get_db
from app.models import UMKM, Role, User
from app.schemas.auth import (
    AdminUserCreate,
    RegisterRequest,
    RoleName,
    TokenResponse,
    UMKMCreate,
    UserOut,
    UserStatusUpdate,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_user_token(user),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


def _umkm_from_schema(data: UMKMCreate) -> UMKM:
    return UMKM(
        name=data.name.strip(),
        umkm_type=data.umkm_type.strip() or "UMKM Umum",
        address=data.address.strip(),
        kecamatan=data.kecamatan.strip(),
        phone_whatsapp=data.phone_whatsapp,
        connected_power_va=data.connected_power_va,
        tariff_group=settings.tariff_group,
        consent_share_data=data.consent_share_data,
    )


async def _ensure_username_free(db: AsyncSession, username: str) -> None:
    if await get_user_by_username(db, username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username sudah digunakan")


async def _commit_user(db: AsyncSession, user: User) -> User:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username sudah digunakan")
    await db.refresh(user, attribute_names=["umkm"])
    return user


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await authenticate_user(db, form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Akun dinonaktifkan")
    return _token_response(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Daftar sebagai pemilik UMKM. Role lain hanya bisa dibuat oleh admin."""
    await _ensure_username_free(db, req.username)
    umkm = _umkm_from_schema(req.to_umkm())
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        email=str(req.email) if req.email else None,
        role=Role.UMKM.value,
        umkm=umkm,
        is_active=True,
    )
    db.add_all([umkm, user])
    user = await _commit_user(db, user)
    return _token_response(user)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: AdminUserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> UserOut:
    await _ensure_username_free(db, req.username)
    umkm: Optional[UMKM] = None
    if req.role == Role.UMKM.value:
        if req.umkm_id is not None:
            umkm = await db.get(UMKM, req.umkm_id)
            if umkm is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UMKM tidak ditemukan")
        else:
            assert req.umkm is not None
            umkm = _umkm_from_schema(req.umkm)
            db.add(umkm)
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        full_name=req.full_name.strip(),
        email=str(req.email) if req.email else None,
        role=req.role,
        umkm=umkm,
        is_active=True,
    )
    db.add(user)
    user = await _commit_user(db, user)
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    role: Optional[RoleName] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_roles("admin")),
) -> list[UserOut]:
    stmt = select(User).order_by(User.id).limit(limit).offset(offset)
    if role:
        stmt = stmt.where(User.role == role)
    result = await db.execute(stmt)
    return [UserOut.model_validate(u) for u in result.scalars().all()]


@router.patch("/users/{user_id}/status", response_model=UserOut)
async def set_user_status(
    user_id: int,
    req: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_roles("admin")),
) -> UserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User tidak ditemukan")
    if user.id == admin.id and not req.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin tidak bisa menonaktifkan akunnya sendiri")
    user.is_active = req.is_active
    await db.commit()
    await db.refresh(user, attribute_names=["umkm"])
    return UserOut.model_validate(user)

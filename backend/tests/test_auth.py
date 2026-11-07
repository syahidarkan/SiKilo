"""Tes platform inti: auth, role, perangkat, wiring aplikasi."""
from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core import auth as auth_mod
from app.core.config import settings
from app.models import UMKM, Device, User

API = "/api/v1"


# ── Unit: password & token ──────────────────────────────────────────────────
def test_hash_and_verify_password():
    hashed = auth_mod.hash_password("rahasia-123")
    assert hashed != "rahasia-123"
    assert auth_mod.verify_password("rahasia-123", hashed)
    assert not auth_mod.verify_password("salah-123", hashed)


def test_password_over_72_bytes_rejected():
    too_long = "a" * 73
    assert auth_mod.password_problem(too_long) is not None
    with pytest.raises(ValueError):
        auth_mod.hash_password(too_long)
    assert auth_mod.verify_password(too_long, auth_mod.hash_password("a" * 72)) is False
    # Karakter multibyte dihitung dalam byte, bukan huruf.
    assert auth_mod.password_problem("é" * 37) is not None  # 74 byte
    assert auth_mod.password_problem("é" * 36) is None  # 72 byte


def test_secret_key_comes_from_settings():
    assert auth_mod.get_secret_key() == settings.secret_key
    assert "nota-listrik" not in auth_mod.get_secret_key()


def test_secret_key_required_in_production(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "")
    monkeypatch.setattr(settings, "environment", "production")
    auth_mod.get_secret_key.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            auth_mod.get_secret_key()
    finally:
        auth_mod.get_secret_key.cache_clear()


def test_secret_key_random_in_development(monkeypatch, caplog):
    monkeypatch.setattr(settings, "secret_key", "")
    monkeypatch.setattr(settings, "environment", "development")
    auth_mod.get_secret_key.cache_clear()
    try:
        key = auth_mod.get_secret_key()
        assert len(key) >= 32
        assert "SECRET_KEY kosong" in caplog.text
    finally:
        auth_mod.get_secret_key.cache_clear()


def test_require_roles_rejects_unknown_role():
    with pytest.raises(ValueError):
        auth_mod.require_roles("superuser")


# ── Wiring aplikasi ─────────────────────────────────────────────────────────
def test_health_and_brand(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["routers"]["endpoints_auth"] == "ok"
    assert body["routers"]["endpoints_devices"] == "ok"
    openapi = client.get("/openapi.json").json()
    assert "WASKITA" in openapi["info"]["title"]
    assert "NOTA LISTRIK" not in openapi["info"].get("description", "")


def test_cors_does_not_allow_arbitrary_origin(client):
    resp = client.options(
        "/health",
        headers={"Origin": "https://jahat.example", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") not in ("*", "https://jahat.example")
    allowed = settings.cors_origins[0]
    resp = client.options("/health", headers={"Origin": allowed, "Access-Control-Request-Method": "GET"})
    assert resp.headers.get("access-control-allow-origin") == allowed


def test_no_default_admin_account(client):
    resp = client.post(f"{API}/auth/login", data={"username": "admin", "password": "admin123"})
    assert resp.status_code == 401


def test_tables_created(db_call):
    async def _count(session):
        return (await session.execute(select(User).where(User.role == "admin"))).scalars().all()

    admins = db_call(_count)
    assert any(u.username == "admin_uji" for u in admins)


# ── Register & login ────────────────────────────────────────────────────────
def test_register_creates_umkm_user_and_record(client, db_call):
    payload = {
        "username": "Pak_Budi_Konveksi",
        "password": "sandi-aman-123",
        "full_name": "Budi Santoso",
        "email": "budi@contoh.id",
        "umkm_name": "Konveksi Pak Budi",
        "umkm_type": "Konveksi",
        "address": "Jl. Veteran 12",
        "kecamatan": "Sukoharjo",
        "phone_whatsapp": "0812-3456-7890",
        "connected_power_va": 5500,
        "consent_share_data": True,
        "role": "admin",  # harus diabaikan
    }
    resp = client.post(f"{API}/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    user = body["user"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60
    assert user["role"] == "umkm"
    assert user["username"] == "pak_budi_konveksi"
    assert user["umkm_name"] == "Konveksi Pak Budi"
    assert user["umkm"]["phone_whatsapp"] == "6281234567890"
    assert user["umkm"]["connected_power_va"] == 5500
    assert user["umkm"]["consent_share_data"] is True
    assert user["umkm"]["tariff_group"] == settings.tariff_group
    assert "hashed_password" not in user

    async def _load(session):
        u = (await session.execute(select(User).where(User.username == "pak_budi_konveksi"))).scalar_one()
        m = await session.get(UMKM, u.umkm_id)
        return u, m

    db_user, db_umkm = db_call(_load)
    assert db_user.hashed_password.startswith("$2")
    assert db_umkm.kecamatan == "Sukoharjo"

    # Username sama (beda huruf besar/kecil) ditolak
    resp = client.post(f"{API}/auth/register", json={**payload, "username": "PAK_BUDI_KONVEKSI"})
    assert resp.status_code == 409

    # Login (username case-insensitive)
    resp = client.post(f"{API}/auth/login", data={"username": "Pak_Budi_Konveksi", "password": "sandi-aman-123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["umkm"]["name"] == "Konveksi Pak Budi"


@pytest.mark.parametrize(
    "override,fragment",
    [
        ({"password": "pendek"}, "minimal"),
        ({"password": "x" * 73}, "maksimal"),
        ({"phone_whatsapp": "12345"}, "WhatsApp"),
        ({"username": "a b"}, "Username"),
    ],
)
def test_register_validation(client, override, fragment):
    payload = {
        "username": "validasi_user",
        "password": "sandi-aman-123",
        "full_name": "Uji Validasi",
        "umkm_name": "UMKM Validasi",
    }
    payload.update(override)
    resp = client.post(f"{API}/auth/register", json=payload)
    assert resp.status_code == 422
    assert fragment in resp.text


def test_login_wrong_password(client, umkm_user):
    resp = client.post(f"{API}/auth/login", data={"username": umkm_user.username, "password": "salah-salah"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Username atau password salah"


def test_me_requires_valid_token(client):
    assert client.get(f"{API}/auth/me").status_code == 401
    resp = client.get(f"{API}/auth/me", headers={"Authorization": "Bearer bukan-token"})
    assert resp.status_code == 401


def test_expired_token_rejected(client, umkm_user):
    token = auth_mod.create_access_token({"sub": umkm_user.username}, expires_delta=timedelta(seconds=-5))
    resp = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ── Admin membuat user & role ───────────────────────────────────────────────
@pytest.mark.parametrize("role", ["disperinaker", "installer", "bank", "admin"])
def test_admin_creates_staff_roles(make_user, client, role):
    user = make_user(role)
    assert user.role == role
    assert user.umkm_id is None
    me = client.get(f"{API}/auth/me", headers=user.headers)
    assert me.json()["role"] == role


def test_non_admin_cannot_create_users(client, umkm_user, installer_user):
    payload = {"username": "penyusup", "password": "sandi-aman-123", "full_name": "X", "role": "admin"}
    for user in (umkm_user, installer_user):
        resp = client.post(f"{API}/auth/users", json=payload, headers=user.headers)
        assert resp.status_code == 403
    assert client.post(f"{API}/auth/users", json=payload).status_code == 401


def test_admin_creates_umkm_user_linked_to_existing(client, admin_headers, umkm_user):
    payload = {
        "username": "karyawan_umkm",
        "password": "sandi-aman-123",
        "full_name": "Karyawan",
        "role": "umkm",
        "umkm_id": umkm_user.umkm_id,
    }
    resp = client.post(f"{API}/auth/users", json=payload, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["umkm_id"] == umkm_user.umkm_id

    bad = {**payload, "username": "tanpa_umkm"}
    bad.pop("umkm_id")
    assert client.post(f"{API}/auth/users", json=bad, headers=admin_headers).status_code == 422

    staff_with_umkm = {**payload, "username": "bank_salah", "role": "bank"}
    assert client.post(f"{API}/auth/users", json=staff_with_umkm, headers=admin_headers).status_code == 422


def test_admin_list_and_deactivate(client, admin_headers, bank_user):
    resp = client.get(f"{API}/auth/users", params={"role": "bank"}, headers=admin_headers)
    assert resp.status_code == 200
    assert any(u["username"] == bank_user.username for u in resp.json())

    resp = client.patch(f"{API}/auth/users/{bank_user.id}/status", json={"is_active": False}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert client.get(f"{API}/auth/me", headers=bank_user.headers).status_code == 403
    resp = client.post(f"{API}/auth/login", data={"username": bank_user.username, "password": bank_user.password})
    assert resp.status_code == 403


def test_ensure_umkm_access(umkm_user, db_call):
    from fastapi import HTTPException

    async def _get(session):
        return await session.get(User, umkm_user.id)

    user = db_call(_get)
    auth_mod.ensure_umkm_access(user, umkm_user.umkm_id)
    with pytest.raises(HTTPException) as exc:
        auth_mod.ensure_umkm_access(user, umkm_user.umkm_id + 10_000)
    assert exc.value.status_code == 403


# ── Perangkat ───────────────────────────────────────────────────────────────
def _assign_lead(client, admin_headers, umkm_id: int, installer_id: int) -> dict:
    """Admin menugaskan rujukan UMKM ke installer (syarat installer mengelola perangkat UMKM itu)."""
    r = client.post(
        f"{API}/dashboard/leads",
        json={"umkm_id": umkm_id, "installer_user_id": installer_id, "recommended_kwp": 2.0},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_device_registration_returns_key_once(client, installer_user, umkm_user, db_call, admin_headers):
    _assign_lead(client, admin_headers, umkm_user.umkm_id, installer_user.id)
    resp = client.post(
        f"{API}/devices",
        json={"device_id": "ESP32-SKH-042", "umkm_id": umkm_user.umkm_id, "firmware_version": "1.2.0"},
        headers=installer_user.headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    api_key = body["api_key"]
    assert len(api_key) >= 40
    assert body["header_name"] == "X-Device-Key"

    async def _load(session):
        return (await session.execute(select(Device).where(Device.device_id == "ESP32-SKH-042"))).scalar_one()

    dev = db_call(_load)
    assert dev.api_key_hash == auth_mod.hash_api_key(api_key)
    assert api_key not in dev.api_key_hash

    # Tidak ada endpoint list yang mengembalikan key
    resp = client.get(f"{API}/devices", params={"umkm_id": umkm_user.umkm_id}, headers=installer_user.headers)
    assert resp.status_code == 200
    assert [d["device_id"] for d in resp.json()] == ["ESP32-SKH-042"]
    assert "api_key" not in resp.json()[0]

    # Duplikat ditolak
    resp = client.post(
        f"{API}/devices",
        json={"device_id": "ESP32-SKH-042", "umkm_id": umkm_user.umkm_id},
        headers=installer_user.headers,
    )
    assert resp.status_code == 409


def test_device_registration_permissions(client, umkm_user, bank_user, disperinaker_user, admin_headers):
    payload = {"device_id": "ESP32-TOLAK-1", "umkm_id": umkm_user.umkm_id}
    for user in (umkm_user, bank_user, disperinaker_user):
        assert client.post(f"{API}/devices", json=payload, headers=user.headers).status_code == 403
    resp = client.post(f"{API}/devices", json={**payload, "umkm_id": 999_999}, headers=admin_headers)
    assert resp.status_code == 404


def test_umkm_lists_only_own_devices(client, make_user, make_device):
    owner = make_user("umkm")
    other = make_user("umkm")
    mine = make_device(owner.umkm_id)
    make_device(other.umkm_id)
    resp = client.get(f"{API}/devices", headers=owner.headers)
    assert resp.status_code == 200
    assert [d["device_id"] for d in resp.json()] == [mine.device_id]
    resp = client.get(f"{API}/devices", params={"umkm_id": other.umkm_id}, headers=owner.headers)
    assert resp.status_code == 403


def test_get_current_device_and_last_seen(client, device, db_call):
    assert client.get(f"{API}/devices/whoami").status_code == 401
    assert client.get(f"{API}/devices/whoami", headers={"X-Device-Key": "salah"}).status_code == 401
    resp = client.get(f"{API}/devices/whoami", headers=device.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["device_id"] == device.device_id
    assert body["last_seen"] is not None

    async def _load(session):
        return (await session.execute(select(Device).where(Device.device_id == device.device_id))).scalar_one()

    dev = db_call(_load)
    assert dev.last_seen is not None and dev.last_seen.tzinfo is not None


def test_rotate_key_invalidates_old_key(client, device, admin_headers, umkm_user):
    assert client.post(f"{API}/devices/{device.device_id}/rotate-key", headers=umkm_user.headers).status_code == 403
    resp = client.post(f"{API}/devices/{device.device_id}/rotate-key", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    new_key = resp.json()["api_key"]
    assert new_key != device.api_key
    assert client.get(f"{API}/devices/whoami", headers=device.headers).status_code == 401
    assert client.get(f"{API}/devices/whoami", headers={"X-Device-Key": new_key}).status_code == 200
    assert client.post(f"{API}/devices/TIDAK-ADA/rotate-key", headers=admin_headers).status_code == 404


# ── Database ────────────────────────────────────────────────────────────────
def test_sqlite_url_creates_parent_dir(tmp_path):
    from app.core.database import _build_engine

    target = tmp_path / "nested" / "dir" / "x.db"
    eng = _build_engine(f"sqlite+aiosqlite:///{target.as_posix()}")
    assert target.parent.is_dir()
    assert eng.pool.__class__.__name__ == "NullPool"
    asyncio.run(eng.dispose())


def test_postgres_url_normalized():
    from app.core.database import normalize_database_url

    url = normalize_database_url("postgres://u:p@db:5432/waskita")
    assert url.drivername == "postgresql+asyncpg"
    assert normalize_database_url("sqlite:///./x.db").drivername == "sqlite+aiosqlite"


def test_installer_scoped_to_assigned_umkm(client, make_user, make_device, admin_headers):
    """Installer tidak boleh mendaftarkan/melihat/memutar key perangkat UMKM yang tidak ditugaskan."""
    inst = make_user("installer")
    victim = make_user("umkm", consent_share_data=False)
    dev = make_device(victim.umkm_id)

    assert client.post(f"{API}/devices", json={"device_id": "ESP32-BAJAK-1", "umkm_id": victim.umkm_id},
                       headers=inst.headers).status_code == 403
    assert client.post(f"{API}/devices/{dev.device_id}/rotate-key", headers=inst.headers).status_code == 403
    listed = client.get(f"{API}/devices", headers=inst.headers).json()
    assert dev.device_id not in {d["device_id"] for d in listed}
    assert client.get(f"{API}/devices", params={"umkm_id": victim.umkm_id}, headers=inst.headers).status_code == 403
    # key lama tetap berlaku
    assert client.get(f"{API}/devices/whoami", headers=dev.headers).status_code == 200

    # setelah ditugaskan admin, installer boleh mengelola
    _assign_lead(client, admin_headers, victim.umkm_id, inst.id)
    r = client.post(f"{API}/devices/{dev.device_id}/rotate-key", headers=inst.headers)
    assert r.status_code == 200
    assert client.get(f"{API}/devices/whoami", headers=dev.headers).status_code == 401
    listed = client.get(f"{API}/devices", headers=inst.headers).json()
    assert dev.device_id in {d["device_id"] for d in listed}

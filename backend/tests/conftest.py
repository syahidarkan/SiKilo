"""
Fixture pytest bersama untuk backend WASKITA.

Lingkungan tes (diset SEBELUM ``app`` di-import, lewat ``os.environ.setdefault``
sehingga bisa ditimpa dari luar):
    DATABASE_URL       sqlite+aiosqlite ke file sementara (satu file per sesi pytest)
    ENVIRONMENT=test, SECRET_KEY (nilai uji), PRELOAD_MODELS=false,
    SCHEDULER_ENABLED=false, USE_NASA_POWER=false (tanpa jaringan),
    WHATSAPP_PROVIDER=none, BOOTSTRAP_ADMIN_USERNAME/PASSWORD (admin uji).

Database dipakai bersama satu sesi pytest; JANGAN mengasumsikan tabel kosong.
Semua fixture pembuat user/perangkat memakai nama unik (uuid).

Fixture yang tersedia
---------------------
``client`` (session)
    ``fastapi.testclient.TestClient`` dengan lifespan aktif (init_db +
    bootstrap admin sudah jalan). Pakai untuk semua request HTTP.
``db_call`` (session)
    ``db_call(async_fn)`` menjalankan ``await async_fn(session)`` dengan
    ``AsyncSession`` baru di event loop aplikasi dan mengembalikan hasilnya.
    Contoh: ``db_call(lambda s: s.scalar(select(func.count(TelemetryRecord.id))))``.
    Commit sendiri di dalam ``async_fn`` bila menulis.
``admin_headers`` (session)
    Header ``Authorization`` untuk admin bootstrap.
``make_user`` (function)
    Factory ``make_user(role="umkm", **override) -> AuthedUser``.
    ``AuthedUser`` punya atribut ``id, username, password, role, umkm_id,
    token, headers, data`` (data = JSON UserOut). Role ``umkm`` dibuat lewat
    ``POST /auth/register`` (UMKM baru); role lain lewat ``POST /auth/users``.
    Override yang dikenali: ``umkm_name, kecamatan, consent_share_data,
    phone_whatsapp, connected_power_va, full_name``.
``umkm_user``, ``disperinaker_user``, ``installer_user``, ``bank_user``, ``admin_user`` (function)
    ``AuthedUser`` baru per tes untuk tiap role.
``auth_headers`` (function)
    Alias ``umkm_user.headers``.
``make_device`` (function)
    Factory ``make_device(umkm_id, device_id=None) -> RegisteredDevice``
    (didaftarkan admin lewat ``POST /devices``).
``device`` (function)
    ``RegisteredDevice`` milik ``umkm_user``; atribut ``device_id, api_key,
    umkm_id, headers`` (headers = ``{"X-Device-Key": api_key}``), ``owner``
    (AuthedUser pemilik).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

_TMP_DIR = Path(tempfile.mkdtemp(prefix="waskita-test-"))
_DB_PATH = (_TMP_DIR / "test.db").as_posix()

TEST_ADMIN_USERNAME = "admin_uji"
TEST_ADMIN_PASSWORD = "admin-uji-rahasia-123"
TEST_USER_PASSWORD = "sandi-uji-12345"

os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_DB_PATH}")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "kunci-rahasia-khusus-pengujian-waskita-0123456789")
os.environ.setdefault("PRELOAD_MODELS", "false")
os.environ.setdefault("BCRYPT_ROUNDS", "4")
os.environ.setdefault("SCHEDULER_ENABLED", "false")
os.environ.setdefault("USE_NASA_POWER", "false")
os.environ.setdefault("WHATSAPP_PROVIDER", "none")
os.environ.setdefault("BOOTSTRAP_ADMIN_USERNAME", TEST_ADMIN_USERNAME)
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", TEST_ADMIN_PASSWORD)


@dataclass
class AuthedUser:
    id: int
    username: str
    password: str
    role: str
    umkm_id: int | None
    token: str
    headers: dict[str, str]
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegisteredDevice:
    device_id: str
    api_key: str
    umkm_id: int
    headers: dict[str, str]
    data: dict[str, Any] = field(default_factory=dict)
    owner: AuthedUser | None = None


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _login(client, username: str, password: str) -> dict[str, Any]:
    resp = client.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def db_call(client) -> Callable[[Callable[[Any], Awaitable[Any]]], Any]:
    from app.core.database import AsyncSessionLocal

    def _run(fn: Callable[[Any], Awaitable[Any]]) -> Any:
        async def _wrapper():
            async with AsyncSessionLocal() as session:
                return await fn(session)

        return client.portal.call(_wrapper)

    return _run


@pytest.fixture(scope="session")
def admin_headers(client) -> dict[str, str]:
    body = _login(client, TEST_ADMIN_USERNAME, TEST_ADMIN_PASSWORD)
    return {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
def make_user(client, admin_headers) -> Callable[..., AuthedUser]:
    def _make(role: str = "umkm", **override: Any) -> AuthedUser:
        username = override.pop("username", None) or _unique(role)
        password = override.pop("password", TEST_USER_PASSWORD)
        full_name = override.pop("full_name", f"Pengguna Uji {role}")
        if role == "umkm":
            payload = {
                "username": username,
                "password": password,
                "full_name": full_name,
                "email": f"{username}@contoh.id",
                "umkm_name": override.pop("umkm_name", f"UMKM Uji {username[-4:]}"),
                "umkm_type": override.pop("umkm_type", "Konveksi & Laundry"),
                "address": override.pop("address", "Jl. Uji No. 1"),
                "kecamatan": override.pop("kecamatan", "Grogol"),
                "phone_whatsapp": override.pop("phone_whatsapp", "081234567890"),
                "connected_power_va": override.pop("connected_power_va", 5500),
                "consent_share_data": override.pop("consent_share_data", True),
            }
            payload.update(override)
            resp = client.post("/api/v1/auth/register", json=payload)
            assert resp.status_code == 201, resp.text
            body = resp.json()
            token = body["access_token"]
            data = body["user"]
        else:
            payload = {
                "username": username,
                "password": password,
                "full_name": full_name,
                "email": f"{username}@contoh.id",
                "role": role,
            }
            payload.update(override)
            resp = client.post("/api/v1/auth/users", json=payload, headers=admin_headers)
            assert resp.status_code == 201, resp.text
            data = resp.json()
            token = _login(client, username, password)["access_token"]
        return AuthedUser(
            id=data["id"],
            username=data["username"],
            password=password,
            role=data["role"],
            umkm_id=data.get("umkm_id"),
            token=token,
            headers={"Authorization": f"Bearer {token}"},
            data=data,
        )

    return _make


@pytest.fixture
def umkm_user(make_user) -> AuthedUser:
    return make_user("umkm")


@pytest.fixture
def disperinaker_user(make_user) -> AuthedUser:
    return make_user("disperinaker")


@pytest.fixture
def installer_user(make_user) -> AuthedUser:
    return make_user("installer")


@pytest.fixture
def bank_user(make_user) -> AuthedUser:
    return make_user("bank")


@pytest.fixture
def admin_user(make_user) -> AuthedUser:
    return make_user("admin")


@pytest.fixture
def auth_headers(umkm_user) -> dict[str, str]:
    return umkm_user.headers


@pytest.fixture
def make_device(client, admin_headers) -> Callable[..., RegisteredDevice]:
    def _make(umkm_id: int, device_id: str | None = None, firmware_version: str = "1.0.0") -> RegisteredDevice:
        device_id = device_id or _unique("ESP32").upper()
        resp = client.post(
            "/api/v1/devices",
            json={"device_id": device_id, "umkm_id": umkm_id, "firmware_version": firmware_version},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        return RegisteredDevice(
            device_id=data["device_id"],
            api_key=data["api_key"],
            umkm_id=data["umkm_id"],
            headers={"X-Device-Key": data["api_key"]},
            data=data,
        )

    return _make


@pytest.fixture
def device(make_device, umkm_user) -> RegisteredDevice:
    assert umkm_user.umkm_id is not None
    dev = make_device(umkm_user.umkm_id)
    dev.owner = umkm_user
    return dev

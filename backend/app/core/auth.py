from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = "nota-listrik-secret-2026-uns-hackathon"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 jam

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# In-memory user store (cukup untuk hackathon)
_USERS: dict[str, dict] = {
    "admin": {
        "username": "admin",
        "full_name": "Administrator",
        "email": "admin@notallistrik.id",
        "hashed_password": hash_password("admin123"),
        "umkm_name": "Demo UMKM Sukoharjo",
        "umkm_type": "Konveksi & Laundry",
        "role": "admin",
    }
}


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = _USERS.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def register_user(username: str, password: str, full_name: str, email: str, umkm_name: str, umkm_type: str) -> dict:
    if username in _USERS:
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    user = {
        "username": username,
        "full_name": full_name,
        "email": email,
        "hashed_password": hash_password(password),
        "umkm_name": umkm_name,
        "umkm_type": umkm_type,
        "role": "user",
    }
    _USERS[username] = user
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tidak terautentikasi")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub", "")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tidak valid")
    user = _USERS.get(username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User tidak ditemukan")
    return user

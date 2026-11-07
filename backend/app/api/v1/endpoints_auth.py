from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from app.core.auth import authenticate_user, register_user, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    email: str
    umkm_name: str
    umkm_type: str = "UMKM Umum"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    token = create_access_token({"sub": user["username"]})
    safe_user = {k: v for k, v in user.items() if k != "hashed_password"}
    return TokenResponse(access_token=token, token_type="bearer", user=safe_user)


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest):
    user = register_user(
        username=req.username,
        password=req.password,
        full_name=req.full_name,
        email=req.email,
        umkm_name=req.umkm_name,
        umkm_type=req.umkm_type,
    )
    token = create_access_token({"sub": user["username"]})
    safe_user = {k: v for k, v in user.items() if k != "hashed_password"}
    return TokenResponse(access_token=token, token_type="bearer", user=safe_user)


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {k: v for k, v in current_user.items() if k != "hashed_password"}

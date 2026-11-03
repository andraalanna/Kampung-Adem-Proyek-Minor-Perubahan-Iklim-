from datetime import timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_deps import (
    CurrentUser,
    decode_token,
    get_current_user,
    make_token,
    verify_password,
)
from app.config import get_settings
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "ka_refresh"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _issue(resp: Response, user_id: int) -> TokenOut:
    s = get_settings()
    resp.set_cookie(
        REFRESH_COOKIE, make_token(user_id, "refresh", timedelta(days=s.refresh_token_days)),
        httponly=True, secure=s.cookie_secure, samesite="strict", path="/api/v1/auth",
        max_age=s.refresh_token_days * 86400,
    )
    return TokenOut(access_token=make_token(user_id, "access",
                                            timedelta(minutes=s.access_token_minutes)),
                    expires_in=s.access_token_minutes * 60)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, resp: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email atau kata sandi salah")
    return _issue(resp, user.id)


@router.post("/refresh", response_model=TokenOut)
def refresh(resp: Response, ka_refresh: str | None = Cookie(default=None),
            db: Session = Depends(get_db)):
    if not ka_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "perlu login")
    uid = decode_token(ka_refresh, "refresh")
    user = db.get(User, uid)
    if user is None or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "akun tidak aktif")
    return _issue(resp, uid)


@router.post("/logout", status_code=204)
def logout(resp: Response):
    resp.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth")


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role,
            "rw_ids": None if user.rw_ids is None else sorted(user.rw_ids)}

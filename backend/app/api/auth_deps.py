"""Authentication (Argon2 + JWT) and authorization (5 roles + user_scopes), design doc 16.5."""

from dataclasses import dataclass
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.timeutil import now_utc
from app.db import get_db
from app.models import Role, Rw, User, UserScope, Village

_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

ADMIN, KELURAHAN, RTRW, KADER, TEKNIS = "admin", "kelurahan", "rtrw", "kader", "teknis"
ALL_ROLES = (ADMIN, KELURAHAN, RTRW, KADER, TEKNIS)
UNSCOPED_ROLES = (ADMIN, TEKNIS)  # see all regions (design doc 14.1)


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerificationError:
        return False


def make_token(user_id: int, kind: str, ttl: timedelta) -> str:
    now = now_utc()
    payload = {"sub": str(user_id), "typ": kind, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def decode_token(token: str, kind: str) -> int:
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token tidak valid") from exc
    if data.get("typ") != kind:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "jenis token salah")
    return int(data["sub"])


@dataclass
class CurrentUser:
    id: int
    name: str
    email: str
    role: str
    rw_ids: set[int] | None  # None = all regions

    def can_see_rw(self, rw_id: int) -> bool:
        return self.rw_ids is None or rw_id in self.rw_ids


def resolve_rw_scope(db: Session, user_id: int, role: str) -> set[int] | None:
    if role in UNSCOPED_ROLES:
        return None
    scopes = db.scalars(select(UserScope).where(UserScope.user_id == user_id)).all()
    district_ids = {s.district_id for s in scopes if s.district_id}
    village_ids = {s.village_id for s in scopes if s.village_id}
    rw_ids = {s.rw_id for s in scopes if s.rw_id}
    if district_ids or village_ids:
        q = select(Rw.id).join(Village, Village.id == Rw.village_id).where(
            or_(Village.district_id.in_(district_ids or {-1}),
                Rw.village_id.in_(village_ids or {-1}))
        )
        rw_ids |= set(db.scalars(q).all())
    return rw_ids


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "perlu login")
    uid = decode_token(creds.credentials, "access")
    row = db.execute(
        select(User, Role.name).join(Role, Role.id == User.role_id).where(User.id == uid)
    ).first()
    if row is None or not row[0].active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "akun tidak aktif")
    user, role = row
    return CurrentUser(user.id, user.name, user.email, role, resolve_rw_scope(db, user.id, role))


def require_roles(*roles: str):
    def dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "tidak punya akses")
        return user

    return dep


def require_ingest_key(x_api_key: str | None = Header(default=None)) -> None:
    key = get_settings().ingest_api_key
    if not key or x_api_key != key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "API key salah")


def scope_filter(column, user: CurrentUser):
    """SQL condition restricting `column` (an rw_id column) to the user's scope."""
    if user.rw_ids is None:
        return True
    return column.in_(user.rw_ids or {-1})

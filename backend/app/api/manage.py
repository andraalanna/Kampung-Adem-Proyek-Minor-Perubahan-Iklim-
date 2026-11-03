"""Recipients, thresholds, maintenance logs, users, reports."""

import csv
import io
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.auth_deps import (
    ADMIN,
    ALL_ROLES,
    KELURAHAN,
    TEKNIS,
    CurrentUser,
    get_current_user,
    hash_password,
    require_roles,
    scope_filter,
)
from app.config import get_settings
from app.core.crypto import decrypt_phone, encrypt_phone, hash_phone, mask_phone, normalize_phone
from app.core.timeutil import WIB, iso_wib, now_utc
from app.db import get_db
from app.models import (
    AlertThreshold,
    AuditLog,
    MaintenanceLog,
    Recipient,
    Role,
    User,
    UserScope,
)

router = APIRouter(tags=["manage"])


# ---------------------------------------------------------------- recipients

class RecipientIn(BaseModel):
    rw_id: int
    name: str = Field(min_length=2, max_length=120)
    role: str = Field(pattern="^(ketua_rw|ketua_rt|kader|staf_kelurahan)$")
    phone: str
    opt_in_at: datetime | None = None
    opt_in_evidence: str | None = Field(None, max_length=500)


class RecipientPatch(BaseModel):
    name: str | None = None
    role: str | None = Field(None, pattern="^(ketua_rw|ketua_rt|kader|staf_kelurahan)$")
    active: bool | None = None
    opt_in_at: datetime | None = None
    opt_in_evidence: str | None = None


def _recipient_out(r: Recipient) -> dict:
    s = get_settings()
    try:
        masked = mask_phone(decrypt_phone(r.phone_enc, s.phone_enc_key))
    except Exception:  # noqa: BLE001  wrong key -> never leak, show placeholder
        masked = "tidak dapat dibaca"
    return {"id": r.id, "rw_id": r.rw_id, "name": r.name, "role": r.role, "phone_masked": masked,
            "opt_in_at": iso_wib(r.opt_in_at), "opt_out_at": iso_wib(r.opt_out_at),
            "active": r.active, "last_failure": r.last_failure}


recipient_admins = require_roles(ADMIN, KELURAHAN)


@router.get("/recipients")
def list_recipients(rw_id: int | None = None, user: CurrentUser = Depends(recipient_admins),
                    db: Session = Depends(get_db)):
    q = select(Recipient).where(scope_filter(Recipient.rw_id, user))
    if rw_id is not None:
        q = q.where(Recipient.rw_id == rw_id)
    return {"items": [_recipient_out(r) for r in db.scalars(q.order_by(Recipient.rw_id,
                                                                         Recipient.name))]}


@router.post("/recipients", status_code=201)
def create_recipient(body: RecipientIn, user: CurrentUser = Depends(recipient_admins),
                     db: Session = Depends(get_db)):
    if not user.can_see_rw(body.rw_id):
        raise HTTPException(403, "RW di luar wilayah Anda")
    s = get_settings()
    try:
        phone = normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    h = hash_phone(phone, s.phone_hash_key)
    if db.scalar(select(Recipient).where(Recipient.phone_hash == h,
                                         Recipient.rw_id == body.rw_id)):
        raise HTTPException(409, "Nomor ini sudah terdaftar untuk RW tersebut")
    r = Recipient(rw_id=body.rw_id, name=body.name, role=body.role,
                  phone_enc=encrypt_phone(phone, s.phone_enc_key), phone_hash=h,
                  opt_in_at=body.opt_in_at, opt_in_evidence=body.opt_in_evidence)
    db.add(r)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="create", entity="recipient", entity_id=str(r.id)))
    db.commit()
    return _recipient_out(r)


@router.patch("/recipients/{rid}")
def patch_recipient(rid: int, body: RecipientPatch, user: CurrentUser = Depends(recipient_admins),
                    db: Session = Depends(get_db)):
    r = db.get(Recipient, rid)
    if r is None or not user.can_see_rw(r.rw_id):
        raise HTTPException(404, "Penerima tidak ditemukan")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(r, k, v)
    if data.get("active") is True and r.opt_out_at is not None:
        raise HTTPException(409, "Penerima sudah berhenti (STOP). Perlu opt-in baru tertulis.")
    db.add(AuditLog(user_id=user.id, action="update", entity="recipient", entity_id=str(r.id),
                    detail=json.dumps(list(data))))
    db.commit()
    return _recipient_out(r)


@router.delete("/recipients/{rid}", status_code=204)
def delete_recipient(rid: int, user: CurrentUser = Depends(recipient_admins),
                     db: Session = Depends(get_db)):
    """Right to erasure: remove the phone number. Notification logs keep only the recipient id."""
    r = db.get(Recipient, rid)
    if r is None or not user.can_see_rw(r.rw_id):
        raise HTTPException(404, "Penerima tidak ditemukan")
    r.active = False
    r.name = "(dihapus)"
    r.phone_enc = ""
    r.phone_hash = ""
    db.add(AuditLog(user_id=user.id, action="erase", entity="recipient", entity_id=str(r.id)))
    db.commit()


# ---------------------------------------------------------------- thresholds

class ThresholdIn(BaseModel):
    rw_id: int | None = None
    level: str = Field(pattern="^(WASPADA|SIAGA|AWAS)$")
    min_value: float = Field(ge=20, le=60)
    duration_min: int = Field(ge=10, le=360, multiple_of=10)
    min_sensors: int = Field(ge=1, le=5)
    exit_value: float = Field(ge=20, le=60)
    exit_duration_min: int = Field(ge=10, le=360, multiple_of=10)
    escalate_from: str | None = Field(None, pattern="^(WASPADA|SIAGA)$")
    escalate_after_min: int | None = Field(None, ge=30, le=1440)
    approved_note: str = Field(min_length=5, description="e.g. persetujuan Dinkes, nomor surat")


def _threshold_out(t: AlertThreshold) -> dict:
    return {"id": t.id, "rw_id": t.rw_id, "level": t.level, "metric": t.metric,
            "min_value": t.min_value, "duration_min": t.duration_min,
            "min_sensors": t.min_sensors, "exit_value": t.exit_value,
            "exit_duration_min": t.exit_duration_min, "escalate_from": t.escalate_from,
            "escalate_after_min": t.escalate_after_min, "version": t.version,
            "active": t.active, "approved_note": t.approved_note,
            "created_at": iso_wib(t.created_at)}


@router.get("/thresholds")
def list_thresholds(include_history: bool = False, _: CurrentUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    q = select(AlertThreshold)
    if not include_history:
        q = q.where(AlertThreshold.active.is_(True))
    rows = db.scalars(q.order_by(AlertThreshold.level, AlertThreshold.version.desc())).all()
    return {"items": [_threshold_out(t) for t in rows]}


@router.put("/thresholds")
def put_threshold(body: ThresholdIn, user: CurrentUser = Depends(require_roles(ADMIN)),
                  db: Session = Depends(get_db)):
    """Saves a new version; the previous one is deactivated but kept for history."""
    if body.exit_value >= body.min_value:
        raise HTTPException(422, "Ambang keluar harus lebih rendah dari ambang masuk (histeresis)")
    prev = db.scalar(select(AlertThreshold).where(
        AlertThreshold.level == body.level, AlertThreshold.active.is_(True),
        AlertThreshold.rw_id.is_(None) if body.rw_id is None
        else AlertThreshold.rw_id == body.rw_id))
    version = 1
    if prev:
        prev.active = False
        version = prev.version + 1
    t = AlertThreshold(**body.model_dump(), metric="heat_index_c", version=version, active=True,
                       created_by=user.id)
    db.add(t)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="threshold_version", entity="alert_threshold",
                    entity_id=str(t.id), detail=body.model_dump_json()))
    db.commit()
    return _threshold_out(t)


# ---------------------------------------------------------------- maintenance

class MaintenanceIn(BaseModel):
    node_id: str | None = None
    gateway_id: int | None = None
    type: str = Field(pattern="^(cleaning|battery|replace|calibration|antenna|other)$")
    description: str = Field(min_length=3)
    performed_at: datetime
    resolves_tickets: bool = True


@router.get("/maintenance-logs")
def list_maintenance(node_id: str | None = None, open_only: bool = False,
                     _: CurrentUser = Depends(require_roles(ADMIN, TEKNIS)),
                     db: Session = Depends(get_db)):
    q = select(MaintenanceLog)
    if node_id:
        q = q.where(MaintenanceLog.node_id == node_id)
    if open_only:
        q = q.where(MaintenanceLog.resolved.is_(False), MaintenanceLog.type.like("ticket%"))
    rows = db.scalars(q.order_by(MaintenanceLog.created_at.desc()).limit(500)).all()
    return {"items": [{"id": m.id, "node_id": m.node_id, "gateway_id": m.gateway_id,
                       "type": m.type, "description": m.description, "resolved": m.resolved,
                       "performed_at": iso_wib(m.performed_at),
                       "created_at": iso_wib(m.created_at)} for m in rows]}


@router.post("/maintenance-logs", status_code=201)
def create_maintenance(body: MaintenanceIn,
                       user: CurrentUser = Depends(require_roles(ADMIN, TEKNIS)),
                       db: Session = Depends(get_db)):
    m = MaintenanceLog(node_id=body.node_id, gateway_id=body.gateway_id, user_id=user.id,
                       type=body.type, description=body.description,
                       performed_at=body.performed_at, resolved=True)
    db.add(m)
    if body.resolves_tickets and body.node_id:
        for t in db.scalars(select(MaintenanceLog).where(
                MaintenanceLog.node_id == body.node_id, MaintenanceLog.resolved.is_(False))):
            t.resolved = True
    db.commit()
    return {"id": m.id}


# ---------------------------------------------------------------- users (admin)

class UserIn(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=10)
    role: str
    district_ids: list[int] = []
    village_ids: list[int] = []
    rw_ids: list[int] = []


@router.get("/users")
def list_users(_: CurrentUser = Depends(require_roles(ADMIN)), db: Session = Depends(get_db)):
    rows = db.execute(select(User, Role.name).join(Role, Role.id == User.role_id)
                      .order_by(User.name)).all()
    out = []
    for u, role in rows:
        scopes = db.scalars(select(UserScope).where(UserScope.user_id == u.id)).all()
        out.append({"id": u.id, "name": u.name, "email": u.email, "role": role,
                    "active": u.active,
                    "scopes": [{"district_id": s.district_id, "village_id": s.village_id,
                                "rw_id": s.rw_id} for s in scopes]})
    return {"items": out}


@router.post("/users", status_code=201)
def create_user(body: UserIn, admin: CurrentUser = Depends(require_roles(ADMIN)),
                db: Session = Depends(get_db)):
    if body.role not in ALL_ROLES:
        raise HTTPException(422, "Peran tidak dikenal")
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "Email sudah terdaftar")
    role_id = db.scalar(select(Role.id).where(Role.name == body.role))
    u = User(name=body.name, email=body.email.lower(), password_hash=hash_password(body.password),
             role_id=role_id)
    db.add(u)
    db.flush()
    for d in body.district_ids:
        db.add(UserScope(user_id=u.id, district_id=d))
    for v in body.village_ids:
        db.add(UserScope(user_id=u.id, village_id=v))
    for r in body.rw_ids:
        db.add(UserScope(user_id=u.id, rw_id=r))
    db.add(AuditLog(user_id=admin.id, action="create", entity="user", entity_id=str(u.id),
                    detail=f"role={body.role}"))
    db.commit()
    return {"id": u.id}


@router.patch("/users/{uid}")
def patch_user(uid: int, active: bool | None = None, role: str | None = None,
               admin: CurrentUser = Depends(require_roles(ADMIN)), db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if u is None:
        raise HTTPException(404, "Pengguna tidak ditemukan")
    if active is not None:
        u.active = active
    if role is not None:
        if role not in ALL_ROLES:
            raise HTTPException(422, "Peran tidak dikenal")
        u.role_id = db.scalar(select(Role.id).where(Role.name == role))
    db.add(AuditLog(user_id=admin.id, action="update", entity="user", entity_id=str(uid),
                    detail=f"active={active} role={role}"))
    db.commit()
    return {"id": uid}


# ---------------------------------------------------------------- reports

@router.get("/reports/monthly")
def monthly_report(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                   format: str = Query("csv", pattern="^(csv)$"),
                   user: CurrentUser = Depends(require_roles(ADMIN, KELURAHAN, TEKNIS)),
                   db: Session = Depends(get_db)):
    """Per RW: hours in each status, alert count, data completeness. CSV only (PDF later)."""
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1, tzinfo=WIB)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=WIB)
    rows = db.execute(text("""
        SELECT h.rw_id,
               count(*) FILTER (WHERE h.status = 'WASPADA') / 6.0 AS jam_waspada,
               count(*) FILTER (WHERE h.status = 'SIAGA') / 6.0 AS jam_siaga,
               count(*) FILTER (WHERE h.status = 'AWAS') / 6.0 AS jam_awas,
               count(*) FILTER (WHERE h.status = 'TIDAK_ADA_DATA') / 6.0 AS jam_tanpa_data,
               max(h.heat_index_c) FILTER (WHERE h.tier = 'A') AS hi_maks,
               100.0 * count(*) FILTER (WHERE h.tier = 'A')
                 / NULLIF(count(*), 0) AS kelengkapan_pct,
               (SELECT count(*) FROM alerts a WHERE a.rw_id = h.rw_id
                  AND a.started_at >= :s AND a.started_at < :e
                  AND a.level IN ('SIAGA', 'AWAS')) AS jumlah_alert
        FROM heatmap_data h
        WHERE h.ts >= :s AND h.ts < :e
        GROUP BY h.rw_id ORDER BY h.rw_id
    """), {"s": start, "e": end}).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rw_id", "jam_waspada", "jam_siaga", "jam_awas", "jam_tanpa_data",
                "indeks_panas_maks_c", "kelengkapan_data_pct", "jumlah_peringatan"])
    for r in rows:
        if user.can_see_rw(r.rw_id):
            w.writerow([r.rw_id, *(None if v is None else round(float(v), 1) for v in r[1:7]),
                        r.jumlah_alert])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="laporan-{month}.csv"'})


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(func.now()))
    return {"ok": True, "time": iso_wib(now_utc()), "date": date.today().isoformat()}

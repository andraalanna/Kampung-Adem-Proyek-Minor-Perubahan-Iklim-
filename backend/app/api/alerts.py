from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.auth_deps import (
    ADMIN,
    KELURAHAN,
    CurrentUser,
    get_current_user,
    require_roles,
    scope_filter,
)
from app.core.timeutil import iso_wib, now_utc
from app.db import get_db
from app.models import Alert, AuditLog, NotificationLog, Rw, StatusEvent, Village

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_out(a: Alert, counts: dict) -> dict:
    c = counts.get(a.id, {})
    return {
        "id": a.id, "rw_id": a.rw_id, "level": a.level, "source": a.source,
        "started_at": iso_wib(a.started_at), "resolved_at": iso_wib(a.resolved_at),
        "resolved_reason": a.resolved_reason, "confidence": a.confidence, "note": a.note,
        "trigger": {"heat_index_c": a.trigger_hi_c, "rule": a.rule},
        "peak_hi_c": a.peak_hi_c,
        "notifications": {k: c.get(k, 0) for k in ("sent", "delivered", "failed", "held",
                                                     "confirmed")},
    }


def _notification_counts(db: Session, ids: list[int]) -> dict:
    if not ids:
        return {}
    rows = db.execute(select(
        NotificationLog.alert_id,
        func.count().filter(NotificationLog.status.in_(["sent", "delivered", "read",
                                                        "dry_run"])),
        func.count().filter(NotificationLog.status.in_(["delivered", "read"])),
        func.count().filter(NotificationLog.status == "failed"),
        func.count().filter(NotificationLog.status == "held"),
        func.count(NotificationLog.confirmed_at),
    ).where(NotificationLog.alert_id.in_(ids)).group_by(NotificationLog.alert_id)).all()
    return {r[0]: dict(zip(["sent", "delivered", "failed", "held", "confirmed"], r[1:],
                           strict=True)) for r in rows}


@router.get("")
def list_alerts(rw_id: int | None = None,
                status: str | None = Query(None, pattern="^(active|resolved)$"),
                level: str | None = Query(None, pattern="^(WASPADA|SIAGA|AWAS)$"),
                from_: datetime | None = Query(None, alias="from"), to: datetime | None = None,
                limit: int = Query(100, le=1000),
                user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    q = (select(Alert, Rw.rw_number, Village.name).join(Rw, Rw.id == Alert.rw_id)
         .join(Village, Village.id == Rw.village_id).where(scope_filter(Alert.rw_id, user)))
    if rw_id is not None:
        q = q.where(Alert.rw_id == rw_id)
    if status == "active":
        q = q.where(Alert.resolved_at.is_(None))
    elif status == "resolved":
        q = q.where(Alert.resolved_at.is_not(None))
    if level:
        q = q.where(Alert.level == level)
    if from_:
        q = q.where(Alert.started_at >= from_)
    if to:
        q = q.where(Alert.started_at <= to)
    rows = db.execute(q.order_by(case((Alert.resolved_at.is_(None), 0), else_=1),
                                 Alert.started_at.desc()).limit(limit)).all()
    counts = _notification_counts(db, [a.id for a, *_ in rows])
    return {"items": [_alert_out(a, counts) | {"rw_name": f"RW {n}, Kel. {v}"}
                      for a, n, v in rows]}


class ManualAlertIn(BaseModel):
    rw_ids: list[int] = Field(min_length=1)
    level: str = Field(pattern="^(WASPADA|SIAGA|AWAS)$")
    source: str = Field("manual", pattern="^(manual|manual_bmkg|manual_dinkes)$")
    note: str = Field(min_length=3, max_length=500)
    send_whatsapp: bool = False


@router.post("", status_code=201)
def create_manual(body: ManualAlertIn,
                  user: CurrentUser = Depends(require_roles(ADMIN, KELURAHAN)),
                  db: Session = Depends(get_db)):
    """Manual alert, e.g. forwarding a BMKG/Dinkes advisory (design doc 8.3 #7).

    Manual alerts are dashboard-only for now: the approved template peringatan_panas_rw needs
    measured values, and a separate manual-advisory template has not been worded or approved.
    """
    if body.send_whatsapp:
        raise HTTPException(422, "Pengiriman WhatsApp untuk peringatan manual belum tersedia: "
                                 "template khusus belum disetujui.")
    now = now_utc()
    created = []
    for rw_id in body.rw_ids:
        if not user.can_see_rw(rw_id):
            raise HTTPException(403, f"RW {rw_id} di luar wilayah Anda")
        rw = db.get(Rw, rw_id)
        if rw is None:
            raise HTTPException(404, f"RW {rw_id} tidak ditemukan")
        a = Alert(rw_id=rw_id, level=body.level, source=body.source, note=body.note,
                  rule="manual", started_at=now, created_by=user.id)
        db.add(a)
        db.flush()
        db.add(StatusEvent(rw_id=rw_id, ts=now, kind="manual_alert", from_level="-",
                           to_level=body.level, reason=body.note, alert_id=a.id))
        created.append(a.id)
    db.add(AuditLog(user_id=user.id, action="create_manual_alert", entity="alert",
                    entity_id=",".join(map(str, created)), detail=body.model_dump_json()))
    db.commit()
    return {"id": created[0] if len(created) == 1 else created, "queued_notifications": 0}


@router.post("/{alert_id}/close")
def close_alert(alert_id: int, user: CurrentUser = Depends(require_roles(ADMIN)),
                db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or a.resolved_at is not None:
        raise HTTPException(404, "Peringatan aktif tidak ditemukan")
    now = now_utc()
    a.resolved_at, a.resolved_reason = now, "ditutup_manual"
    db.add(StatusEvent(rw_id=a.rw_id, ts=now, kind="manual_close", from_level=a.level,
                       to_level="-", reason=f"ditutup oleh user {user.id}", alert_id=a.id))
    db.add(AuditLog(user_id=user.id, action="close_alert", entity="alert", entity_id=str(a.id)))
    db.commit()
    return {"id": a.id, "resolved_at": iso_wib(now)}


@router.get("/{alert_id}/notifications")
def alert_notifications(alert_id: int, user: CurrentUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or not user.can_see_rw(a.rw_id):
        raise HTTPException(404, "Peringatan tidak ditemukan")
    logs = db.scalars(select(NotificationLog).where(NotificationLog.alert_id == alert_id)
                      .order_by(NotificationLog.id)).all()
    return {"items": [{"id": n.id, "recipient_id": n.recipient_id, "template": n.template_name,
                       "status": n.status, "hold_reason": n.hold_reason,
                       "error_code": n.error_code, "sent_at": iso_wib(n.sent_at),
                       "confirmed_at": iso_wib(n.confirmed_at)} for n in logs]}

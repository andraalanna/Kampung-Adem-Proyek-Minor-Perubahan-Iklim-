"""Meta WhatsApp webhook: delivery statuses, "1" confirmations, "STOP" opt-out (doc 11.3, 11.6)."""

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.crypto import hash_phone
from app.core.timeutil import now_utc
from app.db import get_db
from app.models import AuditLog, NotificationLog, Recipient
from app.worker.whatsapp import verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)

STOP_WORDS = {"stop", "berhenti", "unsubscribe"}
CONFIRM_WORDS = {"1", "sudah", "ok"}


@router.get("/whatsapp", response_class=PlainTextResponse)
def verify(mode: str = Query(alias="hub.mode"), token: str = Query(alias="hub.verify_token"),
           challenge: str = Query(alias="hub.challenge")):
    s = get_settings()
    if mode == "subscribe" and s.wa_verify_token and token == s.wa_verify_token:
        return challenge
    raise HTTPException(403, "verify token mismatch")


def _ts(raw: str | None) -> datetime:
    return datetime.fromtimestamp(int(raw), UTC) if raw else now_utc()


def handle_status(db: Session, st: dict) -> None:
    n = db.scalar(select(NotificationLog).where(NotificationLog.wa_message_id == st.get("id")))
    if n is None:
        return
    new = st.get("status")  # sent | delivered | read | failed
    order = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}
    if new == "failed":
        n.status = "failed"
        errs = st.get("errors") or [{}]
        n.error_code = str(errs[0].get("code", "unknown"))
        r = db.get(Recipient, n.recipient_id)
        if r:
            r.last_failure = f"{n.error_code}: {errs[0].get('title', '')}"[:120]
    elif new in order and order[new] > order.get(n.status, -1):
        n.status = new
    n.status_at = _ts(st.get("timestamp"))


def handle_message(db: Session, msg: dict) -> None:
    if msg.get("type") != "text":
        return
    body = (msg.get("text", {}).get("body") or "").strip().lower()
    sender = msg.get("from", "")
    h = hash_phone(sender, get_settings().phone_hash_key)
    recipients = db.scalars(select(Recipient).where(Recipient.phone_hash == h)).all()
    if not recipients:
        return
    now = _ts(msg.get("timestamp"))
    if body in STOP_WORDS:
        for r in recipients:
            r.active = False
            r.opt_out_at = now
            db.add(AuditLog(action="opt_out_stop", entity="recipient", entity_id=str(r.id)))
        log.info("recipient(s) %s opted out via STOP", [r.id for r in recipients])
    elif body in CONFIRM_WORDS:
        last = db.scalar(select(NotificationLog).where(
            NotificationLog.recipient_id.in_([r.id for r in recipients]),
            NotificationLog.status.in_(["sent", "delivered", "read"]),
        ).order_by(NotificationLog.sent_at.desc()))
        if last and last.confirmed_at is None:
            last.confirmed_at = now


@router.post("/whatsapp")
async def receive(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_signature(get_settings().wa_app_secret, raw,
                            request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(401, "invalid signature")
    data = json.loads(raw)
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for st in value.get("statuses", []):
                handle_status(db, st)
            for msg in value.get("messages", []):
                handle_message(db, msg)
    db.commit()
    return {"ok": True}

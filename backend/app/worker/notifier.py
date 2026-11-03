"""Notification queue (design doc 11.3, 11.6, 11.7, 13.3).

Every decision produces a notification_logs row: queued, held (with reason), sent, failed,
or dry_run (WA_ENABLED=false). Recipients need opt_in_at and no opt_out_at.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core.antispam import (
    AntiSpamConfig,
    recipient_hold_reason,
    rw_cooldown_reason,
    wib_day_start,
)
from app.core.crypto import decrypt_phone
from app.core.timeutil import now_utc
from app.models import Alert, NotificationLog, Recipient
from app.worker.whatsapp import ALERT_TEMPLATES, TEMPLATE_ALERT, WhatsAppError, send_template

log = logging.getLogger(__name__)

RETRY_DELAYS = [timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10)]
MAX_ATTEMPTS = 4
COUNTED_STATUSES = ("queued", "sent", "delivered", "read", "dry_run")


def antispam_config(s: Settings) -> AntiSpamConfig:
    return AntiSpamConfig(cooldown_min=s.cooldown_min,
                          max_per_recipient_per_day=s.max_alerts_per_recipient_per_day,
                          quiet_start_hour=s.quiet_start_hour, quiet_end_hour=s.quiet_end_hour)


def eligible_recipients(db: Session, rw_id: int) -> list[Recipient]:
    return list(db.scalars(select(Recipient).where(
        Recipient.rw_id == rw_id, Recipient.active.is_(True),
        Recipient.opt_in_at.is_not(None), Recipient.opt_out_at.is_(None),
    )))


def _last_alert_sent(db: Session, rw_id: int, level: str) -> datetime | None:
    return db.scalar(
        select(func.max(NotificationLog.created_at))
        .join(Alert, Alert.id == NotificationLog.alert_id)
        .where(Alert.rw_id == rw_id, NotificationLog.level == level,
               NotificationLog.template_name == TEMPLATE_ALERT,
               NotificationLog.status.in_(COUNTED_STATUSES))
    )


def _sent_today(db: Session, recipient_id: int, now: datetime) -> int:
    return db.scalar(
        select(func.count()).select_from(NotificationLog).where(
            NotificationLog.recipient_id == recipient_id,
            NotificationLog.template_name.in_(ALERT_TEMPLATES),
            NotificationLog.status.in_(COUNTED_STATUSES),
            NotificationLog.created_at >= wib_day_start(now),
        )
    ) or 0


def enqueue(db: Session, alert: Alert, template: str, level: str, params: list[str],
            now: datetime | None = None) -> int:
    """Create log rows for all eligible recipients of the alert's RW. Returns number queued."""
    now = now or now_utc()
    cfg = antispam_config(get_settings())
    rw_hold = (rw_cooldown_reason(level, now, _last_alert_sent(db, alert.rw_id, level), cfg)
               if template == TEMPLATE_ALERT else None)
    queued = 0
    for r in eligible_recipients(db, alert.rw_id):
        hold = rw_hold or recipient_hold_reason(level, now, _sent_today(db, r.id, now), cfg)
        db.add(NotificationLog(
            alert_id=alert.id, recipient_id=r.id, template_name=template,
            params=json.dumps(params, ensure_ascii=False), level=level,
            status="held" if hold else "queued", hold_reason=hold,
            next_attempt_at=None if hold else now, created_at=now,
        ))
        queued += 0 if hold else 1
    db.flush()
    return queued


def send_due(db: Session, now: datetime | None = None, client=None) -> int:
    """Send queued messages whose next_attempt_at has passed. Returns number processed."""
    s = get_settings()
    now = now or now_utc()
    due = db.scalars(select(NotificationLog).where(
        NotificationLog.status == "queued", NotificationLog.next_attempt_at <= now,
    ).order_by(NotificationLog.id).limit(100).with_for_update(skip_locked=True)).all()
    for n in due:
        r = db.get(Recipient, n.recipient_id)
        if r is None or not r.active or r.opt_in_at is None or r.opt_out_at is not None:
            n.status, n.hold_reason, n.status_at = "held", "not_eligible", now
            continue
        n.attempts += 1
        if not s.wa_enabled:
            n.status, n.sent_at, n.status_at = "dry_run", now, now
            log.info("[dry-run] %s to recipient %s params=%s", n.template_name, r.id, n.params)
            continue
        try:
            phone = decrypt_phone(r.phone_enc, s.phone_enc_key)
            n.wa_message_id = send_template(s, phone, n.template_name, json.loads(n.params or "[]"),
                                            client=client)
            n.status, n.sent_at, n.status_at = "sent", now, now
        except WhatsAppError as exc:
            n.error_code = exc.code
            if exc.retryable and n.attempts < MAX_ATTEMPTS:
                n.next_attempt_at = now + RETRY_DELAYS[min(n.attempts - 1, len(RETRY_DELAYS) - 1)]
                log.warning("WA send retry %s for log %s: %s", n.attempts, n.id, exc)
            else:
                n.status, n.status_at = "failed", now
                r.last_failure = f"{exc.code}: {exc}"[:120]
                log.error("WA send failed for log %s: %s", n.id, exc)
    db.commit()
    return len(due)

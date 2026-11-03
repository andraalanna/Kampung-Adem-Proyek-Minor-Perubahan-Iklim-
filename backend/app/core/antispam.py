"""WhatsApp anti-spam rules (design doc 13.3): cooldown, daily cap, quiet hours."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.timeutil import to_wib


@dataclass(frozen=True)
class AntiSpamConfig:
    cooldown_min: int = 180  # per RW per level
    max_per_recipient_per_day: int = 3
    quiet_start_hour: int = 21  # WIB, inclusive
    quiet_end_hour: int = 5  # WIB, exclusive
    quiet_exempt_levels: frozenset[str] = frozenset({"AWAS"})


def in_quiet_hours(now: datetime, cfg: AntiSpamConfig) -> bool:
    h = to_wib(now).hour
    if cfg.quiet_start_hour > cfg.quiet_end_hour:
        return h >= cfg.quiet_start_hour or h < cfg.quiet_end_hour
    return cfg.quiet_start_hour <= h < cfg.quiet_end_hour


def wib_day_start(now: datetime) -> datetime:
    return to_wib(now).replace(hour=0, minute=0, second=0, microsecond=0)


def rw_cooldown_reason(level: str, now: datetime, last_alert_sent_at: datetime | None,
                       cfg: AntiSpamConfig) -> str | None:
    """Cooldown is per RW per level and applies to alert (peringatan) messages only."""
    if last_alert_sent_at and now - last_alert_sent_at < timedelta(minutes=cfg.cooldown_min):
        return "cooldown"
    return None


def recipient_hold_reason(level: str, now: datetime, sent_today: int,
                          cfg: AntiSpamConfig) -> str | None:
    """Reason to hold a message for one recipient, or None if it may be sent now."""
    if sent_today >= cfg.max_per_recipient_per_day:
        return "daily_limit"
    if in_quiet_hours(now, cfg) and level not in cfg.quiet_exempt_levels:
        return "quiet_hours"
    return None

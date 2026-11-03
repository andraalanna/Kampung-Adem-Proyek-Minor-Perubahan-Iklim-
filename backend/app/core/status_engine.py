"""RW status engine (design doc 13.2, 13.3, 13.4, 13.5).

Pure function: given the previous state, recent 10-minute buckets of tier-A sensor heat index,
and rules loaded from `alert_thresholds`, return the new state and the events that happened.
Thresholds are never hardcoded here; they come in as `LevelRule` objects.
"""

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from statistics import fmean

NORMAL = "NORMAL"
WASPADA = "WASPADA"
SIAGA = "SIAGA"
AWAS = "AWAS"
NO_DATA = "TIDAK_ADA_DATA"

RANK = {NORMAL: 0, WASPADA: 1, SIAGA: 2, AWAS: 3}
WHATSAPP_LEVELS = frozenset({SIAGA, AWAS})


@dataclass(frozen=True)
class LevelRule:
    level: str
    min_value: float  # enter when RW heat index >= this
    duration_min: int  # ... for this long
    min_sensors: int  # sensors that must exceed min_value (capped at sensors available)
    exit_value: float  # leave when RW heat index < this
    exit_duration_min: int  # ... for this long
    escalate_from: str | None = None  # e.g. AWAS also entered when SIAGA lasts ...
    escalate_after_min: int | None = None  # ... this many minutes


@dataclass(frozen=True)
class EngineConfig:
    rules: tuple[LevelRule, ...]
    bucket_min: int = 10
    no_data_after_min: int = 30
    data_gap_close_after_min: int = 180

    def rule(self, level: str) -> LevelRule | None:
        return next((r for r in self.rules if r.level == level), None)


@dataclass(frozen=True)
class Bucket:
    ts: datetime  # bucket start
    sensor_hi: tuple[float, ...]  # one value per tier-A sensor with ok data in this bucket

    @property
    def hi(self) -> float | None:
        return fmean(self.sensor_hi) if self.sensor_hi else None


@dataclass(frozen=True)
class RwState:
    level: str = NORMAL
    level_since: datetime | None = None
    no_data_since: datetime | None = None
    # True when the current level was reached by escalation (e.g. SIAGA lasting 3 h -> AWAS).
    # Such a level is left by the exit rule of the level it escalated from, so it does not
    # flap back immediately when HI never reached the escalated level's own entry value.
    escalated: bool = False

    @property
    def display_status(self) -> str:
        return NO_DATA if self.no_data_since is not None else self.level


@dataclass(frozen=True)
class Event:
    kind: str  # raised | lowered | no_data_started | data_resumed | closed_data_gap
    from_level: str
    to_level: str
    reason: str


@dataclass
class Decision:
    state: RwState
    events: list[Event] = field(default_factory=list)

    @property
    def display_status(self) -> str:
        return self.state.display_status


def _window(buckets: dict[datetime, Bucket], latest: datetime, minutes: int,
            bucket_min: int) -> list[Bucket] | None:
    """Consecutive buckets covering `minutes` and ending at `latest`; None if any is missing."""
    n = max(1, math.ceil(minutes / bucket_min))
    out = []
    for i in range(n):
        b = buckets.get(latest - timedelta(minutes=i * bucket_min))
        if b is None or not b.sensor_hi:
            return None
        out.append(b)
    return out


def _entry_ok(rule: LevelRule, window: list[Bucket] | None) -> bool:
    if window is None:
        return False
    for b in window:
        required = min(rule.min_sensors, len(b.sensor_hi))
        above = sum(1 for v in b.sensor_hi if v >= rule.min_value)
        if b.hi < rule.min_value or above < required:
            return False
    return True


def _exit_ok(rule: LevelRule, window: list[Bucket] | None) -> bool:
    return window is not None and all(b.hi < rule.exit_value for b in window)


def evaluate(state: RwState, buckets: list[Bucket], now: datetime, cfg: EngineConfig) -> Decision:
    by_ts = {b.ts: b for b in buckets if b.sensor_hi}
    cutoff = now - timedelta(minutes=cfg.no_data_after_min)
    recent = [ts for ts in by_ts if ts + timedelta(minutes=cfg.bucket_min) > cutoff]
    d = Decision(state)

    if not recent:
        s = state
        if s.no_data_since is None:
            s = replace(s, no_data_since=now)
            d.events.append(Event("no_data_started", s.level, s.level, "no valid reading 30 min"))
        if s.level != NORMAL and now - s.no_data_since >= timedelta(
            minutes=cfg.data_gap_close_after_min
        ):
            d.events.append(Event("closed_data_gap", s.level, NORMAL, "data terputus"))
            s = replace(s, level=NORMAL, level_since=now, escalated=False)
        d.state = s
        return d

    s = state
    if s.no_data_since is not None:
        d.events.append(Event("data_resumed", s.level, s.level, "valid data returned"))
        s = replace(s, no_data_since=None)

    latest = max(recent)
    rules = sorted(cfg.rules, key=lambda r: RANK[r.level])
    satisfied = NORMAL
    for r in rules:
        if _entry_ok(r, _window(by_ts, latest, r.duration_min, cfg.bucket_min)):
            satisfied = r.level

    if RANK[satisfied] > RANK[s.level]:
        rule = cfg.rule(satisfied)
        d.events.append(Event("raised", s.level, satisfied,
                              f"HI>={rule.min_value} selama {rule.duration_min} menit"))
        d.state = replace(s, level=satisfied, level_since=now, escalated=False)
        return d

    for r in rules:
        if (r.escalate_from == s.level and r.escalate_after_min is not None
                and s.level_since is not None and RANK[r.level] > RANK[s.level]
                and now - s.level_since >= timedelta(minutes=r.escalate_after_min)):
            d.events.append(Event("raised", s.level, r.level,
                                  f"{s.level} bertahan {r.escalate_after_min} menit"))
            d.state = replace(s, level=r.level, level_since=now, escalated=True)
            return d

    current = cfg.rule(s.level)
    if current is not None and s.escalated and current.escalate_from:
        current = cfg.rule(current.escalate_from) or current
    if current is not None and _exit_ok(
        current, _window(by_ts, latest, current.exit_duration_min, cfg.bucket_min)
    ):
        target = satisfied if RANK[satisfied] < RANK[current.level] else NORMAL
        d.events.append(Event("lowered", s.level, target,
                              f"HI<{current.exit_value} selama {current.exit_duration_min} menit"))
        d.state = replace(s, level=target, level_since=now, escalated=False)
        return d

    d.state = s
    return d


def needs_alert_message(e: Event) -> bool:
    """Template peringatan_panas_rw: on rising into SIAGA or AWAS (incl. SIAGA -> AWAS)."""
    return e.kind == "raised" and e.to_level in WHATSAPP_LEVELS


def needs_down_message(e: Event) -> bool:
    """Template status_panas_turun: once, when leaving SIAGA/AWAS to below SIAGA by hysteresis.

    Never after a data gap closure (no fake "status turun").
    """
    return (e.kind == "lowered" and e.from_level in WHATSAPP_LEVELS
            and e.to_level not in WHATSAPP_LEVELS)


def confidence_label(n_sensors: int) -> str:
    return "tinggi" if n_sensors >= 2 else "sedang" if n_sensors == 1 else "tidak ada"

"""Per-reading quality control (design doc 10.2).

Flags: ok, suspect, invalid. Only `ok` feeds status. The neighbor check (difference from the
kelurahan median) and the MAD anomaly check need other nodes, so they run in the worker
(app.worker.health) and can downgrade an `ok` reading to `suspect` later.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

OK = "ok"
SUSPECT = "suspect"
INVALID = "invalid"

TEMP_MIN_C, TEMP_MAX_C = 15.0, 50.0
RH_MIN, RH_MAX = 5.0, 100.0
SPIKE_C = 3.0
SPIKE_WINDOW = timedelta(minutes=5, seconds=90)  # 5 min nominal, tolerate jitter
STUCK_COUNT = 6
CONDENSATION_RH = 99.0
CONDENSATION_DURATION = timedelta(hours=2)
LOW_BATTERY_V = 3.3
NEIGHBOR_DIFF_C = 4.0
MAD_Z_LIMIT = 3.5
# Doc 10.2: |z| above the limit "selama lebih dari 1 jam". Checks run every 10 minutes, so the
# node must be anomalous in every check covering the last hour (now, -10, ..., -60 min).
MAD_PERSIST_CHECKS = 7
MAD_CHECK_STEP = timedelta(minutes=10)


@dataclass(frozen=True)
class PastReading:
    ts: datetime
    temp_c: float | None
    rh_pct: float | None


@dataclass
class QcResult:
    flag: str = OK
    reasons: list[str] = field(default_factory=list)

    def mark(self, flag: str, reason: str) -> None:
        self.reasons.append(reason)
        if flag == INVALID or (flag == SUSPECT and self.flag == OK):
            self.flag = flag


def check_reading(ts: datetime, temp_c: float | None, rh_pct: float | None,
                  battery_v: float | None, history: list[PastReading]) -> QcResult:
    """history: earlier readings of the same node (any order), calibrated values."""
    r = QcResult()
    if temp_c is None or rh_pct is None:
        r.mark(INVALID, "missing")
        return r
    if not (TEMP_MIN_C <= temp_c <= TEMP_MAX_C):
        r.mark(INVALID, "temp_range")
    if not (RH_MIN <= rh_pct <= RH_MAX):
        r.mark(INVALID, "rh_range")
    if r.flag == INVALID:
        return r

    past = sorted((h for h in history if h.ts < ts), key=lambda h: h.ts, reverse=True)

    prev = next((h for h in past if h.temp_c is not None), None)
    if prev and ts - prev.ts <= SPIKE_WINDOW and abs(temp_c - prev.temp_c) > SPIKE_C:
        r.mark(SUSPECT, "spike")

    last = past[: STUCK_COUNT - 1]
    if len(last) == STUCK_COUNT - 1 and all(
        h.temp_c == temp_c and h.rh_pct == rh_pct for h in last
    ):
        r.mark(SUSPECT, "stuck")

    if rh_pct > CONDENSATION_RH:
        start = ts
        for h in past:
            if h.rh_pct is None or h.rh_pct <= CONDENSATION_RH:
                break
            start = h.ts
        if ts - start > CONDENSATION_DURATION:
            r.mark(SUSPECT, "condensation")

    if battery_v is not None and battery_v < LOW_BATTERY_V:
        r.mark(SUSPECT, "low_battery")
    return r


def neighbor_outliers(values: dict[str, float]) -> set[str]:
    """Nodes differing > 4 C from the median of the other nodes in the same kelurahan."""
    out: set[str] = set()
    if len(values) < 3:
        return out
    for node_id, v in values.items():
        others = [x for k, x in values.items() if k != node_id]
        if abs(v - median(others)) > NEIGHBOR_DIFF_C:
            out.add(node_id)
    return out


def robust_z_scores(values: dict[str, float]) -> dict[str, float]:
    """Robust z-score 0.6745 * (x - median) / MAD. Empty when fewer than 3 nodes or MAD is 0."""
    if len(values) < 3:
        return {}
    med = median(values.values())
    mad = median(abs(v - med) for v in values.values())
    if mad == 0:
        return {}
    return {k: 0.6745 * (v - med) / mad for k, v in values.items()}


def persistent_anomalies(windows: list[dict[str, float]]) -> dict[str, float]:
    """Nodes with |robust z| > MAD_Z_LIMIT in every window (latest window first).

    Each window is one check's per-node hourly mean for one kelurahan. Returns node -> latest z.
    Fewer windows than MAD_PERSIST_CHECKS means not enough history: no anomaly.
    """
    if len(windows) < MAD_PERSIST_CHECKS:
        return {}
    flagged: dict[str, float] | None = None
    for values in windows[:MAD_PERSIST_CHECKS]:
        hits = {k: z for k, z in robust_z_scores(values).items() if abs(z) > MAD_Z_LIMIT}
        if flagged is None:
            flagged = hits
        else:
            flagged = {k: z for k, z in flagged.items() if k in hits}
        if not flagged:
            return {}
    return flagged or {}

"""Every 10 minutes: RW estimation -> status engine -> alerts -> notifications (doc 13.5, 15.4).

Only tier-A RWs (own sensors with ok data) go through the status engine, so only they can
trigger WhatsApp. Other RWs get an estimate for the map and status TIDAK_ADA_DATA.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import fmean

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import status_engine as se
from app.core.estimation import Point, SensorValue, estimate_rw
from app.core.timeutil import floor_10min, format_decimal_id, format_wib_human, now_utc
from app.models import (
    Alert,
    AlertThreshold,
    HeatmapData,
    Rw,
    RwStatus,
    SatelliteData,
    SatelliteScene,
    SensorNode,
    StatusEvent,
    Village,
)
from app.worker import notifier
from app.worker.whatsapp import TEMPLATE_ALERT, TEMPLATE_DOWN

log = logging.getLogger(__name__)

HISTORY = timedelta(hours=2)


def load_rules(db: Session, rw_id: int | None = None) -> tuple[se.LevelRule, ...]:
    """Active thresholds; an RW-specific row overrides the global row for the same level."""
    rows = db.scalars(select(AlertThreshold).where(
        AlertThreshold.active.is_(True),
        (AlertThreshold.rw_id.is_(None)) | (AlertThreshold.rw_id == rw_id),
    )).all()
    by_level: dict[str, AlertThreshold] = {}
    for r in sorted(rows, key=lambda r: (r.rw_id is not None, r.version)):
        by_level[r.level] = r
    return tuple(
        se.LevelRule(r.level, r.min_value, r.duration_min, r.min_sensors, r.exit_value,
                     r.exit_duration_min, r.escalate_from, r.escalate_after_min)
        for r in by_level.values()
    )


def load_buckets(db: Session, now: datetime) -> dict[int, dict[datetime, dict[str, tuple]]]:
    """rw_id -> bucket ts -> node_id -> (hi_avg, temp_avg, rh_avg). Complete buckets only."""
    end = floor_10min(now)
    rows = db.execute(text("""
        SELECT r.bucket, r.node_id, n.rw_id, r.heat_index_c_avg, r.temp_c_avg, r.rh_pct_avg
        FROM readings_10m r JOIN sensor_nodes n ON n.id = r.node_id
        WHERE r.bucket >= :start AND r.bucket < :end AND n.active AND n.rw_id IS NOT NULL
    """), {"start": end - HISTORY, "end": end}).all()
    out: dict[int, dict[datetime, dict[str, tuple]]] = defaultdict(lambda: defaultdict(dict))
    for bucket, node_id, rw_id, hi, t, rh in rows:
        if hi is not None:
            out[rw_id][bucket][node_id] = (hi, t, rh)
    return out


def _region_name(db: Session, rw: Rw) -> str:
    v = db.get(Village, rw.village_id)
    return f"RW {rw.rw_number}, Kelurahan {v.name}" if v else f"RW {rw.rw_number}"


def _latest_lst(db: Session) -> dict[int, tuple[float, object]]:
    sub = (select(SatelliteData.rw_id, SatelliteData.lst_mean_c, SatelliteScene.acquired_on,
                  func.row_number().over(partition_by=SatelliteData.rw_id,
                                         order_by=SatelliteScene.acquired_on.desc()).label("rn"))
           .join(SatelliteScene, SatelliteScene.id == SatelliteData.scene_id)
           .where(SatelliteScene.accepted.is_(True), SatelliteData.lst_mean_c.is_not(None))
           .subquery())
    rows = db.execute(select(sub.c.rw_id, sub.c.lst_mean_c, sub.c.acquired_on)
                      .where(sub.c.rn == 1)).all()
    return {r[0]: (r[1], r[2]) for r in rows}


def apply_events(db: Session, rw: Rw, decision: se.Decision, now: datetime,
                 hi: float | None, t: float | None, rh: float | None, n_sensors: int,
                 measured_at: datetime | None = None) -> None:
    open_alert = db.scalar(select(Alert).where(Alert.rw_id == rw.id, Alert.source == "auto",
                                              Alert.resolved_at.is_(None))
                           .order_by(Alert.started_at.desc()))
    if open_alert and hi is not None:
        open_alert.peak_hi_c = max(open_alert.peak_hi_c or hi, hi)

    for e in decision.events:
        alert_id = open_alert.id if open_alert else None
        if e.kind in ("raised", "lowered", "closed_data_gap"):
            if open_alert:
                open_alert.resolved_at = now
                open_alert.resolved_reason = {"raised": "naik", "lowered": "histeresis",
                                              "closed_data_gap": "data_terputus"}[e.kind]
                open_alert = None
            if e.kind != "closed_data_gap" and se.RANK[e.to_level] >= se.RANK[se.WASPADA]:
                open_alert = Alert(rw_id=rw.id, level=e.to_level, source="auto", rule=e.reason,
                                   started_at=now, trigger_hi_c=hi, peak_hi_c=hi,
                                   confidence=se.confidence_label(n_sensors))
                db.add(open_alert)
                db.flush()
                alert_id = open_alert.id

        db.add(StatusEvent(rw_id=rw.id, ts=now, kind=e.kind, from_level=e.from_level,
                           to_level=e.to_level, reason=e.reason, heat_index_c=hi,
                           alert_id=alert_id))
        log.info("RW %s %s %s -> %s (%s)", rw.id, e.kind, e.from_level, e.to_level, e.reason)

        name = _region_name(db, rw)
        if (se.needs_alert_message(e) and open_alert is not None
                and t is not None and rh is not None):
            notifier.enqueue(db, open_alert, TEMPLATE_ALERT, e.to_level, [
                e.to_level, name, format_decimal_id(t), format_decimal_id(rh, 0),
                format_decimal_id(hi), format_wib_human(measured_at or now),
            ], now)
        elif se.needs_down_message(e):
            ref = db.scalar(select(Alert).where(Alert.rw_id == rw.id, Alert.source == "auto",
                                               Alert.level == e.from_level)
                            .order_by(Alert.started_at.desc()))
            if ref is not None:
                notifier.enqueue(db, ref, TEMPLATE_DOWN, e.from_level,
                                 [name, e.to_level, format_wib_human(now)], now)


def run(db: Session, now: datetime | None = None) -> None:
    now = now or now_utc()
    ts = floor_10min(now)
    buckets = load_buckets(db, now)
    lst = _latest_lst(db)

    rws = db.execute(select(Rw, func.ST_Y(func.ST_Centroid(Rw.geom)),
                            func.ST_X(func.ST_Centroid(Rw.geom)))).all()
    rw_with_nodes = set(db.scalars(select(SensorNode.rw_id).where(
        SensorNode.active.is_(True), SensorNode.rw_id.is_not(None))).all())

    # Latest valid value per node (last complete bucket within 30 min) for tier A/B estimates.
    node_loc = {n: (lat, lon) for n, lat, lon in db.execute(select(
        SensorNode.id, ST_Y(SensorNode.location), ST_X(SensorNode.location))
        .where(SensorNode.location.is_not(None)))}
    latest_values: list[SensorValue] = []
    rw_latest: dict[int, list[tuple]] = defaultdict(list)
    rw_measured: dict[int, datetime] = {}
    for rw_id, by_ts in buckets.items():
        recent = [b for b in by_ts if b + timedelta(minutes=40) > now]
        if not recent:
            continue
        last = max(recent)
        rw_measured[rw_id] = last + timedelta(minutes=10)  # end of the latest bucket
        for node_id, (hi, t, rh) in by_ts[last].items():
            rw_latest[rw_id].append((hi, t, rh))
            if node_id in node_loc:
                lat, lon = node_loc[node_id]
                latest_values.append(SensorValue(rw_id, Point(lat, lon), t, hi))

    for rw, lat, lon in rws:
        state_row = db.get(RwStatus, rw.id)
        if state_row is None:
            state_row = RwStatus(rw_id=rw.id, level=se.NORMAL)
            db.add(state_row)
        status = se.NO_DATA
        own = rw_latest.get(rw.id, [])
        hi = t = rh = None
        if own:
            hi = fmean(v[0] for v in own)
            t = fmean(v[1] for v in own)
            rhs = [v[2] for v in own if v[2] is not None]
            rh = fmean(rhs) if rhs else None

        if rw.id in rw_with_nodes:
            rules = load_rules(db, rw.id)
            series = [se.Bucket(b, tuple(v[0] for v in nodes.values()))
                      for b, nodes in buckets.get(rw.id, {}).items()]
            state = se.RwState(state_row.level, state_row.level_since, state_row.no_data_since,
                               bool(state_row.escalated))
            decision = se.evaluate(state, series, now, se.EngineConfig(rules=rules))
            apply_events(db, rw, decision, now, hi, t, rh, len(own), rw_measured.get(rw.id))
            state_row.level = decision.state.level
            state_row.level_since = decision.state.level_since
            state_row.no_data_since = decision.state.no_data_since
            state_row.escalated = decision.state.escalated
            status = decision.display_status
        state_row.updated_at = now

        centroid = Point(lat, lon) if lat is not None else None
        est = (estimate_rw(rw.id, centroid, latest_values) if centroid
               else estimate_rw(rw.id, Point(0, 0), [v for v in latest_values if v.rw_id == rw.id]))
        lst_c, lst_date = lst.get(rw.id, (None, None))
        db.merge(HeatmapData(
            rw_id=rw.id, ts=ts, air_temp_c=est.air_temp_c, heat_index_c=est.heat_index_c,
            rh_pct=rh if est.tier == "A" else None, lst_c=lst_c, lst_scene_date=lst_date,
            tier=est.tier, method=est.method, n_sensors=est.n_sensors,
            confidence=est.confidence, status=status if est.tier == "A" else se.NO_DATA,
        ))
    db.commit()

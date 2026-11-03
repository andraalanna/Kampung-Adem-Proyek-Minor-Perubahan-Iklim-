"""Every 10 minutes: node health, neighbor QC, MAD anomaly, gateway outage.

Design doc 10.2, 13.4, 15.10.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.qc import (
    MAD_CHECK_STEP,
    MAD_PERSIST_CHECKS,
    SUSPECT,
    neighbor_outliers,
    persistent_anomalies,
)
from app.core.timeutil import now_utc
from app.models import MaintenanceLog, Rw, SensorNode, SensorReading

log = logging.getLogger(__name__)


def _open_ticket(db: Session, node_id: str | None, kind: str, desc: str) -> None:
    exists = db.scalar(select(MaintenanceLog.id).where(
        MaintenanceLog.node_id == node_id, MaintenanceLog.type == kind,
        MaintenanceLog.resolved.is_(False)).limit(1))
    if exists is None:
        db.add(MaintenanceLog(node_id=node_id, type=kind, description=desc))
        log.warning("ticket %s for %s: %s", kind, node_id, desc)


def update_node_status(db: Session, now: datetime) -> None:
    s = get_settings()
    for n in db.scalars(select(SensorNode).where(SensorNode.active.is_(True))):
        if n.last_seen is None:
            continue
        age = now - n.last_seen
        if age > timedelta(minutes=s.node_offline_min):
            if n.status != "offline":
                _open_ticket(db, n.id, "ticket_offline",
                             "Node tidak mengirim data lebih dari 2 jam. Perlu kunjungan lapangan.")
            n.status = "offline"
        elif age > timedelta(minutes=s.node_late_min):
            n.status = "late"
        else:
            n.status = "online"
        if n.battery_v is not None and n.battery_v < s.low_battery_ticket_v:
            _open_ticket(db, n.id, "ticket_battery", f"Tegangan baterai {n.battery_v:.2f} V.")


def gateway_outage_check(db: Session) -> None:
    """> 50% of nodes in one kelurahan late/offline at once -> suspect gateway/internet."""
    rows = db.execute(select(Rw.village_id, SensorNode.status).join(Rw, Rw.id == SensorNode.rw_id)
                      .where(SensorNode.active.is_(True), SensorNode.last_seen.is_not(None))).all()
    per_village: dict[int, list[str]] = defaultdict(list)
    for village_id, status in rows:
        per_village[village_id].append(status)
    for village_id, statuses in per_village.items():
        down = sum(1 for st in statuses if st in ("late", "offline"))
        if len(statuses) >= 2 and down / len(statuses) > 0.5:
            _open_ticket(db, None, f"gateway_outage_v{village_id}",
                         f"{down}/{len(statuses)} node di kelurahan {village_id} diam. "
                         "Dugaan gateway/internet putus.")


def neighbor_and_anomaly(db: Session, now: datetime) -> None:
    neighbor_check(db, now)
    anomaly_check(db, now)


def neighbor_check(db: Session, now: datetime) -> None:
    """Uses only `ok` readings of the last hour; outliers are downgraded to `suspect`."""
    start = now - timedelta(hours=1)
    rows = db.execute(text("""
        SELECT r.node_id, rw.village_id, avg(r.temp_c) AS t
        FROM sensor_readings r
        JOIN sensor_nodes n ON n.id = r.node_id
        JOIN rw ON rw.id = n.rw_id
        WHERE r.ts >= :start AND r.ts <= :now AND r.qc_flag = 'ok'
        GROUP BY r.node_id, rw.village_id
    """), {"start": start, "now": now}).all()
    per_village: dict[int, dict[str, float]] = defaultdict(dict)
    for node_id, village_id, t in rows:
        per_village[village_id][node_id] = t
    for values in per_village.values():
        for node_id in neighbor_outliers(values):
            db.execute(update(SensorReading).where(
                SensorReading.node_id == node_id, SensorReading.ts >= start,
                SensorReading.ts <= now, SensorReading.qc_flag == "ok",
            ).values(qc_flag=SUSPECT, qc_reasons="neighbor"))
            log.warning("neighbor check: %s differs > 4 C from kelurahan median", node_id)


def anomaly_check(db: Session, now: datetime) -> None:
    """MAD anomaly that must persist for more than 1 hour (doc 10.2) before a ticket opens.

    Uses all non-invalid readings: with only `ok`, a node already flagged by the neighbor
    check would drop out of the reference group and shift the median and MAD of the rest.
    """
    rows = db.execute(text("""
        SELECT k, r.node_id, rw.village_id, avg(r.temp_c) AS t
        FROM generate_series(0, :checks - 1) AS k
        JOIN sensor_readings r
          ON r.ts > :now - (k * :step) - interval '1 hour' AND r.ts <= :now - (k * :step)
        JOIN sensor_nodes n ON n.id = r.node_id
        JOIN rw ON rw.id = n.rw_id
        WHERE r.qc_flag <> 'invalid' AND r.temp_c IS NOT NULL
        GROUP BY k, r.node_id, rw.village_id
    """), {"now": now, "checks": MAD_PERSIST_CHECKS, "step": MAD_CHECK_STEP}).all()
    windows: dict[int, list[dict[str, float]]] = defaultdict(
        lambda: [{} for _ in range(MAD_PERSIST_CHECKS)])
    for k, node_id, village_id, t in rows:
        windows[village_id][k][node_id] = t
    for village_windows in windows.values():
        for node_id, z in persistent_anomalies(village_windows).items():
            _open_ticket(db, node_id, "ticket_anomaly",
                         f"Anomali terhadap node se-kelurahan lebih dari 1 jam "
                         f"(robust z = {z:.1f}). Cek perangkat.")


def run(db: Session, now: datetime | None = None) -> None:
    now = now or now_utc()
    update_node_status(db, now)
    db.flush()
    gateway_outage_check(db)
    neighbor_and_anomaly(db, now)
    db.commit()

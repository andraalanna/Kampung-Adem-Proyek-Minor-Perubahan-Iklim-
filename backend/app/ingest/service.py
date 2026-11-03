"""Uplink processing shared by the MQTT consumer and POST /api/v1/sensors/readings (doc 15.4).

Steps: find node by DevEUI -> decode -> two readings (now, now - 5 min) -> calibration offsets
-> QC -> heat index -> insert (skip duplicates) -> update node last_seen/RSSI/battery.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core import payload as pl
from app.core.heat_index import heat_index_c
from app.core.qc import INVALID, PastReading, check_reading
from app.models import Gateway, SensorNode, SensorReading, UnknownDevice

log = logging.getLogger(__name__)

READ_INTERVAL = timedelta(minutes=5)
DUPLICATE_WINDOW = timedelta(seconds=150)  # half the read interval
QC_HISTORY = timedelta(hours=3)


@dataclass
class GatewayRx:
    gateway_id: str
    rssi: int | None = None
    snr: float | None = None


@dataclass
class Uplink:
    dev_eui: str
    received_at: datetime
    payload: bytes
    f_cnt: int | None = None
    gateways: list[GatewayRx] | None = None


@dataclass
class IngestResult:
    sensor_id: str | None
    accepted: int
    qc: list[str]
    unknown: bool = False


def _best_gateway(db: Session, rx: list[GatewayRx] | None) -> tuple[int | None, GatewayRx | None]:
    if not rx:
        return None, None
    best = max(rx, key=lambda g: g.rssi if g.rssi is not None else -999)
    gw = db.scalar(select(Gateway).where(Gateway.gateway_eui == best.gateway_id.upper()))
    if gw is None:
        gw = db.scalar(select(Gateway).where(Gateway.name == best.gateway_id))
    return (gw.id if gw else None), best


def process_uplink(db: Session, up: Uplink) -> IngestResult:
    dev_eui = up.dev_eui.upper()
    node = db.scalar(select(SensorNode).where(SensorNode.dev_eui == dev_eui))
    if node is None or not node.active:
        db.add(UnknownDevice(dev_eui=dev_eui, received_at=up.received_at,
                             payload_hex=up.payload.hex()))
        db.commit()
        log.warning("uplink from unknown/inactive device %s", dev_eui)
        return IngestResult(None, 0, [], unknown=True)

    decoded = pl.decode(up.payload)  # raises PayloadError -> caller logs/returns 422
    gateway_db_id, best_rx = _best_gateway(db, up.gateways)
    rssi = best_rx.rssi if best_rx else None
    snr = best_rx.snr if best_rx else None

    history = [
        PastReading(r.ts, r.temp_c, r.rh_pct)
        for r in db.scalars(
            select(SensorReading).where(
                SensorReading.node_id == node.id,
                SensorReading.ts > up.received_at - QC_HISTORY,
            )
        )
    ]

    accepted, flags = 0, []
    # prev first so QC of "now" sees it in history
    for ts, reading in ((up.received_at - READ_INTERVAL, decoded.prev),
                        (up.received_at, decoded.now)):
        if reading.temp_c is None and reading.rh_pct is None and ts != up.received_at:
            continue  # no previous reading in this packet (e.g. first after boot)
        exists = db.scalar(select(SensorReading.ts).where(and_(
            SensorReading.node_id == node.id,
            SensorReading.ts.between(ts - DUPLICATE_WINDOW, ts + DUPLICATE_WINDOW),
        )).limit(1))
        if exists is not None:
            continue  # already stored from the previous packet

        t = None if reading.temp_c is None else reading.temp_c + (node.offset_temp or 0.0)
        h = None if reading.rh_pct is None else min(100.0, reading.rh_pct + (node.offset_rh or 0.0))
        q = check_reading(ts, t, h, decoded.battery_v, history)
        hi = heat_index_c(t, h) if q.flag != INVALID else None
        stmt = insert(SensorReading).values(
            node_id=node.id, ts=ts, temp_c=t, rh_pct=h, temp_raw_c=reading.temp_c,
            rh_raw_pct=reading.rh_pct, heat_index_c=hi, battery_v=decoded.battery_v, rssi=rssi,
            snr=snr, gateway_id=gateway_db_id, seq=decoded.seq, qc_flag=q.flag,
            qc_reasons=",".join(q.reasons) or None,
        ).on_conflict_do_nothing(index_elements=["node_id", "ts"])
        db.execute(stmt)
        history.append(PastReading(ts, t, h))
        accepted += 1
        flags.append(q.flag)

    if node.last_seen is None or up.received_at >= node.last_seen:
        node.last_seen = up.received_at
        node.last_seq = decoded.seq
        node.battery_v = decoded.battery_v
        node.rssi, node.snr = rssi, snr
        node.status = "online"
    if gateway_db_id is not None:
        gw = db.get(Gateway, gateway_db_id)
        if gw.last_seen is None or up.received_at > gw.last_seen:
            gw.last_seen = up.received_at
    db.commit()
    return IngestResult(node.id, accepted, flags)

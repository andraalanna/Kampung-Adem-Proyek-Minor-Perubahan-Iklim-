from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.functions import ST_X, ST_Y
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.auth_deps import (
    ADMIN,
    KELURAHAN,
    TEKNIS,
    CurrentUser,
    require_ingest_key,
    require_roles,
    scope_filter,
)
from app.core.payload import PayloadError, parse_hex
from app.core.timeutil import iso_wib
from app.db import get_db
from app.ingest.service import GatewayRx, Uplink, process_uplink
from app.models import AuditLog, SensorNode, SensorReading

router = APIRouter(prefix="/sensors", tags=["sensors"])

# Design doc 14.1: device details are for admin, kelurahan (summary) and teknis, not RT/RW/kader.
can_view_devices = require_roles(ADMIN, KELURAHAN, TEKNIS)

# Hourly aggregates need >= 70 % of the 12 expected 5-minute readings (CLAUDE.md rule 7).
MIN_OK_PER_HOUR = 9
MIN_OK_PER_DAY = 202  # 70 % of 288


def _node_out(n: SensorNode, lat, lon, last: SensorReading | None) -> dict:
    return {
        "id": n.id, "name": n.name, "dev_eui": n.dev_eui, "rw_id": n.rw_id,
        "location": None if lat is None else {"lat": lat, "lon": lon},
        "mount_height_m": n.mount_height_m, "status": n.status, "active": n.active,
        "last_seen": iso_wib(n.last_seen), "battery_v": n.battery_v, "rssi": n.rssi,
        "snr": n.snr, "offset_temp": n.offset_temp, "offset_rh": n.offset_rh,
        "firmware_version": n.firmware_version,
        "last_reading": None if last is None else {
            "ts": iso_wib(last.ts), "temp_c": last.temp_c, "rh_pct": last.rh_pct,
            "heat_index_c": last.heat_index_c, "qc_flag": last.qc_flag,
        },
    }


@router.get("")
def list_sensors(rw_id: int | None = None, status_: str | None = Query(None, alias="status"),
                 page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                 user: CurrentUser = Depends(can_view_devices), db: Session = Depends(get_db)):
    q = select(SensorNode, ST_Y(SensorNode.location), ST_X(SensorNode.location)).where(
        scope_filter(SensorNode.rw_id, user))
    if rw_id is not None:
        q = q.where(SensorNode.rw_id == rw_id)
    if status_:
        q = q.where(SensorNode.status == status_)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(q.order_by(SensorNode.id).offset((page - 1) * page_size).limit(page_size))
    items = []
    for n, lat, lon in rows:
        last = db.scalar(select(SensorReading).where(SensorReading.node_id == n.id)
                         .order_by(SensorReading.ts.desc()).limit(1))
        items.append(_node_out(n, lat, lon, last))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{sensor_id}")
def get_sensor(sensor_id: str, user: CurrentUser = Depends(can_view_devices),
               db: Session = Depends(get_db)):
    row = db.execute(select(SensorNode, ST_Y(SensorNode.location), ST_X(SensorNode.location))
                     .where(SensorNode.id == sensor_id)).first()
    if row is None or (row[0].rw_id is not None and not user.can_see_rw(row[0].rw_id)):
        raise HTTPException(404, "Sensor tidak ditemukan")
    last = db.scalar(select(SensorReading).where(SensorReading.node_id == sensor_id)
                     .order_by(SensorReading.ts.desc()).limit(1))
    return _node_out(row[0], row[1], row[2], last)


@router.get("/{sensor_id}/readings")
def readings(sensor_id: str, from_: datetime = Query(..., alias="from"), to: datetime = Query(...),
             interval: str = Query("10m", pattern="^(raw|10m|1h|1d)$"),
             user: CurrentUser = Depends(can_view_devices), db: Session = Depends(get_db)):
    node = db.get(SensorNode, sensor_id)
    if node is None or (node.rw_id is not None and not user.can_see_rw(node.rw_id)):
        raise HTTPException(404, "Sensor tidak ditemukan")
    if interval == "raw":
        rows = db.scalars(select(SensorReading).where(
            SensorReading.node_id == sensor_id, SensorReading.ts.between(from_, to))
            .order_by(SensorReading.ts)).all()
        points = [{"ts": iso_wib(r.ts), "temp_c": r.temp_c, "rh_pct": r.rh_pct,
                   "heat_index_c": r.heat_index_c, "battery_v": r.battery_v, "rssi": r.rssi,
                   "qc_flag": r.qc_flag, "qc_reasons": r.qc_reasons} for r in rows]
        return {"sensor_id": sensor_id, "interval": interval, "points": points}

    view = {"10m": "readings_10m", "1h": "readings_1h", "1d": "readings_1d"}[interval]
    min_n = {"10m": 1, "1h": MIN_OK_PER_HOUR, "1d": MIN_OK_PER_DAY}[interval]
    rows = db.execute(text(f"""
        SELECT bucket, n_ok, temp_c_avg, temp_c_max, temp_c_min, rh_pct_avg, heat_index_c_max
        FROM {view} WHERE node_id = :id AND bucket BETWEEN :f AND :t ORDER BY bucket
    """), {"id": sensor_id, "f": from_, "t": to}).all()
    # Incomplete buckets are dropped, never filled: the chart shows a gap.
    points = [{"ts": iso_wib(r.bucket), "n_ok": r.n_ok,
               "temp_c_avg": _r(r.temp_c_avg), "temp_c_max": _r(r.temp_c_max),
               "temp_c_min": _r(r.temp_c_min), "rh_pct_avg": _r(r.rh_pct_avg),
               "heat_index_c_max": _r(r.heat_index_c_max), "qc_flag": "ok"}
              for r in rows if r.n_ok >= min_n]
    return {"sensor_id": sensor_id, "interval": interval, "points": points}


def _r(v, d=2):
    return None if v is None else round(v, d)


class GatewayIn(BaseModel):
    gateway_id: str
    rssi: int | None = None
    snr: float | None = None


class ReadingIn(BaseModel):
    dev_eui: str = Field(pattern="^[0-9A-Fa-f]{16}$")
    received_at: datetime
    f_cnt: int | None = None
    payload_hex: str
    gateways: list[GatewayIn] = []


@router.post("/readings", status_code=201, dependencies=[Depends(require_ingest_key)])
def ingest(body: ReadingIn, db: Session = Depends(get_db)):
    if body.received_at.tzinfo is None:
        raise HTTPException(422, "received_at must include a timezone offset")
    try:
        data = parse_hex(body.payload_hex)
        res = process_uplink(db, Uplink(
            dev_eui=body.dev_eui, received_at=body.received_at, payload=data, f_cnt=body.f_cnt,
            gateways=[GatewayRx(g.gateway_id, g.rssi, g.snr) for g in body.gateways]))
    except PayloadError as exc:
        raise HTTPException(422, str(exc)) from exc
    if res.unknown:
        raise HTTPException(404, "Perangkat belum terdaftar atau tidak aktif")
    return {"accepted": res.accepted, "sensor_id": res.sensor_id, "qc": res.qc}


class NodeIn(BaseModel):
    id: str = Field(pattern=r"^KA-[A-Z]{3}-\d{4}$")
    dev_eui: str = Field(pattern="^[0-9A-Fa-f]{16}$")
    name: str | None = None
    rw_id: int | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    mount_height_m: float | None = None
    offset_temp: float = 0.0
    offset_rh: float = 0.0
    installed_at: datetime | None = None
    firmware_version: str | None = None


class NodePatch(BaseModel):
    name: str | None = None
    rw_id: int | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    mount_height_m: float | None = None
    offset_temp: float | None = None
    offset_rh: float | None = None
    active: bool | None = None
    firmware_version: str | None = None


def _point(lat, lon):
    if lat is None or lon is None:
        return None
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)


@router.post("", status_code=201)
def create_node(body: NodeIn, user: CurrentUser = Depends(require_roles(ADMIN, TEKNIS)),
                db: Session = Depends(get_db)):
    if db.get(SensorNode, body.id) or db.scalar(
            select(SensorNode).where(SensorNode.dev_eui == body.dev_eui.upper())):
        raise HTTPException(status.HTTP_409_CONFLICT, "ID atau DevEUI sudah terdaftar")
    n = SensorNode(id=body.id, dev_eui=body.dev_eui.upper(), name=body.name, rw_id=body.rw_id,
                   location=_point(body.lat, body.lon), mount_height_m=body.mount_height_m,
                   offset_temp=body.offset_temp, offset_rh=body.offset_rh,
                   installed_at=body.installed_at, firmware_version=body.firmware_version)
    db.add(n)
    db.add(AuditLog(user_id=user.id, action="create", entity="sensor_node", entity_id=n.id))
    db.commit()
    return {"id": n.id}


@router.patch("/{sensor_id}")
def patch_node(sensor_id: str, body: NodePatch,
               user: CurrentUser = Depends(require_roles(ADMIN, TEKNIS)),
               db: Session = Depends(get_db)):
    n = db.get(SensorNode, sensor_id)
    if n is None:
        raise HTTPException(404, "Sensor tidak ditemukan")
    data = body.model_dump(exclude_unset=True)
    lat, lon = data.pop("lat", None), data.pop("lon", None)
    if lat is not None and lon is not None:
        n.location = _point(lat, lon)
    for k, v in data.items():
        setattr(n, k, v)
    db.add(AuditLog(user_id=user.id, action="update", entity="sensor_node", entity_id=n.id,
                    detail=str(body.model_dump(exclude_unset=True))))
    db.commit()
    return {"id": n.id}


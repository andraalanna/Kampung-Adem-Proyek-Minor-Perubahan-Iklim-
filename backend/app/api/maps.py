"""Heatmap (GeoJSON), regions, per-RW history and dashboard summary."""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_deps import CurrentUser, get_current_user, scope_filter
from app.config import get_settings
from app.core.timeutil import iso_wib, now_utc, wib_day_start_utc
from app.db import get_db
from app.models import (
    Alert,
    District,
    HeatmapData,
    NotificationLog,
    Rw,
    RwStatus,
    SensorNode,
    Village,
)

router = APIRouter(tags=["maps"])

STATUSES = ["NORMAL", "WASPADA", "SIAGA", "AWAS", "TIDAK_ADA_DATA"]


def _rw_name(rw_number: str, village: str) -> str:
    return f"RW {rw_number}, Kel. {village}"


def _r(v, d=1):
    return None if v is None else round(v, d)


@router.get("/heatmap")
def heatmap(level: str = Query("rw", pattern="^(rw|kelurahan)$"),
            kecamatan_id: int | None = None, at: datetime | None = None,
            layer: str = Query("combined", pattern="^(air|lst|combined)$"),
            user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    ts = db.scalar(select(func.max(HeatmapData.ts)).where(
        HeatmapData.ts <= (at or now_utc())))
    q = (select(HeatmapData, Rw.rw_number, Village.name, Village.district_id,
                func.ST_AsGeoJSON(Rw.geom, 6))
         .join(Rw, Rw.id == HeatmapData.rw_id).join(Village, Village.id == Rw.village_id)
         .where(HeatmapData.ts == ts, scope_filter(HeatmapData.rw_id, user)))
    if kecamatan_id is not None:
        q = q.where(Village.district_id == kecamatan_id)
    rows = db.execute(q).all() if ts else []

    features, scene_dates = [], []
    for h, rw_number, village, _district, geojson in rows:
        if h.lst_scene_date:
            scene_dates.append(h.lst_scene_date)
        props = {
            "rw_id": h.rw_id, "name": _rw_name(rw_number, village), "ts": iso_wib(h.ts),
            "status": h.status, "estimate_method": h.method, "tier": h.tier,
            "n_sensors": h.n_sensors, "confidence": h.confidence,
            "is_estimate": h.tier != "A",
        }
        if layer in ("air", "combined"):
            props |= {"air_temp_c": _r(h.air_temp_c), "rh_pct": _r(h.rh_pct, 0),
                      "heat_index_c": _r(h.heat_index_c)}
        if layer in ("lst", "combined"):
            props |= {"lst_c": _r(h.lst_c),
                      "lst_scene_date": h.lst_scene_date.isoformat() if h.lst_scene_date else None}
        features.append({"type": "Feature", "geometry": json.loads(geojson) if geojson else None,
                         "properties": props})

    if level == "kelurahan":
        features = _aggregate_kelurahan(db, features, rows)

    return {
        "type": "FeatureCollection",
        "generated_at": iso_wib(ts),
        "lst_scene_date": max(scene_dates).isoformat() if scene_dates else None,
        "features": features,
    }


def _aggregate_kelurahan(db: Session, rw_features: list[dict], rows) -> list[dict]:
    """Kelurahan view: worst status and max heat index of its tier-A RWs."""
    rank = {s: i for i, s in enumerate(["TIDAK_ADA_DATA", "NORMAL", "WASPADA", "SIAGA", "AWAS"])}
    by_village: dict[str, list[dict]] = {}
    for f, row in zip(rw_features, rows, strict=True):
        by_village.setdefault(row[2], []).append(f["properties"])
    out = []
    for vname, props in by_village.items():
        v = db.execute(select(Village.id, func.ST_AsGeoJSON(Village.geom, 6))
                       .where(Village.name == vname)).first()
        his = [p.get("heat_index_c") for p in props if p["tier"] == "A" and p.get("heat_index_c")]
        out.append({"type": "Feature", "geometry": json.loads(v[1]) if v and v[1] else None,
                    "properties": {
                        "village_id": v[0] if v else None, "name": f"Kel. {vname}",
                        "status": max((p["status"] for p in props), key=lambda s: rank[s]),
                        "heat_index_c": max(his) if his else None, "n_rw": len(props)}})
    return out


@router.get("/regions")
def regions(level: str = Query("rw", pattern="^(kecamatan|kelurahan|rw)$"),
            parent_id: int | None = None, include_geometry: bool = False,
            user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if level == "kecamatan":
        q = select(District.id, District.bps_code, District.name, District.region_id,
                   func.ST_AsGeoJSON(District.geom, 6))
        if parent_id:
            q = q.where(District.region_id == parent_id)
        items = [{"id": i, "level": level, "code": c, "name": n, "parent_id": p,
                  **({"geometry": json.loads(g) if g else None} if include_geometry else {})}
                 for i, c, n, p, g in db.execute(q.order_by(District.name))]
    elif level == "kelurahan":
        q = select(Village.id, Village.bps_code, Village.name, Village.district_id,
                   func.ST_AsGeoJSON(Village.geom, 6))
        if parent_id:
            q = q.where(Village.district_id == parent_id)
        items = [{"id": i, "level": level, "code": c, "name": n, "parent_id": p,
                  **({"geometry": json.loads(g) if g else None} if include_geometry else {})}
                 for i, c, n, p, g in db.execute(q.order_by(Village.name))]
    else:
        q = (select(Rw, Village.bps_code, Village.name, func.ST_AsGeoJSON(Rw.geom, 6))
             .join(Village, Village.id == Rw.village_id).where(scope_filter(Rw.id, user)))
        if parent_id:
            q = q.where(Rw.village_id == parent_id)
        items = [{"id": rw.id, "level": "rw", "code": f"{code}-{rw.rw_number}",
                  "name": f"RW {rw.rw_number}", "village_name": vname,
                  "parent_id": rw.village_id, "population": rw.population,
                  "vulnerable_count": rw.vulnerable_count, "boundary_source": rw.boundary_source,
                  **({"geometry": json.loads(g) if g else None} if include_geometry else {})}
                 for rw, code, vname, g in db.execute(q.order_by(Rw.village_id, Rw.rw_number))]
    return {"items": items}


@router.get("/regions/rw/{rw_id}")
def rw_detail(rw_id: int, hours: int = Query(24, ge=1, le=24 * 31),
              user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.can_see_rw(rw_id):
        raise HTTPException(404, "RW tidak ditemukan")
    row = db.execute(select(Rw, Village.name).join(Village, Village.id == Rw.village_id)
                     .where(Rw.id == rw_id)).first()
    if row is None:
        raise HTTPException(404, "RW tidak ditemukan")
    rw, vname = row
    st = db.get(RwStatus, rw_id)
    hist = db.scalars(select(HeatmapData).where(
        HeatmapData.rw_id == rw_id, HeatmapData.ts >= now_utc() - timedelta(hours=hours))
        .order_by(HeatmapData.ts)).all()
    latest = hist[-1] if hist else None
    n_active = db.scalar(select(func.count()).select_from(SensorNode).where(
        SensorNode.rw_id == rw_id, SensorNode.active.is_(True), SensorNode.status == "online"))
    alert = db.scalar(select(Alert).where(Alert.rw_id == rw_id, Alert.resolved_at.is_(None))
                      .order_by(Alert.started_at.desc()))
    return {
        "id": rw.id, "name": _rw_name(rw.rw_number, vname), "population": rw.population,
        "vulnerable_count": rw.vulnerable_count,
        "status": latest.status if latest else "TIDAK_ADA_DATA",
        "level_since": iso_wib(st.level_since) if st else None,
        "latest": None if latest is None else {
            "ts": iso_wib(latest.ts), "air_temp_c": _r(latest.air_temp_c),
            "rh_pct": _r(latest.rh_pct, 0), "heat_index_c": _r(latest.heat_index_c),
            "lst_c": _r(latest.lst_c),
            "lst_scene_date": latest.lst_scene_date.isoformat() if latest.lst_scene_date else None,
            "tier": latest.tier, "confidence": latest.confidence, "n_sensors": latest.n_sensors},
        "active_sensors": n_active,
        "active_alert": None if alert is None else {
            "id": alert.id, "level": alert.level, "started_at": iso_wib(alert.started_at)},
        "history": [{"ts": iso_wib(h.ts), "heat_index_c": _r(h.heat_index_c),
                     "air_temp_c": _r(h.air_temp_c), "status": h.status, "tier": h.tier}
                    for h in hist],
    }


@router.get("/dashboard/summary")
def summary(kecamatan_id: int | None = None, user: CurrentUser = Depends(get_current_user),
            db: Session = Depends(get_db)):
    ts = db.scalar(select(func.max(HeatmapData.ts)))
    q = (select(HeatmapData, Rw.rw_number, Village.name)
         .join(Rw, Rw.id == HeatmapData.rw_id).join(Village, Village.id == Rw.village_id)
         .where(HeatmapData.ts == ts, scope_filter(HeatmapData.rw_id, user)))
    if kecamatan_id is not None:
        q = q.where(Village.district_id == kecamatan_id)
    rows = db.execute(q).all() if ts else []
    by_status = dict.fromkeys(STATUSES, 0)
    hottest = None
    for h, rw_number, vname in rows:
        by_status[h.status] = by_status.get(h.status, 0) + 1
        if h.tier == "A" and h.heat_index_c is not None and (
                hottest is None or h.heat_index_c > hottest["heat_index_c"]):
            hottest = {"rw_id": h.rw_id, "name": _rw_name(rw_number, vname),
                       "heat_index_c": _r(h.heat_index_c)}

    sensor_counts = dict(db.execute(
        select(SensorNode.status, func.count()).where(
            SensorNode.active.is_(True), scope_filter(SensorNode.rw_id, user))
        .group_by(SensorNode.status)).all())
    active_alerts = db.scalar(select(func.count()).select_from(Alert).where(
        Alert.resolved_at.is_(None), Alert.level.in_(["SIAGA", "AWAS"]),
        scope_filter(Alert.rw_id, user)))
    wa_today = db.scalar(
        select(func.count()).select_from(NotificationLog)
        .join(Alert, Alert.id == NotificationLog.alert_id)
        .where(NotificationLog.status.in_(["sent", "delivered", "read", "dry_run"]),
               NotificationLog.sent_at >= wib_day_start_utc(),
               scope_filter(Alert.rw_id, user)))
    return {
        "as_of": iso_wib(ts),
        "rw_by_status": by_status,
        "hottest_rw": hottest,
        "sensors": {k: sensor_counts.get(k, 0) for k in ("online", "late", "offline")},
        "active_alerts": active_alerts,
        "wa_sent_today": wa_today,
        "wa_dry_run": not get_settings().wa_enabled,
        "bmkg_reference": None,  # BMKG integration not built yet; shown as unavailable in UI
    }

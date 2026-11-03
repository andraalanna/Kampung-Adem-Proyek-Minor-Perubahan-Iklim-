"""SQLAlchemy models. Follows the ERD in the design doc (9.2). Additions beyond the ERD:

- rw_status: current status-engine state per RW (level, since, no-data since).
- status_events: log of every status/alert change (CLAUDE.md: every change must be logged).
- unknown_devices: uplinks from unregistered DevEUIs (design doc 15.4).
- alert_thresholds: exit_value, exit_duration_min, escalate_from, escalate_after_min, version,
  active, approved_note so hysteresis and escalation also live in the table, not in code.
- sensor_readings: seq, qc_reasons, rh/temp raw; notification_logs: queue + webhook fields.
- recipients: phone_hash, opt_out_at.
"""

from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TS = DateTime(timezone=True)


class Base(DeclarativeBase):
    pass


def geom(kind: str):
    # spatial_index=False: GiST indexes are created explicitly in the migration.
    return Geometry(kind, srid=4326, spatial_index=False)


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)  # admin|kelurahan|rtrw|kader|teknis


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone_enc: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class UserScope(Base):
    __tablename__ = "user_scopes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    district_id: Mapped[int | None] = mapped_column(ForeignKey("districts.id"))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    rw_id: Mapped[int | None] = mapped_column(ForeignKey("rw.id"))


class Region(Base):
    __tablename__ = "regions"
    id: Mapped[int] = mapped_column(primary_key=True)
    bps_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    geom = mapped_column(geom("MULTIPOLYGON"), nullable=True)


class District(Base):
    __tablename__ = "districts"
    id: Mapped[int] = mapped_column(primary_key=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("regions.id"), index=True)
    bps_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    geom = mapped_column(geom("MULTIPOLYGON"), nullable=True)


class Village(Base):
    __tablename__ = "villages"
    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"), index=True)
    bps_code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    geom = mapped_column(geom("MULTIPOLYGON"), nullable=True)


class Rw(Base):
    __tablename__ = "rw"
    __table_args__ = (UniqueConstraint("village_id", "rw_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    village_id: Mapped[int] = mapped_column(ForeignKey("villages.id"), index=True)
    rw_number: Mapped[str] = mapped_column(String(8))
    geom = mapped_column(geom("MULTIPOLYGON"), nullable=True)
    population: Mapped[int | None] = mapped_column(Integer)
    vulnerable_count: Mapped[int | None] = mapped_column(Integer)  # counts only, never names
    boundary_source: Mapped[str | None] = mapped_column(String(32))  # digitasi|pemkot|perkiraan


class Gateway(Base):
    __tablename__ = "gateways"
    id: Mapped[int] = mapped_column(primary_key=True)
    gateway_eui: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    village_id: Mapped[int | None] = mapped_column(ForeignKey("villages.id"))
    location = mapped_column(geom("POINT"), nullable=True)
    backhaul: Mapped[str | None] = mapped_column(String(16))  # ethernet|wifi|4g
    last_seen: Mapped[datetime | None] = mapped_column(TS)


class SensorNode(Base):
    __tablename__ = "sensor_nodes"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # KA-SBY-0012
    dev_eui: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    rw_id: Mapped[int | None] = mapped_column(ForeignKey("rw.id"), index=True)
    location = mapped_column(geom("POINT"), nullable=True)
    mount_height_m: Mapped[float | None] = mapped_column(Float)
    offset_temp: Mapped[float] = mapped_column(Float, default=0.0)
    offset_rh: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="new")  # new/online/late/offline
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32))
    installed_at: Mapped[datetime | None] = mapped_column(TS)
    last_seen: Mapped[datetime | None] = mapped_column(TS)
    last_seq: Mapped[int | None] = mapped_column(Integer)
    battery_v: Mapped[float | None] = mapped_column(Float)
    rssi: Mapped[int | None] = mapped_column(Integer)
    snr: Mapped[float | None] = mapped_column(Float)


class SensorReading(Base):
    """TimescaleDB hypertable on ts. Values are calibrated (offsets applied in backend)."""

    __tablename__ = "sensor_readings"
    node_id: Mapped[str] = mapped_column(ForeignKey("sensor_nodes.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    temp_c: Mapped[float | None] = mapped_column(Float)
    rh_pct: Mapped[float | None] = mapped_column(Float)
    temp_raw_c: Mapped[float | None] = mapped_column(Float)
    rh_raw_pct: Mapped[float | None] = mapped_column(Float)
    heat_index_c: Mapped[float | None] = mapped_column(Float)
    battery_v: Mapped[float | None] = mapped_column(Float)
    rssi: Mapped[int | None] = mapped_column(Integer)
    snr: Mapped[float | None] = mapped_column(Float)
    gateway_id: Mapped[int | None] = mapped_column(ForeignKey("gateways.id"))
    seq: Mapped[int | None] = mapped_column(Integer)
    qc_flag: Mapped[str] = mapped_column(String(8))  # ok|suspect|invalid
    qc_reasons: Mapped[str | None] = mapped_column(String(120))


class UnknownDevice(Base):
    __tablename__ = "unknown_devices"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dev_eui: Mapped[str] = mapped_column(String(16), index=True)
    received_at: Mapped[datetime] = mapped_column(TS)
    payload_hex: Mapped[str | None] = mapped_column(Text)


class SatelliteScene(Base):
    __tablename__ = "satellite_scenes"
    __table_args__ = (UniqueConstraint("source", "scene_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32))  # landsat8|landsat9|modis|baseline
    scene_id: Mapped[str] = mapped_column(String(120))
    acquired_on: Mapped[date] = mapped_column(Date)
    cloud_pct: Mapped[float | None] = mapped_column(Float)
    valid_pixel_pct: Mapped[float | None] = mapped_column(Float)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    raster_uri: Mapped[str | None] = mapped_column(Text)
    bounds = mapped_column(geom("POLYGON"), nullable=True)


class SatelliteData(Base):
    __tablename__ = "satellite_data"
    __table_args__ = (UniqueConstraint("scene_id", "rw_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("satellite_scenes.id", ondelete="CASCADE"))
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), index=True)
    lst_mean_c: Mapped[float | None] = mapped_column(Float)
    lst_p90_c: Mapped[float | None] = mapped_column(Float)
    valid_pixel_pct: Mapped[float | None] = mapped_column(Float)


class HeatmapData(Base):
    __tablename__ = "heatmap_data"
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    air_temp_c: Mapped[float | None] = mapped_column(Float)
    heat_index_c: Mapped[float | None] = mapped_column(Float)
    rh_pct: Mapped[float | None] = mapped_column(Float)
    lst_c: Mapped[float | None] = mapped_column(Float)  # land surface temp, NOT air temperature
    lst_scene_date: Mapped[date | None] = mapped_column(Date)
    tier: Mapped[str] = mapped_column(String(1))  # A|B|C|D
    method: Mapped[str] = mapped_column(String(16))
    n_sensors: Mapped[int] = mapped_column(SmallInteger, default=0)
    confidence: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))


class RwStatus(Base):
    __tablename__ = "rw_status"
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    level_since: Mapped[datetime | None] = mapped_column(TS)
    no_data_since: Mapped[datetime | None] = mapped_column(TS)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    updated_at: Mapped[datetime | None] = mapped_column(TS)


class AlertThreshold(Base):
    __tablename__ = "alert_thresholds"
    id: Mapped[int] = mapped_column(primary_key=True)
    rw_id: Mapped[int | None] = mapped_column(ForeignKey("rw.id"))  # NULL = global
    level: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(32), default="heat_index_c")
    min_value: Mapped[float] = mapped_column(Float)
    duration_min: Mapped[int] = mapped_column(Integer)
    min_sensors: Mapped[int] = mapped_column(SmallInteger)
    exit_value: Mapped[float] = mapped_column(Float)
    exit_duration_min: Mapped[int] = mapped_column(Integer)
    escalate_from: Mapped[str | None] = mapped_column(String(16))
    escalate_after_min: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_note: Mapped[str | None] = mapped_column(Text)  # e.g. Dinkes approval reference
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), index=True)
    threshold_id: Mapped[int | None] = mapped_column(ForeignKey("alert_thresholds.id"))
    level: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))  # auto|manual_bmkg|manual_dinkes|manual
    rule: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str | None] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(TS)
    resolved_at: Mapped[datetime | None] = mapped_column(TS)
    resolved_reason: Mapped[str | None] = mapped_column(String(32))
    peak_hi_c: Mapped[float | None] = mapped_column(Float)
    trigger_hi_c: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), index=True)
    ts: Mapped[datetime] = mapped_column(TS, index=True)
    kind: Mapped[str] = mapped_column(String(32))
    from_level: Mapped[str] = mapped_column(String(16))
    to_level: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text)
    heat_index_c: Mapped[float | None] = mapped_column(Float)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"))


class Recipient(Base):
    __tablename__ = "recipients"
    id: Mapped[int] = mapped_column(primary_key=True)
    rw_id: Mapped[int] = mapped_column(ForeignKey("rw.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32))  # ketua_rw|ketua_rt|kader|staf_kelurahan
    phone_enc: Mapped[str] = mapped_column(Text)
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    opt_in_at: Mapped[datetime | None] = mapped_column(TS)
    opt_in_evidence: Mapped[str | None] = mapped_column(Text)
    opt_out_at: Mapped[datetime | None] = mapped_column(TS)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_failure: Mapped[str | None] = mapped_column(String(120))


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id"), index=True)
    recipient_id: Mapped[int] = mapped_column(ForeignKey("recipients.id"), index=True)
    template_name: Mapped[str] = mapped_column(String(64))
    params: Mapped[str | None] = mapped_column(Text)  # JSON list of template body params
    level: Mapped[str | None] = mapped_column(String(16))
    wa_message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # queued|sent|delivered|read|failed|held|dry_run
    status: Mapped[str] = mapped_column(String(16), index=True)
    hold_reason: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(TS)
    status_at: Mapped[datetime | None] = mapped_column(TS)
    confirmed_at: Mapped[datetime | None] = mapped_column(TS)  # recipient replied "1"


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str | None] = mapped_column(ForeignKey("sensor_nodes.id"), index=True)
    gateway_id: Mapped[int | None] = mapped_column(ForeignKey("gateways.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(32))  # ticket|cleaning|battery|replace|calibration
    description: Mapped[str | None] = mapped_column(Text)
    performed_at: Mapped[datetime | None] = mapped_column(TS)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())


class AuditLog(Base):
    """Changes to thresholds, recipients and users (design doc 16.4)."""

    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(TS, server_default=func.now())

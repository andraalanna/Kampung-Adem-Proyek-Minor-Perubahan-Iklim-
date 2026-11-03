"""initial schema: regions, devices, readings hypertable, alerts, notifications

Revision ID: 0001
Revises:
Create Date: 2026-11-02

Requires the timescale/timescaledb-ha image (TimescaleDB + PostGIS).
"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

GEOM_COLUMNS = [
    ("regions", "geom"), ("districts", "geom"), ("villages", "geom"), ("rw", "geom"),
    ("gateways", "location"), ("sensor_nodes", "location"), ("satellite_scenes", "bounds"),
]

ROLES = ["admin", "kelurahan", "rtrw", "kader", "teknis"]

# Default operational thresholds, design doc 13.2 [Usulan, review with Dinkes].
# Stored as data so they can be versioned and changed from the dashboard; code never hardcodes them.
THRESHOLDS = [
    # level,    min, dur, min_sensors, exit, exit_dur, escalate_from, escalate_after
    ("WASPADA", 32.0, 30, 2, 31.0, 60, None, None),
    ("SIAGA", 41.0, 30, 2, 39.0, 60, None, None),
    ("AWAS", 46.0, 30, 2, 44.0, 60, "SIAGA", 180),
]

AGG_SELECT = """
    SELECT node_id,
           time_bucket(INTERVAL '{bucket}', ts) AS bucket,
           count(*) AS n_ok,
           avg(temp_c) AS temp_c_avg, max(temp_c) AS temp_c_max, min(temp_c) AS temp_c_min,
           avg(rh_pct) AS rh_pct_avg, max(rh_pct) AS rh_pct_max, min(rh_pct) AS rh_pct_min,
           avg(heat_index_c) AS heat_index_c_avg, max(heat_index_c) AS heat_index_c_max
    FROM sensor_readings
    WHERE qc_flag = 'ok'
    GROUP BY node_id, bucket
"""

# name, bucket, refresh start offset, refresh schedule
AGGREGATES = [
    ("readings_10m", "10 minutes", "2 hours", "5 minutes"),
    ("readings_1h", "1 hour", "1 day", "30 minutes"),
    ("readings_1d", "1 day", "7 days", "6 hours"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table('regions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('bps_code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bps_code')
    )
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=32), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('satellite_scenes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('scene_id', sa.String(length=120), nullable=False),
    sa.Column('acquired_on', sa.Date(), nullable=False),
    sa.Column('cloud_pct', sa.Float(), nullable=True),
    sa.Column('valid_pixel_pct', sa.Float(), nullable=True),
    sa.Column('accepted', sa.Boolean(), nullable=False),
    sa.Column('raster_uri', sa.Text(), nullable=True),
    sa.Column('bounds', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'scene_id')
    )
    op.create_table('unknown_devices',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('dev_eui', sa.String(length=16), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload_hex', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('districts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('region_id', sa.Integer(), nullable=False),
    sa.Column('bps_code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bps_code')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('phone_enc', sa.Text(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('audit_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('entity', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('detail', sa.Text(), nullable=True),
    sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('villages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('district_id', sa.Integer(), nullable=False),
    sa.Column('bps_code', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bps_code')
    )
    op.create_table('gateways',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gateway_eui', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('village_id', sa.Integer(), nullable=True),
    sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('backhaul', sa.String(length=16), nullable=True),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['village_id'], ['villages.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gateway_eui')
    )
    op.create_table('rw',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('village_id', sa.Integer(), nullable=False),
    sa.Column('rw_number', sa.String(length=8), nullable=False),
    sa.Column('geom', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('population', sa.Integer(), nullable=True),
    sa.Column('vulnerable_count', sa.Integer(), nullable=True),
    sa.Column('boundary_source', sa.String(length=32), nullable=True),
    sa.ForeignKeyConstraint(['village_id'], ['villages.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('village_id', 'rw_number')
    )
    op.create_table('alert_thresholds',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rw_id', sa.Integer(), nullable=True),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('metric', sa.String(length=32), nullable=False),
    sa.Column('min_value', sa.Float(), nullable=False),
    sa.Column('duration_min', sa.Integer(), nullable=False),
    sa.Column('min_sensors', sa.SmallInteger(), nullable=False),
    sa.Column('exit_value', sa.Float(), nullable=False),
    sa.Column('exit_duration_min', sa.Integer(), nullable=False),
    sa.Column('escalate_from', sa.String(length=16), nullable=True),
    sa.Column('escalate_after_min', sa.Integer(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('approved_note', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('heatmap_data',
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('air_temp_c', sa.Float(), nullable=True),
    sa.Column('heat_index_c', sa.Float(), nullable=True),
    sa.Column('rh_pct', sa.Float(), nullable=True),
    sa.Column('lst_c', sa.Float(), nullable=True),
    sa.Column('lst_scene_date', sa.Date(), nullable=True),
    sa.Column('tier', sa.String(length=1), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('n_sensors', sa.SmallInteger(), nullable=False),
    sa.Column('confidence', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('rw_id', 'ts')
    )
    op.create_table('recipients',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('phone_enc', sa.Text(), nullable=False),
    sa.Column('phone_hash', sa.String(length=64), nullable=False),
    sa.Column('opt_in_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('opt_in_evidence', sa.Text(), nullable=True),
    sa.Column('opt_out_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('last_failure', sa.String(length=120), nullable=True),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('rw_status',
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('level_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('no_data_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('rw_id')
    )
    op.create_table('satellite_data',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('scene_id', sa.Integer(), nullable=False),
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('lst_mean_c', sa.Float(), nullable=True),
    sa.Column('lst_p90_c', sa.Float(), nullable=True),
    sa.Column('valid_pixel_pct', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.ForeignKeyConstraint(['scene_id'], ['satellite_scenes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('scene_id', 'rw_id')
    )
    op.create_table('sensor_nodes',
    sa.Column('id', sa.String(length=16), nullable=False),
    sa.Column('dev_eui', sa.String(length=16), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=True),
    sa.Column('rw_id', sa.Integer(), nullable=True),
    sa.Column('location', geoalchemy2.types.Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry'), nullable=True),
    sa.Column('mount_height_m', sa.Float(), nullable=True),
    sa.Column('offset_temp', sa.Float(), nullable=False),
    sa.Column('offset_rh', sa.Float(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('firmware_version', sa.String(length=32), nullable=True),
    sa.Column('installed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seq', sa.Integer(), nullable=True),
    sa.Column('battery_v', sa.Float(), nullable=True),
    sa.Column('rssi', sa.Integer(), nullable=True),
    sa.Column('snr', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dev_eui')
    )
    op.create_table('user_scopes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('district_id', sa.Integer(), nullable=True),
    sa.Column('village_id', sa.Integer(), nullable=True),
    sa.Column('rw_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['village_id'], ['villages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('threshold_id', sa.Integer(), nullable=True),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=32), nullable=False),
    sa.Column('rule', sa.Text(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('confidence', sa.String(length=16), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_reason', sa.String(length=32), nullable=True),
    sa.Column('peak_hi_c', sa.Float(), nullable=True),
    sa.Column('trigger_hi_c', sa.Float(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.ForeignKeyConstraint(['threshold_id'], ['alert_thresholds.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('maintenance_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('node_id', sa.String(length=16), nullable=True),
    sa.Column('gateway_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('performed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['gateway_id'], ['gateways.id'], ),
    sa.ForeignKeyConstraint(['node_id'], ['sensor_nodes.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sensor_readings',
    sa.Column('node_id', sa.String(length=16), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('temp_c', sa.Float(), nullable=True),
    sa.Column('rh_pct', sa.Float(), nullable=True),
    sa.Column('temp_raw_c', sa.Float(), nullable=True),
    sa.Column('rh_raw_pct', sa.Float(), nullable=True),
    sa.Column('heat_index_c', sa.Float(), nullable=True),
    sa.Column('battery_v', sa.Float(), nullable=True),
    sa.Column('rssi', sa.Integer(), nullable=True),
    sa.Column('snr', sa.Float(), nullable=True),
    sa.Column('gateway_id', sa.Integer(), nullable=True),
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('qc_flag', sa.String(length=8), nullable=False),
    sa.Column('qc_reasons', sa.String(length=120), nullable=True),
    sa.ForeignKeyConstraint(['gateway_id'], ['gateways.id'], ),
    sa.ForeignKeyConstraint(['node_id'], ['sensor_nodes.id'], ),
    sa.PrimaryKeyConstraint('node_id', 'ts')
    )
    op.create_table('notification_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.Column('recipient_id', sa.Integer(), nullable=False),
    sa.Column('template_name', sa.String(length=64), nullable=False),
    sa.Column('params', sa.Text(), nullable=True),
    sa.Column('level', sa.String(length=16), nullable=True),
    sa.Column('wa_message_id', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('hold_reason', sa.String(length=32), nullable=True),
    sa.Column('error_code', sa.String(length=64), nullable=True),
    sa.Column('attempts', sa.SmallInteger(), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ),
    sa.ForeignKeyConstraint(['recipient_id'], ['recipients.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('status_events',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('rw_id', sa.Integer(), nullable=False),
    sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('from_level', sa.String(length=16), nullable=False),
    sa.Column('to_level', sa.String(length=16), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('heat_index_c', sa.Float(), nullable=True),
    sa.Column('alert_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ),
    sa.ForeignKeyConstraint(['rw_id'], ['rw.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unknown_devices_dev_eui'), 'unknown_devices', ['dev_eui'], unique=False)
    op.create_index(op.f('ix_districts_region_id'), 'districts', ['region_id'], unique=False)
    op.create_index(op.f('ix_villages_district_id'), 'villages', ['district_id'], unique=False)
    op.create_index(op.f('ix_rw_village_id'), 'rw', ['village_id'], unique=False)
    op.create_index(op.f('ix_recipients_rw_id'), 'recipients', ['rw_id'], unique=False)
    op.create_index(op.f('ix_recipients_phone_hash'), 'recipients', ['phone_hash'], unique=False)
    op.create_index(op.f('ix_satellite_data_rw_id'), 'satellite_data', ['rw_id'], unique=False)
    op.create_index(op.f('ix_sensor_nodes_rw_id'), 'sensor_nodes', ['rw_id'], unique=False)
    op.create_index(op.f('ix_user_scopes_user_id'), 'user_scopes', ['user_id'], unique=False)
    op.create_index(op.f('ix_alerts_rw_id'), 'alerts', ['rw_id'], unique=False)
    op.create_index(op.f('ix_maintenance_logs_node_id'), 'maintenance_logs', ['node_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_alert_id'), 'notification_logs', ['alert_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_recipient_id'), 'notification_logs', ['recipient_id'], unique=False)
    op.create_index(op.f('ix_notification_logs_status'), 'notification_logs', ['status'], unique=False)
    op.create_index(op.f('ix_notification_logs_wa_message_id'), 'notification_logs', ['wa_message_id'], unique=False)
    op.create_index(op.f('ix_status_events_ts'), 'status_events', ['ts'], unique=False)
    op.create_index(op.f('ix_status_events_rw_id'), 'status_events', ['rw_id'], unique=False)

    for table, col in GEOM_COLUMNS:
        op.execute(f"CREATE INDEX ix_{table}_{col}_gist ON {table} USING GIST ({col})")

    op.create_index("ix_sensor_readings_node_ts", "sensor_readings", ["node_id", sa.text("ts DESC")])
    op.create_index("ix_heatmap_data_ts", "heatmap_data", [sa.text("ts DESC")])
    op.execute(
        "SELECT create_hypertable('sensor_readings', 'ts', chunk_time_interval => INTERVAL '7 days')"
    )
    op.execute(
        "ALTER TABLE sensor_readings SET (timescaledb.compress, "
        "timescaledb.compress_segmentby = 'node_id')"
    )
    op.execute("SELECT add_compression_policy('sensor_readings', INTERVAL '30 days')")

    roles = sa.table("roles", sa.column("name", sa.String))
    op.bulk_insert(roles, [{"name": r} for r in ROLES])

    thresholds = sa.table(
        "alert_thresholds",
        *(sa.column(c) for c in ["level", "metric", "min_value", "duration_min", "min_sensors",
                                  "exit_value", "exit_duration_min", "escalate_from",
                                  "escalate_after_min", "version", "active", "approved_note"]),
    )
    op.bulk_insert(thresholds, [
        {"level": lv, "metric": "heat_index_c", "min_value": mn, "duration_min": d,
         "min_sensors": ms, "exit_value": ex, "exit_duration_min": ed, "escalate_from": ef,
         "escalate_after_min": ea, "version": 1, "active": True,
         "approved_note": "Default design doc 13.2 [Usulan], belum dikaji Dinkes"}
        for lv, mn, d, ms, ex, ed, ef, ea in THRESHOLDS
    ])

    # Continuous aggregates cannot be created inside a transaction.
    with op.get_context().autocommit_block():
        for name, bucket, start, every in AGGREGATES:
            op.execute(
                f"CREATE MATERIALIZED VIEW {name} WITH (timescaledb.continuous) AS "
                f"{AGG_SELECT.format(bucket=bucket)} WITH NO DATA"
            )
            op.execute(
                f"SELECT add_continuous_aggregate_policy('{name}', "
                f"start_offset => INTERVAL '{start}', end_offset => NULL, "
                f"schedule_interval => INTERVAL '{every}')"
            )
            # Real-time aggregation so the newest bucket is visible before the refresh runs.
            op.execute(f"ALTER MATERIALIZED VIEW {name} SET (timescaledb.materialized_only = false)")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, *_ in reversed(AGGREGATES):
            op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {name}")
    op.drop_table("status_events")
    op.drop_table("notification_logs")
    op.drop_table("sensor_readings")
    op.drop_table("maintenance_logs")
    op.drop_table("alerts")
    op.drop_table("user_scopes")
    op.drop_table("sensor_nodes")
    op.drop_table("satellite_data")
    op.drop_table("rw_status")
    op.drop_table("recipients")
    op.drop_table("heatmap_data")
    op.drop_table("alert_thresholds")
    op.drop_table("rw")
    op.drop_table("gateways")
    op.drop_table("villages")
    op.drop_table("audit_logs")
    op.drop_table("users")
    op.drop_table("districts")
    op.drop_table("unknown_devices")
    op.drop_table("satellite_scenes")
    op.drop_table("roles")
    op.drop_table("regions")

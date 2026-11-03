from datetime import UTC, datetime, timedelta

import pytest

from app.core import antispam, crypto, payload, qc
from app.core.estimation import Point, SensorValue, estimate_rw
from app.core.heat_index import heat_index_c
from app.core.status_engine import (
    AWAS,
    NO_DATA,
    NORMAL,
    SIAGA,
    WASPADA,
    Bucket,
    EngineConfig,
    LevelRule,
    RwState,
    evaluate,
    needs_alert_message,
    needs_down_message,
)
from app.core.timeutil import WIB, format_decimal_id, format_wib_human, iso_wib

T0 = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)  # 12.00 WIB


# ---------- payload ----------

def test_decode_design_doc_example():
    d = payload.decode(payload.parse_hex("01 08F3 0D7A 17D8 0D86 17C0 B6"))
    assert d.version == 1 and d.seq == 2291
    assert d.now.temp_c == 34.50 and d.now.rh_pct == 61.04
    assert d.prev.temp_c == 34.62 and d.prev.rh_pct == 60.80
    assert d.battery_v == 3.82


def test_roundtrip_and_negative_and_missing():
    raw = payload.encode_v1(65535, -1.25, 99.99, None, None, 4.2)
    d = payload.decode(raw)
    assert d.seq == 65535 and d.now.temp_c == -1.25 and d.now.rh_pct == 99.99
    assert d.prev.temp_c is None and d.prev.rh_pct is None
    assert d.battery_v == 4.2
    assert payload.decode(payload.encode_v1(1, 30, 50, 30, 50, None)).battery_v is None


@pytest.mark.parametrize("data", [b"", b"\x02" + b"\x00" * 11, b"\x01" + b"\x00" * 10])
def test_decode_rejects_bad(data):
    with pytest.raises(payload.PayloadError):
        payload.decode(data)


# ---------- heat index ----------

def test_heat_index_known_values():
    # NWS table: 90 F / 70 % RH -> 106 F (41.1 C)
    assert heat_index_c(32.22, 70) == pytest.approx(41.1, abs=0.3)
    # Below 80 F uses the simple formula, close to air temperature
    assert heat_index_c(25.0, 50) == pytest.approx(25.0, abs=1.0)
    # 100 F / 40 % -> 109 F (42.8 C)
    assert heat_index_c(37.78, 40) == pytest.approx(42.8, abs=0.4)


# ---------- QC ----------

def _past(n, temp=30.0, rh=60.0, step=5):
    return [qc.PastReading(T0 - timedelta(minutes=step * (i + 1)), temp, rh) for i in range(n)]


def test_qc_range_and_missing():
    assert qc.check_reading(T0, 55, 50, 4.0, []).flag == qc.INVALID
    assert qc.check_reading(T0, 30, 2, 4.0, []).flag == qc.INVALID
    assert qc.check_reading(T0, None, 50, 4.0, []).flag == qc.INVALID
    assert qc.check_reading(T0, 30, 60, 4.0, []).flag == qc.OK


def test_qc_spike_stuck_battery():
    assert "spike" in qc.check_reading(T0, 34, 60, 4.0, _past(1, 30.0)).reasons
    assert qc.check_reading(T0, 30, 60, 4.0, _past(5)).reasons == ["stuck"]
    assert qc.check_reading(T0, 30, 60, 4.0, _past(4)).flag == qc.OK
    assert qc.check_reading(T0, 30, 60, 3.2, []).reasons == ["low_battery"]


def test_qc_condensation():
    hist = [qc.PastReading(T0 - timedelta(minutes=5 * (i + 1)), 26 + i * 0.01, 99.5)
            for i in range(25)]
    assert "condensation" in qc.check_reading(T0, 26, 99.6, 4.0, hist).reasons
    assert "condensation" not in qc.check_reading(T0, 26, 99.6, 4.0, hist[:10]).reasons


def test_neighbor_and_mad():
    assert qc.neighbor_outliers({"a": 33, "b": 33.5, "c": 34, "d": 39}) == {"d"}
    z = qc.robust_z_scores({"a": 33, "b": 33.5, "c": 34, "d": 39})
    assert z["d"] > qc.MAD_Z_LIMIT


def test_mad_anomaly_must_persist_one_hour():
    bad = {"a": 33, "b": 33.5, "c": 34, "d": 39}
    calm = {"a": 33, "b": 33.5, "c": 34, "d": 34.2}
    n = qc.MAD_PERSIST_CHECKS
    assert set(qc.persistent_anomalies([bad] * n)) == {"d"}
    # one calm check inside the hour (a transient night-time blip) -> no ticket
    assert qc.persistent_anomalies([bad] * (n - 1) + [calm]) == {}
    # not enough history yet
    assert qc.persistent_anomalies([bad] * (n - 1)) == {}


# ---------- status engine ----------

RULES = (
    LevelRule(WASPADA, 32, 30, 2, 31, 60),
    LevelRule(SIAGA, 41, 30, 2, 39, 60),
    LevelRule(AWAS, 46, 30, 2, 44, 60, escalate_from=SIAGA, escalate_after_min=180),
)
CFG = EngineConfig(rules=RULES)


def series(values, end=T0, n_sensors=2):
    """values oldest -> newest, one per 10-min bucket ending at `end`."""
    out = []
    for i, v in enumerate(reversed(values)):
        ts = end - timedelta(minutes=10 * i)
        out.append(Bucket(ts, () if v is None else (v,) * n_sensors))
    return out


def test_normal_stays_normal():
    d = evaluate(RwState(), series([30, 30, 30]), T0 + timedelta(minutes=10), CFG)
    assert d.display_status == NORMAL and not d.events


def test_needs_full_duration_to_enter_siaga():
    now = T0 + timedelta(minutes=10)
    assert evaluate(RwState(), series([30, 42, 42]), now, CFG).state.level == NORMAL
    d = evaluate(RwState(), series([42, 42]), now, CFG)
    assert d.state.level == NORMAL  # only 20 min
    d = evaluate(RwState(), series([42, 42, 42]), now, CFG)
    assert d.state.level == SIAGA
    assert needs_alert_message(d.events[0])


def test_two_sensors_required_when_available():
    b = [Bucket(T0 - timedelta(minutes=10 * i), (42.0, 40.5, 30.0)) for i in range(3)]
    # mean 37.5 -> not SIAGA; ensure count rule also blocks if mean high but one sensor
    assert evaluate(RwState(), b, T0 + timedelta(minutes=5), CFG).state.level == WASPADA
    b = [Bucket(T0 - timedelta(minutes=10 * i), (50.0, 38.0)) for i in range(3)]
    assert evaluate(RwState(), b, T0 + timedelta(minutes=5), CFG).state.level == WASPADA
    one = series([42, 42, 42], n_sensors=1)
    assert evaluate(RwState(), one, T0 + timedelta(minutes=5), CFG).state.level == SIAGA


def test_hysteresis_exit_needs_60_min_below_exit_value():
    s = RwState(SIAGA, T0 - timedelta(hours=1))
    now = T0 + timedelta(minutes=5)
    assert evaluate(s, series([40] * 6), now, CFG).state.level == SIAGA  # 40 >= 39
    assert evaluate(s, series([45, 38, 38, 38, 38, 38]), now, CFG).state.level == SIAGA
    d = evaluate(s, series([38] * 6), now, CFG)
    assert d.state.level == WASPADA and needs_down_message(d.events[0])
    d = evaluate(s, series([30] * 6), now, CFG)
    assert d.state.level == NORMAL


def test_escalation_siaga_three_hours_to_awas():
    s = RwState(SIAGA, T0 - timedelta(hours=3))
    d = evaluate(s, series([42] * 3), T0 + timedelta(minutes=5), CFG)
    assert d.state.level == AWAS and needs_alert_message(d.events[0])


def test_awas_to_siaga_sends_no_message():
    s = RwState(AWAS, T0 - timedelta(hours=1))
    d = evaluate(s, series([42] * 6), T0 + timedelta(minutes=5), CFG)
    assert d.state.level == SIAGA
    assert not needs_alert_message(d.events[0]) and not needs_down_message(d.events[0])


def test_no_data_then_gap_close_without_down_message():
    s = RwState(SIAGA, T0 - timedelta(hours=1))
    stale = series([42] * 3, end=T0 - timedelta(minutes=40))
    d = evaluate(s, stale, T0, CFG)
    assert d.display_status == NO_DATA and d.state.level == SIAGA
    d2 = evaluate(d.state, [], T0 + timedelta(hours=3), CFG)
    assert d2.state.level == NORMAL and d2.events[-1].kind == "closed_data_gap"
    assert not any(needs_down_message(e) for e in d2.events)


# ---------- anti-spam ----------

def test_antispam():
    cfg = antispam.AntiSpamConfig()
    night = datetime(2026, 11, 2, 22, 0, tzinfo=WIB)
    day = datetime(2026, 11, 2, 13, 0, tzinfo=WIB)
    assert antispam.recipient_hold_reason(SIAGA, night, 0, cfg) == "quiet_hours"
    assert antispam.recipient_hold_reason(AWAS, night, 0, cfg) is None
    assert antispam.recipient_hold_reason(SIAGA, day, 3, cfg) == "daily_limit"
    assert antispam.recipient_hold_reason(SIAGA, day, 2, cfg) is None
    assert antispam.rw_cooldown_reason(SIAGA, day, day - timedelta(hours=2), cfg) == "cooldown"
    assert antispam.rw_cooldown_reason(SIAGA, day, day - timedelta(hours=3), cfg) is None


# ---------- crypto ----------

def test_phone_crypto():
    import base64
    import os
    key = base64.b64encode(os.urandom(32)).decode()
    p = crypto.normalize_phone("0812-3456-7890")
    assert p == "6281234567890"
    assert crypto.decrypt_phone(crypto.encrypt_phone(p, key), key) == p
    assert crypto.hash_phone(p, key) == crypto.hash_phone(p, key)
    assert crypto.mask_phone(p) == "0812xxxxx890"
    with pytest.raises(ValueError):
        crypto.normalize_phone("123")


# ---------- estimation ----------

def test_estimation_tiers():
    c = Point(-7.2575, 112.7521)
    s_own = SensorValue(1, Point(-7.2576, 112.7522), 35.0, 42.0)
    s_near = SensorValue(2, Point(-7.2650, 112.7521), 34.0, 40.0)  # ~830 m
    s_far = SensorValue(3, Point(-7.3500, 112.7521), 30.0, 33.0)  # ~10 km
    assert estimate_rw(1, c, [s_own, s_near]).tier == "A"
    e = estimate_rw(9, c, [s_near, s_far])
    assert e.tier == "B" and e.heat_index_c == pytest.approx(40.0)
    assert estimate_rw(9, c, [s_far]).tier == "D"


# ---------- time ----------

def test_time_formats():
    assert iso_wib(T0) == "2026-11-02T12:00:00+07:00"
    assert format_wib_human(T0 + timedelta(minutes=100)) == "2 Nov 2026 13.40 WIB"
    assert format_decimal_id(35.14) == "35,1"


def test_escalated_awas_leaves_by_siaga_exit_rule():
    s = RwState(SIAGA, T0 - timedelta(hours=3))
    d = evaluate(s, series([42] * 6), T0 + timedelta(minutes=5), CFG)
    assert d.state.level == AWAS and d.state.escalated
    # HI stays ~42: below AWAS exit (44) but above SIAGA exit (39) -> must stay AWAS, no flapping
    d2 = evaluate(d.state, series([42] * 6, end=T0 + timedelta(minutes=10)),
                  T0 + timedelta(minutes=15), CFG)
    assert d2.state.level == AWAS and not d2.events
    # 60 min below SIAGA's exit value -> leaves, and a "turun" message is due
    d3 = evaluate(d.state, series([37] * 6, end=T0 + timedelta(hours=1)),
                  T0 + timedelta(hours=1, minutes=5), CFG)
    assert d3.state.level == WASPADA and not d3.state.escalated
    assert needs_down_message(d3.events[0])


def test_awas_entered_directly_uses_own_exit_rule():
    s = RwState(AWAS, T0 - timedelta(hours=1))
    d = evaluate(s, series([42] * 6), T0 + timedelta(minutes=5), CFG)
    assert d.state.level == SIAGA

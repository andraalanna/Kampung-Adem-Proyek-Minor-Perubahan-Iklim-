"""Uplink payload decoder. See CLAUDE.md "Uplink payload v1" and docs/payload.md.

v1, 12 bytes, big-endian:
  0     version   uint8 (= 1)
  1-2   seq       uint16
  3-4   temp_now  int16  x0.01 C
  5-6   rh_now    uint16 x0.01 %
  7-8   temp_prev int16  x0.01 C
  9-10  rh_prev   uint16 x0.01 %
  11    battery   uint8  V = 2.00 + raw * 0.01 (raw 0 = not measured)

Sentinels written by firmware when a reading is missing (sensor error or no previous reading):
  temp 0x7FFF, rh 0xFFFF -> decoded as None.
"""

import struct
from dataclasses import dataclass

PAYLOAD_V1_LEN = 12
TEMP_MISSING = 0x7FFF
RH_MISSING = 0xFFFF
BATTERY_OFFSET_V = 2.0
BATTERY_STEP_V = 0.01


class PayloadError(ValueError):
    pass


@dataclass(frozen=True)
class DecodedReading:
    temp_c: float | None
    rh_pct: float | None


@dataclass(frozen=True)
class DecodedUplink:
    version: int
    seq: int
    now: DecodedReading
    prev: DecodedReading
    battery_v: float | None


def parse_hex(payload_hex: str) -> bytes:
    cleaned = "".join(payload_hex.split())
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise PayloadError(f"invalid hex payload: {exc}") from exc


def _temp(raw: int) -> float | None:
    return None if raw == TEMP_MISSING else raw / 100.0


def _rh(raw: int) -> float | None:
    return None if raw == RH_MISSING else raw / 100.0


def decode_battery(raw: int) -> float | None:
    return None if raw == 0 else round(BATTERY_OFFSET_V + raw * BATTERY_STEP_V, 2)


def decode(data: bytes) -> DecodedUplink:
    if not data:
        raise PayloadError("empty payload")
    version = data[0]
    if version != 1:
        raise PayloadError(f"unsupported payload version {version}")
    if len(data) != PAYLOAD_V1_LEN:
        raise PayloadError(f"v1 payload must be {PAYLOAD_V1_LEN} bytes, got {len(data)}")
    _, seq, t_now, rh_now, t_prev, rh_prev, batt = struct.unpack(">BHhHhHB", data)
    return DecodedUplink(
        version=version,
        seq=seq,
        now=DecodedReading(_temp(t_now), _rh(rh_now)),
        prev=DecodedReading(_temp(t_prev), _rh(rh_prev)),
        battery_v=decode_battery(batt),
    )


def encode_v1(seq: int, temp_now: float | None, rh_now: float | None,
              temp_prev: float | None, rh_prev: float | None, battery_v: float | None) -> bytes:
    """Reference encoder (mirrors firmware); used by tests and the simulator."""

    def t(v: float | None) -> int:
        return TEMP_MISSING if v is None else round(v * 100)

    def h(v: float | None) -> int:
        return RH_MISSING if v is None else round(v * 100)

    if battery_v is None:
        b = 0
    else:
        b = max(1, min(255, round((battery_v - BATTERY_OFFSET_V) / BATTERY_STEP_V)))
    return struct.pack(">BHhHhHB", 1, seq & 0xFFFF, t(temp_now), h(rh_now), t(temp_prev),
                       h(rh_prev), b)

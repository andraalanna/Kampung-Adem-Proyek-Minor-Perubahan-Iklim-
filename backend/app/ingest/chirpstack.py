"""Parse ChirpStack v4 uplink events (JSON marshaler) into `Uplink`."""

import base64
from datetime import UTC, datetime

from app.ingest.service import GatewayRx, Uplink


def parse_uplink_event(event: dict) -> Uplink:
    info = event["deviceInfo"]
    ts_raw = event.get("time")
    received_at = (
        datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else datetime.now(UTC)
    )
    gateways = [
        GatewayRx(gateway_id=rx.get("gatewayId", ""), rssi=rx.get("rssi"), snr=rx.get("snr"))
        for rx in event.get("rxInfo", [])
    ]
    return Uplink(
        dev_eui=info["devEui"],
        received_at=received_at,
        payload=base64.b64decode(event.get("data", "")),
        f_cnt=event.get("fCnt"),
        gateways=gateways,
    )

"""ChirpStack MQTT consumer. Run: python -m app.ingest.mqtt"""

import asyncio
import json
import logging

import aiomqtt

from app.config import get_settings
from app.core.payload import PayloadError
from app.db import SessionLocal
from app.ingest.chirpstack import parse_uplink_event
from app.ingest.service import process_uplink

log = logging.getLogger("ingest")


def _handle(raw: bytes) -> None:
    try:
        up = parse_uplink_event(json.loads(raw))
    except (KeyError, ValueError) as exc:
        log.error("malformed uplink event: %s", exc)
        return
    with SessionLocal() as db:
        try:
            res = process_uplink(db, up)
            log.info("uplink %s -> node=%s accepted=%s qc=%s", up.dev_eui, res.sensor_id,
                     res.accepted, res.qc)
        except PayloadError as exc:
            log.error("bad payload from %s: %s", up.dev_eui, exc)


async def run() -> None:
    s = get_settings()
    while True:
        try:
            async with aiomqtt.Client(s.mqtt_host, s.mqtt_port, username=s.mqtt_username,
                                      password=s.mqtt_password, identifier="kampungadem-ingest",
                                      clean_session=False) as client:
                await client.subscribe(s.mqtt_topic, qos=1)
                log.info("subscribed to %s", s.mqtt_topic)
                async for msg in client.messages:
                    await asyncio.to_thread(_handle, msg.payload)
        except aiomqtt.MqttError as exc:
            log.warning("MQTT connection lost (%s); retrying in 5 s", exc)
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(run())

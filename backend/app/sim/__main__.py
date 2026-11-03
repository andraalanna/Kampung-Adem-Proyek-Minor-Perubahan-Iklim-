"""Simulator CLI.

    python -m app.sim seed                    # demo regions, nodes, users, recipients
    python -m app.sim backfill --hours 24     # fast-forward: past uplinks + status runs
    python -m app.sim live [--boost 2]        # send an uplink per node every 10 minutes
    python -m app.sim demo                    # seed + backfill 24 h + live

Uplinks go through the real ingest code (payload v1 encode -> decode -> QC -> DB), so the
backend is exercised exactly as with real hardware. All values are fake.
"""

import argparse
import logging
import random
import time
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.payload import encode_v1
from app.core.timeutil import floor_10min, now_utc
from app.db import SessionLocal
from app.ingest.service import GatewayRx, Uplink, process_uplink
from app.models import SensorNode
from app.sim import demo
from app.sim.weather import SimNode, battery, drops_packet, reading
from app.worker import health_job, notifier, status_job

log = logging.getLogger("sim")
STEP = timedelta(minutes=10)


def _seq_start(db, node: SimNode) -> int:
    n = db.get(SensorNode, node.node_id)
    return (n.last_seq + 1) if n and n.last_seq is not None else 1


def send_all(db, nodes: list[SimNode], t: datetime, seqs: dict[str, int], rng: random.Random,
             boost: float) -> int:
    sent = 0
    for n in nodes:
        seq = seqs[n.node_id]
        seqs[n.node_id] = (seq + 1) & 0xFFFF
        if drops_packet(n, t, rng):
            continue  # lost packet: the seq gap is visible to the backend
        prev_t, prev_rh = reading(n, t - timedelta(minutes=5), rng, boost)
        now_t, now_rh = reading(n, t, rng, boost)
        payload = encode_v1(seq, now_t, now_rh, prev_t, prev_rh, battery(n, t))
        process_uplink(db, Uplink(
            dev_eui=n.dev_eui, received_at=t, payload=payload,
            gateways=[GatewayRx("SIM-GW-01", rssi=rng.randint(-112, -85),
                                snr=round(rng.uniform(-8, 6), 1))],
        ))
        sent += 1
    return sent


def backfill(hours: int, boost: float, seed: int = 1) -> None:
    rng = random.Random(seed)
    nodes = demo.sim_nodes()
    end = floor_10min(now_utc())
    t = end - timedelta(hours=hours)
    with SessionLocal() as db:
        latest = db.scalar(select(SensorNode.last_seen).order_by(
            SensorNode.last_seen.desc().nulls_last()).limit(1))
        if latest and latest > t:
            t = floor_10min(latest) + STEP
        seqs = {n.node_id: _seq_start(db, n) for n in nodes}
        steps = 0
        while t <= end:
            send_all(db, nodes, t, seqs, rng, boost)
            # Same order and offsets as the real worker: health at :01, status at :02.
            health_job.run(db, now=t + timedelta(minutes=1))
            status_job.run(db, now=t + timedelta(minutes=2))
            notifier.send_due(db, now=t + timedelta(minutes=2))
            t += STEP
            steps += 1
            if steps % 18 == 0:
                log.info("backfill at %s", t.isoformat())
        health_job.run(db)
    log.info("backfill done: %d steps", steps)


def live(boost: float) -> None:
    rng = random.Random()
    nodes = demo.sim_nodes()
    with SessionLocal() as db:
        seqs = {n.node_id: _seq_start(db, n) for n in nodes}
    while True:
        t = now_utc()
        with SessionLocal() as db:
            sent = send_all(db, nodes, t, seqs, rng, boost)
        log.info("sent %d uplinks at %s", sent, t.isoformat(timespec="seconds"))
        nxt = floor_10min(t) + STEP
        time.sleep(max(5.0, (nxt - now_utc()).total_seconds()))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.sim")
    ap.add_argument("command", choices=["seed", "backfill", "live", "demo"])
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--boost", type=float, default=0.0,
                    help="extra degrees C on all nodes, e.g. 2 to force SIAGA/AWAS in a demo")
    a = ap.parse_args()
    if a.command in ("seed", "demo"):
        with SessionLocal() as db:
            ids = demo.seed(db)
        log.info("seeded %d RW; demo login password: %s", len(ids), demo.DEMO_PASSWORD)
    if a.command in ("backfill", "demo"):
        backfill(a.hours, a.boost)
    if a.command in ("live", "demo"):
        live(a.boost)


if __name__ == "__main__":
    main()

"""Synthetic air temperature / humidity for a Surabaya-like day. Pure functions, testable."""

import math
import random
from dataclasses import dataclass
from datetime import datetime

from app.core.timeutil import to_wib


@dataclass(frozen=True)
class SimNode:
    node_id: str
    dev_eui: str
    rw_key: str
    lat: float
    lon: float
    heat_offset_c: float  # how much hotter than the city baseline this spot is
    fault: str | None = None  # None | "dropout" | "low_battery" | "drift"


def diurnal(dt: datetime) -> float:
    """0 at ~05.00 WIB (coolest), 1 at ~14.00 WIB (hottest)."""
    d = to_wib(dt)
    h = d.hour + d.minute / 60
    if 5 <= h <= 14:
        return 0.5 - 0.5 * math.cos(math.pi * (h - 5) / 9)
    hours_since_peak = (h - 14) % 24
    return 0.5 + 0.5 * math.cos(math.pi * hours_since_peak / 15)


def reading(node: SimNode, dt: datetime, rng: random.Random, boost_c: float = 0.0
            ) -> tuple[float, float]:
    """(temp_c, rh_pct) at time dt. Baseline 26.5-33 C, RH 85-55 %, plus the node's offset."""
    f = diurnal(dt)
    temp = 26.5 + 6.5 * f + node.heat_offset_c * (0.4 + 0.6 * f) + boost_c
    temp += rng.gauss(0, 0.15)
    rh = 85 - 30 * f - node.heat_offset_c * 1.5 + rng.gauss(0, 1.0)
    if node.fault == "drift":
        temp += 7.0  # sensor reading far too high (e.g. shield in direct sun)
    return round(temp, 2), round(max(20.0, min(99.0, rh)), 2)


def battery(node: SimNode, dt: datetime) -> float:
    if node.fault == "low_battery":
        return 3.25
    return round(3.9 + 0.2 * diurnal(dt), 2)  # solar charging during the day


def drops_packet(node: SimNode, dt: datetime, rng: random.Random) -> bool:
    if node.fault == "dropout":
        # Off-air for a whole hour every 4 hours (gateway/battery issue), else 5 % loss.
        return to_wib(dt).hour % 4 == 0 or rng.random() < 0.05
    return rng.random() < 0.02

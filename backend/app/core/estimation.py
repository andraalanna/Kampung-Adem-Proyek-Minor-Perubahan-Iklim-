"""Per-RW estimation tiers (design doc 10.5).

Tier A: RW has >= 1 valid sensor in the last 30 min -> mean of its sensors.
Tier B: no own sensor, sensors within 2 km -> IDW (power 2). Shown as "perkiraan", never alerts.
Tier C: (pilot, >= 5 active sensors) regression on LST baseline + IDW residuals. Not implemented
        yet; falls back to tier B, which the design doc allows.
Tier D: nothing within 2 km -> LST only, status TIDAK_ADA_DATA.
"""

import math
from dataclasses import dataclass
from statistics import fmean

IDW_RADIUS_M = 2000.0
IDW_POWER = 2.0


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float


@dataclass(frozen=True)
class SensorValue:
    rw_id: int
    location: Point
    air_temp_c: float
    heat_index_c: float


@dataclass(frozen=True)
class Estimate:
    tier: str  # A | B | D
    method: str  # sensor | idw | lst_only
    air_temp_c: float | None
    heat_index_c: float | None
    n_sensors: int
    confidence: str  # tinggi | sedang | rendah | tidak ada


def haversine_m(a: Point, b: Point) -> float:
    r = 6371000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def estimate_rw(rw_id: int, centroid: Point, sensors: list[SensorValue]) -> Estimate:
    own = [s for s in sensors if s.rw_id == rw_id]
    if own:
        return Estimate("A", "sensor", fmean(s.air_temp_c for s in own),
                        fmean(s.heat_index_c for s in own), len(own),
                        "tinggi" if len(own) >= 2 else "sedang")

    near = []
    for s in sensors:
        d = haversine_m(centroid, s.location)
        if d <= IDW_RADIUS_M:
            near.append((max(d, 1.0), s))
    if near:
        w = [1.0 / d**IDW_POWER for d, _ in near]
        tw = sum(w)
        t = sum(wi * s.air_temp_c for wi, (_, s) in zip(w, near, strict=True)) / tw
        hi = sum(wi * s.heat_index_c for wi, (_, s) in zip(w, near, strict=True)) / tw
        return Estimate("B", "idw", t, hi, len(near), "rendah")

    return Estimate("D", "lst_only", None, None, 0, "tidak ada")

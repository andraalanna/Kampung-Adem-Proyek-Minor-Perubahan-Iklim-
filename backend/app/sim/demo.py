"""Demo dataset: 3 fake kelurahan, 10 RW, 13 simulated nodes, demo users and recipients."""

import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth_deps import hash_password
from app.config import get_settings
from app.core.crypto import encrypt_phone, hash_phone
from app.core.timeutil import now_utc
from app.models import (
    District,
    Recipient,
    Region,
    Role,
    Rw,
    SatelliteData,
    SatelliteScene,
    SensorNode,
    User,
    UserScope,
    Village,
)
from app.sim.weather import SimNode

DEMO_PASSWORD = "adem-demo-2026"  # demo accounts only; never use on a real deployment

# Grid of 400 m cells over central Surabaya. (village_key, rw_number, col, row)
CELL_DEG = 0.0036
ORIGIN_LON, ORIGIN_LAT = 112.735, -7.245
VILLAGES = {
    "A": ("Demo Utara", "3578990001"),
    "B": ("Demo Selatan", "3578990002"),
    "C": ("Demo Pinggir", "3578990003"),
}
RWS = [
    ("A", "01", 0, 0), ("A", "02", 1, 0), ("A", "03", 2, 0), ("A", "04", 3, 0),
    ("B", "01", 0, 1), ("B", "02", 1, 1), ("B", "03", 2, 1), ("B", "04", 3, 1),
    # far away, no sensors within 2 km -> tier D (LST only)
    ("C", "01", 10, 4), ("C", "02", 11, 4),
]

# rw key -> (heat offset C, number of nodes, fault of 2nd node)
RW_PROFILE = {
    "A01": (0.0, 2, None),          # mild: NORMAL/WASPADA
    "A02": (1.2, 2, None),          # WASPADA most afternoons
    "A03": (2.6, 2, None),          # dense kampung: SIAGA in the afternoon
    "A04": (3.6, 2, None),          # hottest: reaches AWAS
    "B01": (0.8, 2, "drift"),       # one faulty sensor -> neighbor/MAD QC ticket
    "B02": (1.8, 1, None),          # single sensor -> confidence "sedang"
    "B03": (0.0, 0, None),          # no own sensor -> tier B (IDW estimate)
    "B04": (2.2, 2, "dropout"),     # intermittent node -> late/offline, gaps in charts
    "C01": (1.5, 0, None),          # offsets of C01/C02 only shape the fake LST layer
    "C02": (0.5, 0, None),
}
LOW_BATTERY_NODE = "A02"  # 2nd node of this RW reports low battery


def rw_key(village_key: str, number: str) -> str:
    return f"{village_key}{number}"


def _square(col: int, row: int) -> str:
    x0 = ORIGIN_LON + col * CELL_DEG
    y0 = ORIGIN_LAT - row * CELL_DEG
    x1, y1 = x0 + CELL_DEG, y0 - CELL_DEG
    return f"MULTIPOLYGON((({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0})))"


def sim_nodes() -> list[SimNode]:
    nodes, i = [], 1
    for vk, num, col, row in RWS:
        key = rw_key(vk, num)
        offset, n, fault2 = RW_PROFILE[key]
        for k in range(n):
            lon = ORIGIN_LON + (col + 0.3 + 0.4 * k) * CELL_DEG
            lat = ORIGIN_LAT - (row + 0.35 + 0.3 * k) * CELL_DEG
            fault = fault2 if k == 1 else None
            if key == LOW_BATTERY_NODE and k == 1:
                fault = "low_battery"
            nodes.append(SimNode(
                node_id=f"KA-SBY-{i:04d}", dev_eui=f"DEADBEEF{i:08X}", rw_key=key,
                lat=lat, lon=lon, heat_offset_c=offset + (0.3 if k else 0.0), fault=fault,
            ))
            i += 1
    return nodes


def seed(db: Session) -> dict[str, int]:
    """Idempotent: creates regions, nodes, users and recipients if missing. Returns rw ids."""
    s = get_settings()
    if not (s.phone_enc_key and s.phone_hash_key):
        raise SystemExit("PHONE_ENC_KEY and PHONE_HASH_KEY must be set (see infra/dev.env)")

    region = db.scalar(select(Region).where(Region.bps_code == "3578"))
    if region is None:
        region = Region(bps_code="3578", name="Kota Surabaya")
        db.add(region)
        db.flush()
    district = db.scalar(select(District).where(District.bps_code == "357899"))
    if district is None:
        district = District(region_id=region.id, bps_code="357899", name="Kecamatan Demo")
        db.add(district)
        db.flush()

    village_ids = {}
    for vk, (name, code) in VILLAGES.items():
        v = db.scalar(select(Village).where(Village.bps_code == code))
        if v is None:
            v = Village(district_id=district.id, bps_code=code, name=name)
            db.add(v)
            db.flush()
        village_ids[vk] = v.id

    rw_ids: dict[str, int] = {}
    for vk, num, col, row in RWS:
        rw = db.scalar(select(Rw).where(Rw.village_id == village_ids[vk], Rw.rw_number == num))
        if rw is None:
            rw = Rw(village_id=village_ids[vk], rw_number=num,
                    geom=func.ST_GeomFromText(_square(col, row), 4326),
                    population=1500 + 150 * col, vulnerable_count=180 + 25 * col,
                    boundary_source="dummy_demo")
            db.add(rw)
            db.flush()
        rw_ids[rw_key(vk, num)] = rw.id
    db.flush()
    for v in db.scalars(select(Village).where(Village.id.in_(village_ids.values()))):
        v.geom = db.scalar(select(func.ST_Multi(func.ST_Union(Rw.geom)))
                           .where(Rw.village_id == v.id))
    district.geom = db.scalar(select(func.ST_Multi(func.ST_Union(Village.geom)))
                              .where(Village.district_id == district.id))

    installed = now_utc() - timedelta(days=30)
    for n in sim_nodes():
        if db.get(SensorNode, n.node_id) is None:
            db.add(SensorNode(
                id=n.node_id, dev_eui=n.dev_eui, name=f"Simulasi RW {n.rw_key[1:]} {n.rw_key[0]}",
                rw_id=rw_ids[n.rw_key],
                location=func.ST_SetSRID(func.ST_MakePoint(n.lon, n.lat), 4326),
                mount_height_m=2.2, offset_temp=-0.1, offset_rh=0.5,
                firmware_version="sim-1", installed_at=installed,
            ))

    roles = dict(db.execute(select(Role.name, Role.id)).all())
    users = [
        ("Admin Demo", "admin@demo.kampungadem.id", "admin", {}),
        ("Staf Kelurahan Demo", "kelurahan@demo.kampungadem.id", "kelurahan",
         {"village_id": village_ids["A"]}),
        ("Ketua RW 03 Demo", "rw03@demo.kampungadem.id", "rtrw", {"rw_id": rw_ids["A03"]}),
        ("Kader Demo", "kader@demo.kampungadem.id", "kader", {"rw_id": rw_ids["A04"]}),
        ("Tim Teknis Demo", "teknis@demo.kampungadem.id", "teknis", {}),
    ]
    for name, email, role, scope in users:
        if db.scalar(select(User).where(User.email == email)) is None:
            u = User(name=name, email=email, password_hash=hash_password(DEMO_PASSWORD),
                     role_id=roles[role])
            db.add(u)
            db.flush()
            if scope:
                db.add(UserScope(user_id=u.id, **scope))

    # Fake numbers in the 0800 range (not mobile numbers). WhatsApp stays in dry-run.
    k = 1
    for key, rw_id in rw_ids.items():
        if RW_PROFILE[key][1] == 0:
            continue
        for role, label in (("ketua_rw", "Ketua RW"), ("kader", "Kader Posyandu")):
            phone = f"62800000{k:05d}"
            k += 1
            h = hash_phone(phone, s.phone_hash_key)
            if db.scalar(select(Recipient).where(Recipient.phone_hash == h)) is None:
                db.add(Recipient(rw_id=rw_id, name=f"{label} {key} (demo)", role=role,
                                 phone_enc=encrypt_phone(phone, s.phone_enc_key), phone_hash=h,
                                 opt_in_at=installed, opt_in_evidence="Data demo"))
    _seed_fake_lst(db, rw_ids)
    db.commit()
    return rw_ids


def _seed_fake_lst(db: Session, rw_ids: dict[str, int]) -> None:
    """One fake Landsat-like scene (8 days old) so the LST layer can be demonstrated.

    Surface temperature runs much hotter than air temperature at midday (roofs, asphalt).
    """
    if db.scalar(select(SatelliteScene).where(SatelliteScene.source == "simulasi")):
        return
    rng = random.Random(7)
    scene = SatelliteScene(source="simulasi", scene_id="SIMULASI/LST-DEMO-1",
                           acquired_on=(now_utc() - timedelta(days=8)).date(),
                           cloud_pct=12.0, valid_pixel_pct=88.0, accepted=True)
    db.add(scene)
    db.flush()
    for key, rw_id in rw_ids.items():
        offset = RW_PROFILE[key][0]
        mean = round(36.0 + 2.6 * offset + rng.uniform(-1.0, 1.0), 1)
        db.add(SatelliteData(scene_id=scene.id, rw_id=rw_id, lst_mean_c=mean,
                             lst_p90_c=round(mean + rng.uniform(2.0, 4.0), 1),
                             valid_pixel_pct=round(rng.uniform(75, 98), 0)))

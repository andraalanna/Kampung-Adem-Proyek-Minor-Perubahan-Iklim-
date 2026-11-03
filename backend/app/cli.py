"""Admin CLI.

    python -m app.cli gen-key                       # print a random 32-byte base64 key
    python -m app.cli create-admin EMAIL NAME       # prompts for a password
    python -m app.cli import-rw FILE.geojson        # RW polygons, see docs/data-import.md
    python -m app.cli simulate DEV_EUI --temp 34.5 --rh 61 [--api URL --key KEY]
"""

import argparse
import base64
import getpass
import json
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select


def gen_key(_: argparse.Namespace) -> None:
    print(base64.b64encode(os.urandom(32)).decode())


def create_admin(a: argparse.Namespace) -> None:
    from app.api.auth_deps import hash_password
    from app.db import SessionLocal
    from app.models import Role, User

    pw = getpass.getpass("Password (min 10 karakter): ")
    if len(pw) < 10:
        sys.exit("password terlalu pendek")
    with SessionLocal() as db:
        role_id = db.scalar(select(Role.id).where(Role.name == "admin"))
        db.add(User(name=a.name, email=a.email.lower(), password_hash=hash_password(pw),
                    role_id=role_id))
        db.commit()
    print("admin dibuat")


def import_rw(a: argparse.Namespace) -> None:
    """GeoJSON FeatureCollection, properties: kecamatan, kecamatan_code, kelurahan,
    kelurahan_code, rw (number), population?, vulnerable_count?, boundary_source?"""
    from app.db import SessionLocal
    from app.models import District, Region, Rw, Village

    fc = json.load(open(a.file, encoding="utf-8"))
    with SessionLocal() as db:
        region = db.scalar(select(Region).where(Region.bps_code == "3578"))
        if region is None:
            region = Region(bps_code="3578", name="Kota Surabaya")
            db.add(region)
            db.flush()
        n = 0
        for f in fc["features"]:
            p = f["properties"]
            d = db.scalar(select(District).where(District.bps_code == p["kecamatan_code"]))
            if d is None:
                d = District(region_id=region.id, bps_code=p["kecamatan_code"],
                             name=p["kecamatan"])
                db.add(d)
                db.flush()
            v = db.scalar(select(Village).where(Village.bps_code == p["kelurahan_code"]))
            if v is None:
                v = Village(district_id=d.id, bps_code=p["kelurahan_code"], name=p["kelurahan"])
                db.add(v)
                db.flush()
            geom = func.ST_Multi(func.ST_SetSRID(func.ST_GeomFromGeoJSON(
                json.dumps(f["geometry"])), 4326))
            rw_no = str(p["rw"]).zfill(2)
            rw = db.scalar(select(Rw).where(Rw.village_id == v.id, Rw.rw_number == rw_no))
            if rw is None:
                rw = Rw(village_id=v.id, rw_number=rw_no)
                db.add(rw)
            rw.geom = geom
            rw.population = p.get("population")
            rw.vulnerable_count = p.get("vulnerable_count")
            rw.boundary_source = p.get("boundary_source", "perkiraan")
            n += 1
        # Kelurahan/kecamatan outlines from the union of their RWs when not provided.
        db.flush()
        for v in db.scalars(select(Village).where(Village.geom.is_(None))):
            v.geom = db.scalar(select(func.ST_Multi(func.ST_Union(Rw.geom)))
                               .where(Rw.village_id == v.id))
        db.commit()
    print(f"{n} RW diimpor")


def simulate(a: argparse.Namespace) -> None:
    """Send one fake uplink through the real ingest path (for demos and testing only)."""
    import httpx

    from app.core.payload import encode_v1

    data = encode_v1(a.seq, a.temp, a.rh, a.temp, a.rh, a.battery)
    body = {"dev_eui": a.dev_eui, "received_at": datetime.now(UTC).isoformat(),
            "payload_hex": data.hex(), "gateways": [{"gateway_id": "SIM", "rssi": -90}]}
    r = httpx.post(f"{a.api}/api/v1/sensors/readings", json=body, headers={"X-API-Key": a.key})
    print(r.status_code, r.text)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(required=True)
    sub.add_parser("gen-key").set_defaults(fn=gen_key)
    p = sub.add_parser("create-admin")
    p.add_argument("email")
    p.add_argument("name")
    p.set_defaults(fn=create_admin)
    p = sub.add_parser("import-rw")
    p.add_argument("file")
    p.set_defaults(fn=import_rw)
    p = sub.add_parser("simulate")
    p.add_argument("dev_eui")
    p.add_argument("--temp", type=float, required=True)
    p.add_argument("--rh", type=float, required=True)
    p.add_argument("--battery", type=float, default=4.0)
    p.add_argument("--seq", type=int, default=1)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--key", default=os.environ.get("INGEST_API_KEY", ""))
    p.set_defaults(fn=simulate)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

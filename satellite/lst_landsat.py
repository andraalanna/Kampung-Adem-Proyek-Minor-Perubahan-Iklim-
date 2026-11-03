"""Landsat 8/9 Collection 2 Level-2 land surface temperature (LST) per RW via Google Earth Engine.

Design doc 10.4. LST = land surface temperature (roofs, roads, ground). It is NOT air temperature,
is never labelled "suhu udara", and is never used to trigger alerts. Always show the scene date.

Used by backend/app/worker/satellite_job.py (daily) and runnable by hand:

    pip install earthengine-api
    python lst_landsat.py --key key.json --account sa@project.iam.gserviceaccount.com \
        --rw-asset projects/<project>/assets/rw_surabaya --since 2026-10-01

The RW asset is a FeatureCollection whose features carry an integer property `rw_id` matching
rw.id in the database.
"""

import argparse
from datetime import date

# Surabaya bounding box (lon_min, lat_min, lon_max, lat_max), approximate.
SURABAYA_BBOX = (112.59, -7.36, 112.85, -7.18)

COLLECTIONS = {
    "landsat8": "LANDSAT/LC08/C02/T1_L2",
    "landsat9": "LANDSAT/LC09/C02/T1_L2",
}

# USGS Collection 2 surface temperature scaling: ST(K) = DN * 0.00341802 + 149.0
ST_SCALE = 0.00341802
ST_OFFSET = 149.0
KELVIN = 273.15

# QA_PIXEL bits: 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow
QA_MASK_BITS = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)

MIN_VALID_PIXEL_PCT = 60.0  # reject scenes with < 60 % valid pixels over the study area
SCALE_M = 30


def st_dn_to_celsius(dn: float) -> float:
    """Pure helper mirroring the Earth Engine expression, for tests and sanity checks."""
    return dn * ST_SCALE + ST_OFFSET - KELVIN


def init_ee(service_account: str, key_file: str):
    import ee

    ee.Initialize(ee.ServiceAccountCredentials(service_account, key_file))
    return ee


def _ee():
    import ee

    return ee


def _aoi():
    ee = _ee()
    return ee.Geometry.Rectangle(list(SURABAYA_BBOX))


def _lst_celsius(img):
    """Masked LST image in degrees C, band name 'lst'."""
    ee = _ee()
    qa = img.select("QA_PIXEL")
    clear = qa.bitwiseAnd(QA_MASK_BITS).eq(0)
    st = img.select("ST_B10").multiply(ST_SCALE).add(ST_OFFSET).subtract(KELVIN)
    # ST_B10 = 0 means no data (e.g. missing ASTER GED emissivity)
    return st.updateMask(clear).updateMask(img.select("ST_B10").gt(0)).rename("lst").set(
        "system:time_start", img.get("system:time_start")
    ).set("system:index", ee.String(img.get("system:index")))


def list_scenes(since: date, until: date) -> list[dict]:
    ee = _ee()
    out = []
    for source, coll_id in COLLECTIONS.items():
        coll = (ee.ImageCollection(coll_id).filterBounds(_aoi())
                .filterDate(since.isoformat(), until.isoformat()))
        info = coll.aggregate_array("system:id").getInfo()
        dates = coll.aggregate_array("DATE_ACQUIRED").getInfo()
        clouds = coll.aggregate_array("CLOUD_COVER").getInfo()
        for sid, d, c in zip(info, dates, clouds, strict=True):
            out.append({"source": source, "scene_id": sid,
                        "acquired_on": date.fromisoformat(d), "cloud_pct": c})
    return sorted(out, key=lambda s: s["acquired_on"])


def zonal_stats(scene_id: str, rw_asset: str) -> dict:
    """Mean, p90 and valid-pixel % per RW for one scene, plus study-area acceptance."""
    ee = _ee()
    img = ee.Image(scene_id)
    lst = _lst_celsius(img)
    aoi = _aoi()

    valid = lst.mask().reduceRegion(ee.Reducer.mean(), aoi, SCALE_M, maxPixels=1e9).getInfo()
    valid_pct = 100.0 * float(valid.get("lst") or 0.0)
    accepted = valid_pct >= MIN_VALID_PIXEL_PCT

    rows = []
    if accepted:
        reducer = ee.Reducer.mean().combine(ee.Reducer.percentile([90]), sharedInputs=True)
        # 'valid' is 1 for clear pixels, 0 for masked ones (mask() itself is unmasked), so its
        # mean is the valid fraction. Multi-band output properties are named <band>_<reducer>.
        stacked = lst.addBands(lst.mask().rename("valid"))
        stats = stacked.reduceRegions(
            collection=ee.FeatureCollection(rw_asset), reducer=reducer, scale=SCALE_M,
        ).getInfo()
        for f in stats["features"]:
            p = f["properties"]
            rows.append({
                "rw_id": int(p["rw_id"]),
                "lst_mean_c": p.get("lst_mean"),
                "lst_p90_c": p.get("lst_p90"),
                "valid_pixel_pct": None if p.get("valid_mean") is None
                else 100.0 * p["valid_mean"],
            })
    return {"valid_pixel_pct": valid_pct, "accepted": accepted, "rows": rows}


def dry_season_baseline(years: list[int], rw_asset: str) -> list[dict]:
    """Median LST of dry-season (Jun-Oct) clear pixels over several years, per RW (doc 10.4.7)."""
    ee = _ee()
    imgs = None
    for y in years:
        for coll_id in COLLECTIONS.values():
            c = (ee.ImageCollection(coll_id).filterBounds(_aoi())
                 .filterDate(f"{y}-06-01", f"{y}-11-01").map(_lst_celsius))
            imgs = c if imgs is None else imgs.merge(c)
    median = imgs.median().rename("lst")
    stats = median.reduceRegions(
        collection=ee.FeatureCollection(rw_asset),
        reducer=ee.Reducer.mean().combine(ee.Reducer.percentile([90]), sharedInputs=True),
        scale=SCALE_M,
    ).getInfo()
    return [{"rw_id": int(f["properties"]["rw_id"]), "lst_mean_c": f["properties"].get("mean"),
             "lst_p90_c": f["properties"].get("p90")} for f in stats["features"]]


def export_overlay(scene_id: str, folder: str = "kampung_adem_lst"):
    """Export a clipped LST GeoTIFF to Google Drive for the map overlay (rendered to PNG later)."""
    ee = _ee()
    lst = _lst_celsius(ee.Image(scene_id)).clip(_aoi())
    task = ee.batch.Export.image.toDrive(
        image=lst, description=scene_id.split("/")[-1], folder=folder, region=_aoi(),
        scale=SCALE_M, crs="EPSG:4326", fileFormat="GeoTIFF",
        formatOptions={"cloudOptimized": True},
    )
    task.start()
    return task


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--key", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--rw-asset", required=True)
    ap.add_argument("--since", type=date.fromisoformat, required=True)
    ap.add_argument("--until", type=date.fromisoformat, default=date.today())
    a = ap.parse_args()
    init_ee(a.account, a.key)
    for s in list_scenes(a.since, a.until):
        z = zonal_stats(s["scene_id"], a.rw_asset)
        print(f"{s['acquired_on']} {s['scene_id']} cloud={s['cloud_pct']} "
              f"valid={z['valid_pixel_pct']:.0f}% accepted={z['accepted']} rw={len(z['rows'])}")


if __name__ == "__main__":
    main()

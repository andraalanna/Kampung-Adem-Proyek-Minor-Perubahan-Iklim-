"""Daily: fetch new Landsat 8/9 LST scenes from Earth Engine and store zonal stats per RW.

LST is land surface temperature, not air temperature. It is never used to trigger alerts.
The Earth Engine logic lives in satellite/lst_landsat.py so it can also run from a notebook.
"""

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SatelliteData, SatelliteScene

log = logging.getLogger(__name__)

# repo/satellite locally; SATELLITE_DIR in Docker (mounted volume)
_SAT_DIR = Path(os.environ.get("SATELLITE_DIR",
                               Path(__file__).resolve().parents[3] / "satellite"))


def run(db: Session, lookback_days: int = 30) -> int:
    s = get_settings()
    if not (s.gee_service_account and s.gee_key_file and s.gee_rw_asset):
        log.info("GEE not configured; skipping satellite job")
        return 0
    if str(_SAT_DIR) not in sys.path:
        sys.path.append(str(_SAT_DIR))
    import lst_landsat  # noqa: PLC0415  (optional dependency: earthengine-api)

    lst_landsat.init_ee(s.gee_service_account, s.gee_key_file)
    known = set(db.scalars(select(SatelliteScene.scene_id)).all())
    since = date.today() - timedelta(days=lookback_days)
    added = 0
    for scene in lst_landsat.list_scenes(since, date.today()):
        if scene["scene_id"] in known:
            continue
        result = lst_landsat.zonal_stats(scene["scene_id"], s.gee_rw_asset)
        row = SatelliteScene(
            source=scene["source"], scene_id=scene["scene_id"], acquired_on=scene["acquired_on"],
            cloud_pct=scene.get("cloud_pct"), valid_pixel_pct=result["valid_pixel_pct"],
            accepted=result["accepted"],
        )
        db.add(row)
        db.flush()
        for z in result["rows"]:
            db.add(SatelliteData(scene_id=row.id, rw_id=z["rw_id"], lst_mean_c=z["lst_mean_c"],
                                 lst_p90_c=z["lst_p90_c"], valid_pixel_pct=z["valid_pixel_pct"]))
        added += 1
        log.info("scene %s acquired %s accepted=%s", row.scene_id, row.acquired_on, row.accepted)
    db.commit()
    return added

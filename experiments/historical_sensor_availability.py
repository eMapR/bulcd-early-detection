"""Historical (pre-Landsat-8) data availability and cross-sensor NBR offsets.

Context: the apps' expectation years go back to 2010 and the monitoring year
to 2015, with Landsat 5 and 7 as sensor choices (docs/findings.md,
2026-11-02). This measures what the engine actually gets for those years:

1. Raw scene counts per sensor and year, Jun 1 - Sep 30 (the default season),
   2008-2026, for L5, L7, L8 over each area.
2. Clear observations per pixel per season (after bulcd's cloud masking and
   day-step binning, i.e. the evidence BULC-D uses): median over the area.
3. NBR offset between sensors in the years both flew: per pixel, the median
   season NBR from sensor A minus sensor B (same years, same pixels, water
   masked); median and 10th/90th percentile over the area. L7 - L8 in
   2013-2016 (ETM+ vs OLI), L5 - L7 in 2010-2011 (TM vs ETM+). bulcd applies
   no cross-sensor harmonization, so this offset reaches the z-scores as is.

Uses only bulcd's public assemble_evidence_collection(); nothing in bulcd
changes. Output: experiments/output/historical_sensors/availability.json

    python experiments/historical_sensor_availability.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.config.schema import EvidencePeriodConfig, SensorEvidenceConfig  # noqa: E402
from bulcd.inputs import assemble_evidence_collection  # noqa: E402

from bulcd_early_detection import drawing  # noqa: E402
from bulcd_early_detection.config import CLOUD_COVER_THRESHOLD, MonitoringControls, build_config  # noqa: E402

OUT = Path(__file__).parent / "output" / "historical_sensors" / "availability.json"
AOI_DIR = Path(__file__).resolve().parents[1] / "notebooks" / "aois"
TESTSITE = "projects/bulcd-python-rebuild/assets/testsite"
AREAS = [("testsite", None), ("interior_forest_quiet", "geojson"), ("stockton_interior", "geojson")]
COLLECTIONS = {"L5": "LANDSAT/LT05/C02/T1_L2", "L7": "LANDSAT/LE07/C02/T1_L2", "L8": "LANDSAT/LC08/C02/T1_L2"}
YEARS = range(2008, 2027)
PAIRS = [("L7", "L8", [2013, 2014, 2015, 2016]), ("L5", "L7", [2010, 2011])]
CONTROLS = MonitoringControls()  # default season Jun 1 - Sep 30


def area_config(name, kind):
    if kind is None:
        return build_config(CONTROLS, aoi_asset=TESTSITE), ee.FeatureCollection(TESTSITE).geometry()
    area = drawing.study_area(name, AOI_DIR)
    return build_config(CONTROLS, **area.aoi), area.geometry


def period(sensor, first_year, last_year):
    """One sensor, inclusive years, the default season and cloud prefilter."""
    return EvidencePeriodConfig(sensors={sensor: SensorEvidenceConfig(
        enabled=True, first_year=first_year, last_year=last_year + 1, first_doy=CONTROLS.first_doy,
        last_doy=CONTROLS.last_doy, cloud_cover_threshold=CLOUD_COVER_THRESHOLD)})


def not_water():
    return ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).lte(50)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = json.loads(OUT.read_text()) if OUT.exists() else {}
    for name, kind in AREAS:
        config, geom = area_config(name, kind)
        rec = out.setdefault(name, {})
        if "scenes" not in rec:
            rec["scenes"] = ee.Dictionary({s: ee.Dictionary({str(y): ee.ImageCollection(c).filterBounds(geom)
                                                             .filterDate(f"{y}-06-01", f"{y}-10-01").size()
                                                             for y in YEARS})
                                           for s, c in COLLECTIONS.items()}).getInfo()
            print(name, "scenes", json.dumps(rec["scenes"]), flush=True)
            OUT.write_text(json.dumps(out, indent=1))
        clear = rec.setdefault("clear_obs", {})
        for s in COLLECTIONS:
            for y in YEARS:
                key = f"{s} {y}"
                if key in clear or rec["scenes"][s][str(y)] == 0:
                    continue
                col = assemble_evidence_collection(config, period(s, y, y))
                n = col.select("nbr").count().updateMask(not_water()).reduceRegion(
                    ee.Reducer.median(), geom, 30, maxPixels=1e10, bestEffort=True, tileScale=4)
                try:
                    clear[key] = n.getInfo().get("nbr")
                except Exception as e:  # recorded, not fatal
                    clear[key] = {"error": str(e)[:300]}
                print(name, "clear_obs", key, clear[key], flush=True)
                OUT.write_text(json.dumps(out, indent=1))
        offsets = rec.setdefault("nbr_offset", {})
        for a, b, years in PAIRS:
            for y in years:
                key = f"{a}-{b} {y}"
                if key in offsets:
                    continue
                ma = assemble_evidence_collection(config, period(a, y, y)).select("nbr").median()
                mb = assemble_evidence_collection(config, period(b, y, y)).select("nbr").median()
                diff = ma.subtract(mb).updateMask(not_water()).rename("d")
                stats = ee.Image.cat(diff, mb.rename("ref")).reduceRegion(
                    ee.Reducer.percentile([10, 50, 90]).combine(ee.Reducer.count(), sharedInputs=True),
                    geom, 30, maxPixels=1e10, bestEffort=True, tileScale=4)
                try:
                    offsets[key] = stats.getInfo()
                except Exception as e:  # recorded, not fatal
                    offsets[key] = {"error": str(e)[:300]}
                print(name, key, json.dumps(offsets[key]), flush=True)
                OUT.write_text(json.dumps(out, indent=1))
        OUT.write_text(json.dumps(out, indent=1))
    print("DONE", OUT)


if __name__ == "__main__":
    sys.exit(main())

"""Do Landsat 5/7 expectations create false change against Landsat 8 monitoring?

Context: the apps now allow expectation years from 2010 and a monitoring year
from 2015, with Landsat 5 and 7 as sensors (docs/findings.md, 2026-11-02).
Before 2013 only Landsat 5 (to 2011) and Landsat 7 exist, so a 2010-2014
expectation is necessarily TM/ETM+ (plus OLI from 2013), and bulcd applies no
cross-sensor harmonization. historical_sensor_availability.py measured a
small NBR offset (median |L7 - L8| <= 0.013 at three sites); this asks whether
it matters to the detections.

Design (sensor_consistency.py's, same helpers): default controls, monitoring
2015, Jun 1 - Sep 30; ONLY the expectation years/sensors and the monitoring
sensors change:

    L8 13-14 -> L8          what the apps allowed before (2-year expectation)
    L7 -> L7                same sensor both periods
    L7 -> L8                cross-sensor only (ETM+ -> OLI)
    L7 -> L7+L8             expectation sensor kept in monitoring
    L7+L8 -> L7+L8          same mix both periods
    L5+L7 -> L8             all-TM/ETM+ expectation, OLI monitoring
    L5+L7+L8 -> L7+L8       every sensor flying in each period
    (expectation 2010-2014 unless noted)

Areas: two stable interior forests (Apostle Islands; little real change
expected, so mapped change approximates false change) and the testsite
(Oregon, managed forest with harvests). For the testsite, `ref_dnbr_frac` is
the share of decrease pixels where the Landsat 8 season-median NBR fell by
>= 0.1 from 2014 to 2015 (an independent, single-sensor check that a decrease
is real).

Resumable; failures (e.g. memory limits) recorded, not fatal.

    python experiments/historical_sensor_consistency.py
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import ee
import numpy as np

import sensor_consistency as sc  # noqa: E402  (initializes ee)
from bulcd.config.schema import EvidencePeriodConfig, SensorEvidenceConfig  # noqa: E402
from bulcd.inputs import assemble_evidence_collection  # noqa: E402

from bulcd_early_detection import compare, drawing  # noqa: E402
from bulcd_early_detection.config import CLOUD_COVER_THRESHOLD, MonitoringControls, build_config  # noqa: E402
from bulcd_early_detection.outputs import DECREASE, StudyArea  # noqa: E402

OUTPUT_CSV = Path(__file__).parent / "output" / "historical_sensors" / "consistency.csv"
TESTSITE = "projects/bulcd-python-rebuild/assets/testsite"
MONITORING_YEAR = 2015
AREAS = [
    ("interior_forest_quiet", "interior forest, stable"),
    ("stockton_interior", "interior forest, stable"),
    ("testsite", "managed forest, harvests"),
]
# name -> (expectation sensors, expectation years, monitoring sensors)
VARIANTS = {
    "L8 13-14 -> L8": (("L8",), (2013, 2014), ("L8",)),
    "L7 -> L7": (("L7",), (2010, 2014), ("L7",)),
    "L7 -> L8": (("L7",), (2010, 2014), ("L8",)),
    "L7 -> L7+L8": (("L7",), (2010, 2014), ("L7", "L8")),
    "L7+L8 -> L7+L8": (("L7", "L8"), (2010, 2014), ("L7", "L8")),
    "L5+L7 -> L8": (("L5", "L7"), (2010, 2014), ("L8",)),
    "L5+L7+L8 -> L7+L8": (("L5", "L7", "L8"), (2010, 2014), ("L7", "L8")),
}
FIELDS = sc.FIELDS + ["ref_dnbr_frac"]


def area_for(name):
    if name == "testsite":
        return StudyArea(name, ee.FeatureCollection(TESTSITE).geometry(), {"aoi_asset": TESTSITE})
    return drawing.study_area(name, sc.AOI_DIR)


def l8_season_nbr(config, controls, year):
    period = EvidencePeriodConfig(sensors={"L8": SensorEvidenceConfig(
        enabled=True, first_year=year, last_year=year + 1, first_doy=controls.first_doy,
        last_doy=controls.last_doy, cloud_cover_threshold=CLOUD_COVER_THRESHOLD)})
    return assemble_evidence_collection(config, period).select("nbr").median()


def ref_dnbr_frac(config, controls, area, grid, classes):
    """Share of decrease pixels with an L8 2014 -> 2015 season-median NBR drop >= 0.1."""
    drop = l8_season_nbr(config, controls, MONITORING_YEAR - 1).subtract(
        l8_season_nbr(config, controls, MONITORING_YEAR)).gte(0.1).unmask(0).rename("drop").toFloat()
    arr = ee.data.computePixels({"expression": drop, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    dec = classes == DECREASE
    return round(float(np.mean(np.asarray(arr["drop"])[dec] > 0)), 3) if dec.any() else ""


def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUTPUT_CSV.exists():
        with OUTPUT_CSV.open() as f:
            done = {(r["aoi"], r["variant"]) for r in csv.DictReader(f) if r["status"] == "ok"}
    new_file = not OUTPUT_CSV.exists()
    with OUTPUT_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for aoi_name, role in AREAS:
            area = area_for(aoi_name)
            grid = compare.pixel_grid(area.geometry)
            for vname, (exp, (y0, y1), mon) in VARIANTS.items():
                if (aoi_name, vname) in done:
                    continue
                controls = MonitoringControls(monitoring_year=MONITORING_YEAR, baseline_first_year=y0,
                                              baseline_last_year=y1)
                row = {"aoi": aoi_name, "role": role, "variant": vname,
                       "expectation": "+".join(exp) + f" {y0}-{y1}", "monitoring": "+".join(mon)}
                t0 = time.time()
                try:
                    config = sc.with_sensors(build_config(controls, **area.aoi), exp, mon)
                    run = sc.fetch(config, area, grid, controls.decision_threshold)
                    row.update(status="ok", **sc.summarize(run, controls, config))
                    if aoi_name == "testsite":
                        classes = compare.classify(run, controls.decision_threshold, config.study_area.mask_water,
                                                   config.study_area.mask_non_forest)
                        classes = np.where(run["inside"] > 0, classes, -1)
                        row["ref_dnbr_frac"] = ref_dnbr_frac(config, controls, area, grid, classes)
                except Exception as e:  # recorded, not fatal (e.g. EE memory limit)
                    row.update(status="error", error=f"{type(e).__name__}: {e}"[:300])
                row["run_s"] = round(time.time() - t0)
                w.writerow(row)
                f.flush()
                print(f"{aoi_name:<24}{vname:<20}{row['status']:<6}{row['run_s']:>5}s  "
                      f"dec={row.get('decrease_km2', '')}  inc={row.get('increase_km2', '')}  "
                      f"ref={row.get('ref_dnbr_frac', '')}  {row.get('error', '')[:120]}", flush=True)


if __name__ == "__main__":
    main()

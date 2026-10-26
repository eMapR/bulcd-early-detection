"""Checks a run's exported stack tiles (spec.STACK_BANDS: the season tile +
detection_year) and validates detection_year against the interactive app's
first-detected-season layer.

    python experiments/regional_stack_check.py RUN.yaml EARLIER_SEASON.yaml ... [--app-aoi testsite|region]

Per tile:
- the stack's season bands == the monitoring year's season tile (values and
  masks), its properties == that tile's properties plus the stack properties;
- detection_year is masked exactly where condition is;
- detection_year against the season tiles: Y set => season Y's
  first_detection_doy is set and no earlier season's is; 0 => none is set;
- the detection_year histogram.

The app: its first-detected-season layer (outputs.combine_season_timing of the
app's timing seasons, built with the Python app's widgets set to the run's
settings, as EarlyDetectionApp._compute) == detection_year, with 0 for no
season, on the testsite asset (the app's example area), or on the whole region
(--app-aoi region; one live AOI over all tiles).

Writes experiments/output/regional_pilot/stack_check_<app-aoi>.json.
"""

import argparse
import json
import sys
from pathlib import Path

import ee

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bulcd_early_detection import outputs  # noqa: E402
from bulcd_early_detection.regional import spec  # noqa: E402
from bulcd_early_detection.regional.backends import gee  # noqa: E402
from bulcd_early_detection.regional.run_config import RegionalRun  # noqa: E402
from bulcd_early_detection.regional.tiling import lonlat_ring  # noqa: E402

TESTSITE = "projects/bulcd-python-rebuild/assets/testsite"
OUT = ROOT / "experiments" / "output" / "regional_pilot"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("seasons", nargs="+")
    p.add_argument("--app-aoi", choices=("testsite", "region"), default="testsite")
    p.add_argument("--asset-root", default=gee.DEFAULT_ASSET_ROOT)
    a = p.parse_args()
    ee.Initialize(project="bulcd-python-rebuild")

    run = RegionalRun.load(a.run)
    season_runs = [RegionalRun.load(f) for f in a.seasons]
    years = gee.season_years(run, season_runs)
    by_year = {r.controls.monitoring_year: r for r in [*season_runs, run]}
    grid = run.grid
    crs, transform = grid.crs, grid.transform
    rect = lambda b: ee.Geometry.Rectangle(list(b), crs, False)
    # Whole pixels (centers inside geom), not area fractions at polygon edges.
    reduce = lambda img, reducer, geom: img.reduceRegion(reducer.unweighted(), geom, crs=crs, crsTransform=transform,
                                                         maxPixels=1e9)
    stacks = ee.ImageCollection(gee.stack_collection_id(run, a.asset_root))
    report = {"run_id": run.run_id, "years": years, "tiles": {}}

    for tile in run.tiles:
        stack = ee.Image(f"{gee.stack_collection_id(run, a.asset_root)}/{tile.id}")
        seasons = {y: ee.Image(f"{gee.collection_id(by_year[y], a.asset_root)}/{tile.id}") for y in years}
        season = seasons[years[-1]]
        geom = rect(gee.tile_region(run, tile))
        dy = stack.select("detection_year")
        set_in = {y: seasons[y].select("first_detection_doy").unmask(0).gt(0) for y in years}
        wrong = ee.Image(0)
        for i, y in enumerate(years):
            earlier = ee.Image(0)
            for e in years[:i]:
                earlier = earlier.Or(set_in[e])
            wrong = wrong.Or(dy.eq(y).And(set_in[y].Not().Or(earlier)))
        none_set = ee.Image(0)
        for y in years:
            none_set = none_set.Or(set_in[y])
        wrong = wrong.Or(dy.eq(0).And(none_set)).Or(dy.neq(0).And(none_set.Not()))
        band_diff = ee.Image.cat([stack.select(n).unmask(-1).neq(season.select(n).unmask(-1)).rename(n)
                                  for n in spec.BAND_NAMES])
        checks = ee.Dictionary({
            "season_bands_differ": reduce(band_diff, ee.Reducer.sum(), geom),
            "detection_year_mask_differs": reduce(dy.mask().neq(season.select("condition").mask()).rename("n"),
                                                  ee.Reducer.sum(), geom).get("n"),
            "detection_year_inconsistent_with_seasons": reduce(wrong.rename("n"), ee.Reducer.sum(), geom).get("n"),
            "detection_year": reduce(dy, ee.Reducer.frequencyHistogram(), geom).get("detection_year"),
            "band_names": stack.bandNames(),
            "stack_properties": stack.toDictionary(),
            "season_properties": season.toDictionary(),
        }).getInfo()
        sp, tp = checks.pop("stack_properties"), checks.pop("season_properties")
        checks["season_properties_kept"] = all(sp.get(k) == v for k, v in tp.items())
        checks["properties_are_the_spec"] = set(sp) == set(spec.STACK_PROPERTIES)
        checks["band_names_are_the_spec"] = checks.pop("band_names") == list(spec.STACK_BAND_NAMES)
        checks["stack_properties"] = {k: sp[k] for k in spec.STACK_PROPERTIES[len(spec.PROPERTIES):]}
        report["tiles"][tile.id] = checks

    # The app's first-detected-season layer, with the run's settings.
    from bulcd_early_detection.app import EarlyDetectionApp
    app = EarlyDetectionApp()
    c, adv = run.controls, run.advanced
    app.monitoring_year.value = c.monitoring_year
    app.expectation.value = (c.baseline_first_year, c.baseline_last_year)
    for code, box in app.expectation_sensors.items():
        box.value = code in c.expectation_sensors
    for code, box in app.sensors.items():
        box.value = code in adv.monitoring_sensors
    app.timing_confirmed.value = adv.timing_rule == "confirmed"
    if a.app_aoi == "testsite":
        aoi, geom = {"aoi_asset": TESTSITE}, ee.FeatureCollection(TESTSITE).geometry()
    else:
        aoi, geom = {"aoi_coordinates": lonlat_ring(grid, run.region.bounds)}, rect(run.region.bounds)
    report["app_aoi"] = a.app_aoi
    report["app_config_equals_run"] = app.build(app.controls(), **aoi) == run.bulcd_config(**aoi)
    report["app_timing_years"] = app._timing_years()
    report["app_years_are_the_stacks"] = report["app_timing_years"] == years
    t = c.thresholds
    timing_seasons = {y: outputs.detection_timing_image(app.build(app.controls(y), **aoi), t["decrease"],
                                                        t["increase"]) for y in report["app_timing_years"]}
    timing = outputs.combine_season_timing(timing_seasons, confirmed=app.timing_confirmed.value).clip(geom)
    land = timing.select("outcome").mask().gt(0)      # clip(): fractional masks at polygon edges
    app_year = timing.select("first_decrease_year").unmask(0).updateMask(land)
    dy = stacks.mosaic().select("detection_year")
    key = app_year.multiply(10000).add(dy.unmask(9999)).rename("key")   # app year x stack year (9999 = masked)
    hist = reduce(key, ee.Reducer.frequencyHistogram(), geom).getInfo()["key"]
    pairs = {}
    for k, n in hist.items():
        if k == "null":     # unweighted reducers count masked pixels (the app's water) as null
            pairs["app masked"] = n
            continue
        k = int(float(k))
        pairs[f"app {k // 10000} / stack {k % 10000}"] = n
    report["app_vs_stack"] = pairs
    report["app_vs_stack_differ"] = sum(n for k, n in pairs.items() if k.split(" / ")[0][4:] != k.split()[-1])
    report["app_land_stack_masked"] = reduce(land.And(dy.mask().Not()).rename("n"), ee.Reducer.sum(), geom).getInfo()["n"]
    report["stack_valid_app_masked"] = reduce(land.Not().And(dy.mask()).rename("n"), ee.Reducer.sum(), geom).getInfo()["n"]

    tiles_ok = all(not any(v["season_bands_differ"].values()) and v["detection_year_mask_differs"] == 0
                   and v["detection_year_inconsistent_with_seasons"] == 0 and v["season_properties_kept"]
                   and v["properties_are_the_spec"] and v["band_names_are_the_spec"]
                   for v in report["tiles"].values())
    app_ok = (report["app_config_equals_run"] and report["app_years_are_the_stacks"]
              and report["app_vs_stack_differ"] == 0 and report["app_land_stack_masked"] == 0
              and report["stack_valid_app_masked"] == 0)
    report["ok"] = {"tiles": tiles_ok, "app": app_ok}
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"stack_check_{a.app_aoi}.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps(report, indent=1, sort_keys=True))
    print("stack ok:", report["ok"], "->", out)
    return 0 if tiles_ok and app_ok else 1


if __name__ == "__main__":
    sys.exit(main())

"""Validates a regional run's exported tiles (docs/regional_plan.md, step 7):
tile seams / AOI independence, and agreement with the interactive app.

    python experiments/regional_seam_check.py RUN.yaml [--corner-px 20]

1. Mosaic: the run's tiles cover the region once (no gaps, no overlaps): the
   mosaic's pixel count over the region == the region's pixels minus masked ones.
2. AOI independence across the seams, for every spec band (masks included):
   the tiles (each run on its own tile AOI) vs product_image() run live on a
   different AOI and sampled on the same grid pixels:
   - "testsite": the app's example asset; it straddles the pilot's seams;
   - "corner": a small box (corner_px x corner_px) centered on the tile corner
     nearest the region's center, so its BULC-D run covers parts of 4 tiles.
   Value differences are counted where both are valid, mask differences
   separately, and both split by distance to the nearest seam.
3. The interactive app on the testsite, with the run's settings (the Python
   app's widgets set to them; its build() == the run's config is checked):
   - condition == the app's condition layer (outputs.outcome_image), and the
     probabilities == its final probabilities;
   - the app's detection timing is multi-season (the seasons after the
     expectation period, combined: earliest season that counts); a regional
     product holds the monitoring year only. Where the app's first detected
     season is the monitoring year, first_detection_doy / last_detection_doy /
     episode_count must equal the app's; elsewhere the cross-tab is reported.

Writes experiments/output/regional_pilot/seam_check.json.
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
SEAM_BINS = (1, 2, 5, 10, 1e9)   # distance to the nearest seam, pixels: <=1, <=2, <=5, <=10, more


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--corner-px", type=int, default=20)
    p.add_argument("--asset-root", default=gee.DEFAULT_ASSET_ROOT)
    a = p.parse_args()
    ee.Initialize(project="bulcd-python-rebuild")

    run = RegionalRun.load(a.run)
    grid = run.grid
    crs, transform, s = grid.crs, grid.transform, grid.scale
    tiles = ee.ImageCollection(gee.collection_id(run, a.asset_root))
    mosaic = tiles.mosaic()
    rect = lambda b: ee.Geometry.Rectangle(list(b), crs, False)
    # Unweighted: whole pixels (centers inside geom), not area fractions at polygon edges.
    reduce = lambda img, reducer, geom: img.reduceRegion(reducer.unweighted(), geom, crs=crs, crsTransform=transform,
                                                         maxPixels=1e9)
    report = {"run_id": run.run_id, "tiles": tiles.aggregate_array("tile_id").getInfo()}

    # Distance (pixels) from each pixel center to the nearest internal seam of the run's tiles.
    x0, y0, x1, y1 = run.region.bounds
    xs = sorted({t.bounds[0] for t in run.tiles} - {x0})
    ys = sorted({t.bounds[1] for t in run.tiles} - {y0})
    coords = ee.Image.pixelCoordinates(ee.Projection(crs))
    dist = ee.Image(1e9)
    for x in xs:
        dist = dist.min(coords.select("x").subtract(x).abs())
    for y in ys:
        dist = dist.min(coords.select("y").subtract(y).abs())
    seam_px = dist.divide(s).add(0.5).rename("seam_px")   # 1 = the pixel touches the seam

    # 1. Mosaic coverage.
    region = rect(run.region.bounds)
    report["mosaic"] = ee.Dictionary({
        "region_pixels": reduce(ee.Image(1).rename("n"), ee.Reducer.count(), region).get("n"),
        "valid_pixels": reduce(mosaic.select("condition"), ee.Reducer.count(), region).get("condition"),
        "tile_valid_sum": tiles.map(lambda i: i.set("n", i.select("condition").reduceRegion(
            ee.Reducer.count(), i.geometry(), crs=crs, crsTransform=transform, maxPixels=1e9).get("condition")))
            .aggregate_sum("n"),
        "tile_footprint_overlap": reduce(tiles.map(lambda i: i.select("condition").mask().gt(0).unmask(0)
                                                    .rename("n")).sum().gt(1), ee.Reducer.sum(), region).get("n"),
    }).getInfo()

    def compare(live, geom):
        """Per band: differing values (both valid), mask differences, valid pixels; split by seam distance."""
        bins = ee.Image(0)
        for i, b in enumerate(SEAM_BINS[:-1]):
            bins = bins.where(seam_px.gt(b), i + 1)
        out = {}
        for band in spec.BAND_NAMES:
            L, M = live.select(band), mosaic.select(band)
            both = L.mask().And(M.mask())
            img = ee.Image.cat(L.neq(M).And(both).unmask(0).rename("differ"),
                               L.mask().neq(M.mask()).rename("mask_differs"),
                               both.rename("both_valid"))
            out[band] = img.addBands(bins.rename("bin")).reduceRegion(
                ee.Reducer.sum().unweighted().repeat(3).group(3, "seam_bin"), geom, crs=crs, crsTransform=transform,
                maxPixels=1e9)
        return out

    def summarize(raw):
        bands, total = {}, {"differ": 0, "mask_differs": 0}
        for band, d in raw.items():
            rows = {}
            for g in d["groups"]:
                differ, mask_differs, both = g["sum"]
                upper = SEAM_BINS[g["seam_bin"]]
                rows["<=%d px" % upper if upper < 1e9 else "farther"] = {
                    "differ": differ, "mask_differs": mask_differs, "both_valid": both}
                total["differ"] += differ
                total["mask_differs"] += mask_differs
            bands[band] = rows
        return bands, total

    # 2. AOI independence.
    testsite = ee.FeatureCollection(TESTSITE).geometry()
    cx, cy = min(xs, key=lambda x: abs(x - (x0 + x1) / 2)), min(ys, key=lambda y: abs(y - (y0 + y1) / 2))
    h = a.corner_px // 2 * s
    corner = (cx - h, cy - h, cx + h, cy + h)
    aois = {
        "testsite": (run.bulcd_config(aoi_asset=TESTSITE), testsite),
        "corner": (run.bulcd_config(aoi_coordinates=lonlat_ring(grid, corner)), rect(corner)),
    }
    raw = {name: compare(gee.product_image(run, config), geom) for name, (config, geom) in aois.items()}
    raw = ee.Dictionary(raw).getInfo()
    report["aoi_independence"] = {}
    for name, d in raw.items():
        bands, total = summarize(d)
        report["aoi_independence"][name] = {"total": total, "bands": bands}
    report["corner_box"] = corner

    # 3. The interactive app on the testsite, with the run's settings.
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
    config = app.build(app.controls(), aoi_asset=TESTSITE)
    report["app_config_equals_run"] = config == run.bulcd_config(aoi_asset=TESTSITE)
    years = app._timing_years()
    report["app_timing_years"] = years
    confirmed = app.timing_confirmed.value
    t = c.thresholds
    # The app's own layers (EarlyDetectionApp._compute), clipped to the area as there.
    app_out = outputs.outcome_image(config, t["decrease"], t["increase"]).clip(testsite)
    seasons = {y: outputs.detection_timing_image(app.build(app.controls(y), aoi_asset=TESTSITE), t["decrease"],
                                                 t["increase"]) for y in years}
    timing = outputs.combine_season_timing(seasons, confirmed=confirmed).clip(testsite)
    codes = {y: outputs.detection_episode_image(app.build(app.controls(y), aoi_asset=TESTSITE), t["decrease"],
                                                t["increase"], confirmed=confirmed) for y in years}
    episodes = outputs.combine_episode_metrics(codes).clip(testsite)

    M = mosaic
    # clip() gives polygon-edge pixels fractional masks (partial coverage, drawn semi-transparent); any
    # coverage is a valid pixel here.
    land = app_out.select("outcome").mask().gt(0)
    in_year = timing.select("first_decrease_year").eq(c.monitoring_year).unmask(0)
    p = lambda name: app_out.select(name).multiply(spec.PROBABILITY_SCALE).round()
    checks = ee.Image.cat(
        app_out.select("outcome").neq(M.select("condition")).unmask(1).updateMask(land).rename("condition_differs"),
        land.neq(M.select("condition").mask()).rename("mask_differs"),
        p("decrease").neq(M.select("p_decrease")).unmask(1).updateMask(land).rename("p_decrease_differs"),
        p("unchanged").neq(M.select("p_unchanged")).unmask(1).updateMask(land).rename("p_unchanged_differs"),
        p("increase").neq(M.select("p_increase")).unmask(1).updateMask(land).rename("p_increase_differs"),
        # Where the app's first detected season is the monitoring year: same first/last/episodes.
        in_year.And(timing.select("first_decrease_doy").neq(M.select("first_detection_doy")).unmask(1))
               .rename("first_differs_in_year"),
        in_year.And(episodes.select("last_decrease_doy").neq(M.select("last_detection_doy")).unmask(1))
               .rename("last_differs_in_year"),
        in_year.And(episodes.select("decrease_episodes").neq(M.select("episode_count")).unmask(1))
               .rename("episodes_differ_in_year"),
        in_year.rename("app_first_season_is_monitoring_year"),
        land.rename("land"),
    )
    report["app"] = reduce(checks, ee.Reducer.sum(), testsite).getInfo()
    # Cross-tab: app first detected season (0 = none) x regional detection in the monitoring year.
    app_year = timing.select("first_decrease_year").unmask(0).updateMask(land)
    key = app_year.multiply(10).add(M.select("first_detection_doy").gt(0)).rename("key")
    report["app_season_vs_regional"] = {
        f"app {int(float(k)) // 10 or 'none'} / regional {'detected' if int(float(k)) % 10 else 'none'}": n
        for k, n in reduce(key, ee.Reducer.frequencyHistogram(), testsite).getInfo()["key"].items()}

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "seam_check.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps(report, indent=1, sort_keys=True))
    ok = (all(v["total"] == {"differ": 0, "mask_differs": 0} for v in report["aoi_independence"].values())
          and report["app_config_equals_run"]
          and all(v == 0 for k, v in report["app"].items() if k not in ("app_first_season_is_monitoring_year", "land")))
    print("seams and app agree:", ok, "->", out)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

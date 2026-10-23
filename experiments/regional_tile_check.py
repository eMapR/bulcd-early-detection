"""Checks an exported regional tile (docs/regional_plan.md, step 4) against the
same image computed live, on the tile's own grid pixels, and summarizes it.

    python experiments/regional_tile_check.py RUN.yaml TILE_ID [--box-px 60]

- Asset vs live: the backend's product_image() for the tile's config, computed
  interactively over a box of grid pixels (box_px x box_px around the testsite
  reference pixel 1, or the tile center), and the exported asset sampled on
  the same pixels: every band must be identical (masks included).
- Summary over the whole tile: grid, masked share, condition classes, timing
  and observation-count ranges, properties.
- Reference pixel 1 (decrease, -123.56922 44.84283): the tile's values there.

Writes experiments/output/regional_pilot/<tile>_check.json. Tile seams and
AOI independence are step 7's validation, not this check.
"""

import argparse
import json
import sys
from pathlib import Path

import ee

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bulcd_early_detection.regional import spec  # noqa: E402
from bulcd_early_detection.regional.backends import gee  # noqa: E402
from bulcd_early_detection.regional.run_config import RegionalRun  # noqa: E402
from bulcd_early_detection.regional.tiling import to_grid_xy  # noqa: E402

PIXEL_1 = (-123.56922, 44.84283)
OUT = ROOT / "experiments" / "output" / "regional_pilot"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("tile")
    p.add_argument("--box-px", type=int, default=60)
    p.add_argument("--asset-root", default=gee.DEFAULT_ASSET_ROOT)
    a = p.parse_args()
    ee.Initialize(project="bulcd-python-rebuild")

    run = RegionalRun.load(a.run)
    tile = next(t for t in run.tiles if t.id == a.tile)
    asset = ee.Image(f"{gee.collection_id(run, a.asset_root)}/{tile.id}")
    grid = run.grid
    crs, transform = grid.crs, grid.transform
    report = {"tile": tile.id, "asset": asset.id().getInfo()}

    # Box of grid pixels around pixel 1 if it is in the tile, else the tile center.
    px, py = to_grid_xy(grid, *PIXEL_1)
    x0, y0, x1, y1 = gee.tile_region(run, tile)
    inside = x0 <= px < x1 and y0 <= py < y1
    cx, cy = (px, py) if inside else ((x0 + x1) / 2, (y0 + y1) / 2)
    s, h = grid.scale, a.box_px // 2
    bx0 = max(x0, grid.origin[0] + ((cx - grid.origin[0]) // s - h) * s)
    by1 = min(y1, grid.origin[1] - ((grid.origin[1] - cy) // s - h) * s)
    box = (bx0, max(y0, by1 - a.box_px * s), min(x1, bx0 + a.box_px * s), by1)
    region = ee.Geometry.Rectangle(list(box), crs, False)
    report["box"] = box

    # Asset vs live, band by band: differing values, and pixels masked in one but not the other.
    live = gee.product_image(run, gee.tile_config(run, tile))
    diff = {}
    for b in spec.BAND_NAMES:
        L, A = live.select(b), asset.select(b)
        stats = ee.Image.cat(
            L.unmask(-1).neq(A.unmask(-1)).rename("differ"),
            L.mask().neq(A.mask()).rename("mask_differs"),
            A.mask().rename("valid"),
        ).reduceRegion(ee.Reducer.sum(), region, crs=crs, crsTransform=transform, maxPixels=1e9)
        diff[b] = stats
    diff = ee.Dictionary(diff).getInfo()
    report["asset_vs_live"] = diff
    report["asset_vs_live_identical"] = all(v["differ"] == 0 and v["mask_differs"] == 0 for v in diff.values())

    # Whole-tile summary from the asset.
    tile_region = ee.Geometry.Rectangle(list(gee.tile_region(run, tile)), crs, False)
    reduce = lambda img, reducer: img.reduceRegion(reducer, tile_region, crs=crs, crsTransform=transform,
                                                   maxPixels=1e9)
    report["projection"] = asset.select("condition").projection().getInfo()
    report["pixels"] = ee.Dictionary({
        "total": reduce(ee.Image(1).rename("n"), ee.Reducer.count()).get("n"),
        "valid": reduce(asset.select("condition"), ee.Reducer.count()).get("condition"),
    }).getInfo()
    report["condition"] = reduce(asset.select("condition"), ee.Reducer.frequencyHistogram()).getInfo()["condition"]
    ranges = reduce(asset.select(["first_detection_doy", "last_detection_doy", "episode_count", "n_obs_monitoring",
                                  "n_obs_expectation", "p_decrease"]), ee.Reducer.minMax())
    report["ranges"] = ranges.getInfo()
    detected = asset.select("first_detection_doy").gt(0)
    report["detections"] = ee.Dictionary({
        "with_first_detection": reduce(detected.rename("n"), ee.Reducer.sum()).get("n"),
        "first_detection_but_not_decrease": reduce(detected.And(asset.select("condition").neq(spec.DECREASE))
                                                   .rename("n"), ee.Reducer.sum()).get("n"),
        "last_before_first": reduce(asset.select("last_detection_doy").lt(asset.select("first_detection_doy"))
                                    .rename("n"), ee.Reducer.sum()).get("n"),
        "episodes_histogram": reduce(asset.select("episode_count"), ee.Reducer.frequencyHistogram())
                              .get("episode_count"),
    }).getInfo()
    if inside:
        report["pixel_1"] = asset.reduceRegion(ee.Reducer.first(), ee.Geometry.Point(PIXEL_1), crs=crs,
                                               crsTransform=transform).getInfo()
    props = asset.toDictionary().getInfo()
    report["properties"] = {k: v for k, v in props.items() if not k.endswith("_json")}
    report["provenance"] = json.loads(props["provenance_json"])

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{tile.id}_check.json"
    out.write_text(json.dumps(report, indent=1, sort_keys=True))
    print(json.dumps(report, indent=1, sort_keys=True))
    print("asset == live on the box:", report["asset_vs_live_identical"], "->", out)
    return 0 if report["asset_vs_live_identical"] else 1


if __name__ == "__main__":
    sys.exit(main())

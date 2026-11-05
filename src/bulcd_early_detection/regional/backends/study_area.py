"""The R6 regional study area and forest mask (Earth Engine), frozen as two
image assets on the run grid so every tile task reads the same pixels:

- ECOREGION_ASSET: uint8 EPA Level III code (us_l3code) of the seven
  ecoregions, clipped to Oregon + Washington dissolved; masked elsewhere.
  A pixel belongs to a region where its center is inside (Earth Engine's
  rasterization at the grid's 30 m pixels).
- FOREST_ASSET: uint8 1 = forest, 0 = not forest, from LCMS land cover
  (FOREST_DEFINITION); masked outside the ecoregions. Passed to bulcd as
  StudyAreaConfig.forest_mask_asset (bulcd's supported forest-mask input:
  nonzero = forest), so non-forest land gets the spec's condition 3
  "not analyzed", as the apps' forest mask does.

    python -m bulcd_early_detection.regional.backends.study_area export [--wait]
"""

from __future__ import annotations

import argparse
import json
import sys

import ee

from ..tiling import Grid

PROJECT = "bulcd-python-rebuild"
FOLDER = f"projects/{PROJECT}/assets/regional/r6_study_area"
ECOREGION_ASSET = f"{FOLDER}/ecoregions_orwa"
FOREST_ASSET = f"{FOLDER}/forest_lcms2023"

STATES = {"source": "TIGER/2018/States", "field": "NAME", "values": ["Oregon", "Washington"]}
# us_l3code -> (run name, EPA name). The user's "Columbia Mountains" is EPA code 15
# "Northern Rockies" (CEC Level III 6.2.3 "Columbia Mountains/Northern Rockies").
ECOREGIONS = {
    1: ("coast-range", "Coast Range"),
    11: ("blue-mountains", "Blue Mountains"),
    77: ("north-cascades", "North Cascades"),
    9: ("east-cascades", "Eastern Cascades Slopes and Foothills"),
    4: ("cascades", "Cascades"),
    15: ("columbia-mountains", "Northern Rockies (Columbia Mountains/Northern Rockies)"),
    78: ("klamath-mountains", "Klamath Mountains/California High North Coast Range"),
}
ECOREGION_SOURCE = {"source": "EPA/Ecoregions/2013/L3", "field": "us_l3code"}

# One forest definition for all seven ecoregions. Year 2023 = the last
# expectation year: the forest present before the monitoring seasons (2024-2026),
# so a pixel cleared in a monitoring season is still analyzed.
FOREST_DEFINITION = {
    "source": "projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11",
    "study_area": "CONUS",
    "year": 2023,
    "band": "Land_Cover",
    # 1 Trees, 2 Tall Shrubs & Trees Mix (AK only, absent in CONUS), 3 Shrubs & Trees Mix,
    # 4 Grass/Forb/Herb & Trees Mix, 5 Barren & Trees Mix: every LCMS class with trees.
    "forest_classes": [1, 2, 3, 4, 5],
}

# Grid-snapped EPSG:5070 bounds of the seven ecoregions in OR/WA (computed 2026-11-05).
EXPORT_BOUNDS = (-2294715.0, 2360025.0, -1545525.0, 3153855.0)


def states_geometry() -> ee.Geometry:
    s = STATES
    return ee.FeatureCollection(s["source"]).filter(ee.Filter.inList(s["field"], s["values"])).geometry()


def ecoregion_features() -> ee.FeatureCollection:
    codes = [str(c) for c in ECOREGIONS]
    fc = ee.FeatureCollection(ECOREGION_SOURCE["source"]).filter(ee.Filter.inList(ECOREGION_SOURCE["field"], codes))
    return fc.map(lambda f: f.set("code", ee.Number.parse(f.get(ECOREGION_SOURCE["field"]))))


def ecoregion_image() -> ee.Image:
    """us_l3code where the pixel center is in one of the ecoregions and in OR/WA."""
    eco = ecoregion_features().reduceToImage(["code"], ee.Reducer.first())
    in_states = ee.Image(0).paint(ee.FeatureCollection([ee.Feature(states_geometry())]), 1)
    return eco.updateMask(in_states.eq(1)).toUint8().rename("ecoregion")


def forest_image(ecoregions: ee.Image | None = None) -> ee.Image:
    d = FOREST_DEFINITION
    lc = (ee.ImageCollection(d["source"]).filter(ee.Filter.eq("study_area", d["study_area"]))
          .filter(ee.Filter.eq("year", d["year"])).first().select(d["band"]))
    forest = lc.remap(d["forest_classes"], [1] * len(d["forest_classes"]), 0)
    ecoregions = ecoregion_image() if ecoregions is None else ecoregions
    return forest.updateMask(ecoregions.mask()).toUint8().rename("forest")


def _export(image: ee.Image, asset_id: str, grid: Grid, props: dict) -> ee.batch.Task:
    x0, y0, x1, y1 = EXPORT_BOUNDS
    s = grid.scale
    task = ee.batch.Export.image.toAsset(
        image=image.set(props), description=asset_id.split("/")[-1], assetId=asset_id, crs=grid.crs,
        crsTransform=[s, 0, x0, 0, -s, y1], dimensions=f"{round((x1 - x0) / s)}x{round((y1 - y0) / s)}",
        pyramidingPolicy={".default": "mode"}, maxPixels=1e10)
    task.start()
    return task


def export(grid: Grid = Grid()) -> list:
    from ... import outputs
    outputs.ensure_folder(FOLDER)
    common = {"states_json": json.dumps(STATES), "ecoregions_json": json.dumps(
        {str(k): v[1] for k, v in ECOREGIONS.items()}), "ecoregion_source_json": json.dumps(ECOREGION_SOURCE)}
    return [
        _export(ecoregion_image(), ECOREGION_ASSET, grid, common),
        _export(forest_image(), FOREST_ASSET, grid, common | {"forest_definition_json": json.dumps(FOREST_DEFINITION)}),
    ]


def region_mask(code: int) -> ee.Image:
    """1 on the ecoregion's pixels (in OR/WA), masked elsewhere (from the frozen asset)."""
    return ee.Image(ECOREGION_ASSET).eq(code).selfMask()


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("export",))
    p.add_argument("--wait", action="store_true")
    a = p.parse_args(argv)
    ee.Initialize(project=PROJECT)
    tasks = export()
    for t in tasks:
        print("started", t.status()["description"], t.id)
    if a.wait:
        from ... import outputs
        print(json.dumps(outputs.wait_for(tasks), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

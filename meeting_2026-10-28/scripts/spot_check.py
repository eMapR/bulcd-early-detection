"""Spot check (NOT the full regional validation): recompute BULC-D live with the
pilot's own config over a 40 x 40 pixel window centered where all four tiles
meet, and compare pixel by pixel with the exported tiles.

Read-only: nothing exported, no asset modified. Writes data/spot_check.json.
"""
import json
import sys
import tempfile
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
from bulcd.config.loader import load_config  # noqa: E402

from bulcd_early_detection.outputs import outcome_image  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
R = "projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-"
X0, Y1 = -2153385.0, 2750565.0
R0 = C0 = 313  # window rows/cols 313..352; the tile seams are between 332 and 333
N = 40
WX, WY = X0 + 30 * C0, Y1 - 30 * R0
GRID = {"dimensions": {"width": N, "height": N},
        "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": WX, "shearY": 0, "scaleY": -30, "translateY": WY},
        "crsCode": "EPSG:5070"}


def pixels(image, bands):
    raw = ee.data.computePixels({"expression": image.select(bands), "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    return {b: np.asarray(raw[b]) for b in bands}


def check(year):
    tile = ee.data.listAssets({"parent": R + year})["assets"][0]["name"]
    cfg = json.loads(ee.data.getAsset(tile)["properties"]["config_json"])
    cfg["export"]["asset_folder"] = "unused"
    # Drawn AOI around the window, with margin (results per pixel don't depend on it).
    box = ee.Geometry.Rectangle([WX - 600, WY - 30 * N - 600, WX + 30 * N + 600, WY + 600], "EPSG:5070", False)
    ring = box.transform("EPSG:4326", 0.1).coordinates().getInfo()[0]
    cfg["study_area"]["aoi_coordinates"] = ring
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)
    config = load_config(f.name)
    live = outcome_image(config, 0.65, 0.75).unmask(-999)
    lv = pixels(live, ["outcome", "decrease", "unchanged", "increase", "first_detection_doy"])
    asset = ee.ImageCollection(R + year).mosaic().unmask(65535)
    av = pixels(asset, ["condition", "p_decrease", "p_unchanged", "p_increase", "first_detection_doy"])
    land = av["condition"] != 65535
    out = {"year": year, "window_px": N * N, "land_px": int(land.sum()),
           "tiles_in_window": 4,
           "condition_match": int((lv["outcome"][land] == av["condition"][land]).sum())}
    for cls in ("decrease", "unchanged", "increase"):
        diff = np.abs(lv[cls][land] - av["p_" + cls][land] / 10000.0)
        out[f"max_abs_diff_p_{cls}"] = float(diff.max())
    fd_live = np.where(lv["first_detection_doy"] < 0, 0, lv["first_detection_doy"])
    out["first_detection_doy_match"] = int((fd_live[land] == av["first_detection_doy"][land]).sum())
    bad = land & (fd_live != av["first_detection_doy"])
    out["first_detection_doy_mismatch_by_condition"] = {
        int(k): int(v) for k, v in zip(*np.unique(av["condition"][bad], return_counts=True))}
    out["asset_first_detection_doy_at_mismatches"] = sorted({int(v) for v in av["first_detection_doy"][bad]})
    out["condition_counts"] = {int(k): int(v) for k, v in zip(*np.unique(av["condition"][land], return_counts=True))}
    return out


years = sys.argv[1:] or ["2026"]
results = [check(y) for y in years]
(DATA / f"spot_check_{'_'.join(years)}.json").write_text(json.dumps(results, indent=1))
print(json.dumps(results, indent=1))

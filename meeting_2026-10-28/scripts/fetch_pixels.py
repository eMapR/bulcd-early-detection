"""Pixel histories for Slides 1 and 3 (read-only; live BULC-D runs, nothing exported).

Slide 1: one regional-pilot pixel first confirmed as decrease in 2025 and still
decrease in 2026, rerun with the pilot's own configs (config_json on the assets).
Slide 3 uses the saved Pine Mountain experiment outputs instead
(experiments/output/pine_mountain_fit_order/).

Writes meeting_2026-10-28/data/pixels.json.
"""
import json
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
import tempfile  # noqa: E402

from bulcd.config.loader import load_config  # noqa: E402

from bulcd_early_detection.pixel import pixel_history  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
R = "projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-"
X0, Y1 = -2153385.0, 2750565.0


def pick_pixel():
    """Center of the densest homogeneous patch of 'not 2024, decrease 2025, decrease 2026' (code 100)."""
    d = np.load(DATA / "pilot.npz")
    code = (d["condition_2024"].astype(int) * 100 + d["condition_2025"] * 10 + d["condition_2026"])
    hit = code == 100
    best, score = None, -1
    for r in range(7, hit.shape[0] - 7):
        for c in range(7, hit.shape[1] - 7):
            if not hit[r - 2:r + 3, c - 2:c + 3].all():
                continue
            s = hit[r - 7:r + 8, c - 7:c + 8].sum()
            if s > score:
                best, score = (r, c), s
    r, c = best
    x, y = X0 + 30 * c + 15, Y1 - 30 * r - 15
    lon, lat = ee.Geometry.Point([x, y], "EPSG:5070").transform("EPSG:4326", 0.01).coordinates().getInfo()
    asset = {f"{k}_{yr}": int(d[f"{k}_{yr}"][r, c]) for k in ("condition", "first_detection_doy", "p_decrease")
             for yr in ("2024", "2025", "2026")}
    asset["detection_year"] = int(d["detection_year"][r, c])
    return {"row": r, "col": c, "x": x, "y": y, "lon": lon, "lat": lat, "patch_score": int(score), "asset": asset}


def config_for(year, lon, lat):
    tile = ee.data.listAssets({"parent": R + str(year)})["assets"][0]["name"]
    cfg = json.loads(ee.data.getAsset(tile)["properties"]["config_json"])
    cfg["export"]["asset_folder"] = "unused"  # nothing is exported; the loader requires a value
    d = 0.01
    cfg["study_area"]["aoi_coordinates"] = [[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
                                             [lon - d, lat + d], [lon - d, lat - d]]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)  # JSON is YAML; load_config validates it like any config file
    return load_config(f.name)


def rows_json(rows):
    return [{**r, "date": r["date"].isoformat()} for r in rows]


out = {}
p = pick_pixel()
p["seasons"] = {}
for year in (2024, 2025, 2026):
    p["seasons"][str(year)] = rows_json(pixel_history(config_for(year, p["lon"], p["lat"]), p["lon"], p["lat"]))
out["slide1"] = p
print("slide1 pixel", {k: v for k, v in p.items() if k != "seasons"})

(DATA / "pixels.json").write_text(json.dumps(out, indent=1))

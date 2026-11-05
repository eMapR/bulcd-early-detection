"""Download the regional pilot products (read-only) as numpy arrays for the meeting figures.

Reads the existing assets under projects/bulcd-python-rebuild/assets/regional/;
writes meeting_2026-10-28/data/pilot.npz. Nothing in Earth Engine is modified.
"""
import io
import json
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
OUT = Path(__file__).resolve().parents[1] / "data"
R = "projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-"
X0, Y1, NPX = -2153385.0, 2750565.0, 666  # pilot box (run_json region.bounds), 30 m
GRID = {"dimensions": {"width": NPX, "height": NPX},
        "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": X0,
                            "shearY": 0, "scaleY": -30, "translateY": Y1},
        "crsCode": "EPSG:5070"}


def pixels(image, bands):
    raw = ee.data.computePixels({"expression": image.select(bands), "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    return {b: np.asarray(raw[b]) for b in bands}


arrays = {}
for year in ("2024", "2025", "2026"):
    img = ee.ImageCollection(R + year).mosaic().unmask(255)
    for band, a in pixels(img, ["condition", "first_detection_doy", "p_decrease", "n_obs_monitoring"]).items():
        arrays[f"{band}_{year}"] = a
stack = ee.ImageCollection(R + "2026-stack").mosaic().unmask(65535)
arrays["detection_year"] = pixels(stack, ["detection_year"])["detection_year"]

# Background: Sentinel-2 true color, Jul 1 - Sep 15 2026, Cloud Score+ masked median (display only).
box = ee.Geometry.Rectangle([X0, Y1 - NPX * 30, X0 + NPX * 30, Y1], "EPSG:5070", False)
cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(box).filterDate("2026-07-01", "2026-09-16")
      .linkCollection(cs, ["cs_cdf"]).map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))).median())
rgb = s2.select(["B4", "B3", "B2"]).reproject("EPSG:5070", None, 30).unmask(0)
for band, a in pixels(rgb, ["B4", "B3", "B2"]).items():
    arrays["rgb_" + band] = a.astype("float32")

# True north in the EPSG:5070 grid at the box center (Albers: grid north != true north here).
c = ee.Geometry.Point([X0 + NPX * 15, Y1 - NPX * 15], "EPSG:5070").transform("EPSG:4326", 1)
lon, lat = c.coordinates().getInfo()
north = ee.Geometry.Point([lon, lat + 0.05]).transform("EPSG:5070", 1).coordinates().getInfo()
arrays["north_vec"] = np.array([north[0] - (X0 + NPX * 15), north[1] - (Y1 - NPX * 15)])
arrays["center_lonlat"] = np.array([lon, lat])

# Tile footprints, from the asset metadata.
tiles = {}
for a in ee.data.listAssets({"parent": R + "2026"})["assets"]:
    g = json.loads(ee.data.getAsset(a["name"])["properties"]["grid_json"])
    tiles[a["id"].split("/")[-1]] = g["transform"][2], g["transform"][5]
arrays["tiles_json"] = np.array(json.dumps(tiles))

np.savez_compressed(OUT / "pilot.npz", **arrays)
print({k: (v.shape, v.dtype) for k, v in arrays.items()})
print("center", lon, lat, "north", arrays["north_vec"], tiles)

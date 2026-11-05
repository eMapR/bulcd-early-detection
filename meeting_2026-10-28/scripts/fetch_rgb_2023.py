"""Sentinel-2 natural color, summer 2023 and 2024, on the pilot grid (read-only; map backgrounds and the
"before" view for figures_v4). Same compositing as fetch_reference.py (Jul 1 - Sep 15, Cloud Score+ >= 0.6,
median). Writes data/rgb_2023_2024.npz: summer{year}_{B4,B3,B2}.

    python meeting_2026-10-28/scripts/fetch_rgb_2023.py
"""
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
DATA = Path(__file__).resolve().parents[1] / "data"
X0, Y1, N = -2153385.0, 2750565.0, 666
BOX = ee.Geometry.Rectangle([X0, Y1 - N * 30, X0 + N * 30, Y1], "EPSG:5070", False)
GRID = {"dimensions": {"width": N, "height": N}, "crsCode": "EPSG:5070",
        "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": X0, "shearY": 0, "scaleY": -30, "translateY": Y1}}
CS = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")

out = {}
for year in (2023, 2024):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(BOX).filterDate(f"{year}-07-01", f"{year}-09-16")
           .linkCollection(CS, ["cs_cdf"]).map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))))
    img = col.median().select(["B4", "B3", "B2"]).reproject("EPSG:5070", None, 30).unmask(-9).toFloat()
    raw = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    out.update({f"summer{year}_{b}": np.asarray(raw[b]) for b in raw.dtype.names})
    print("fetched", year, flush=True)
np.savez_compressed(DATA / "rgb_2023_2024.npz", **out)

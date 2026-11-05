"""Monthly Sentinel-2 NBR for Nov-Dec 2024 and Nov-Dec 2025 on the pilot grid, with clear-observation counts
(read-only). Extends data/monthly_s2.npz (Jan-Oct 2025/2026) so a change first seen in Jan 2026 can be
checked against late 2025. Same compositing as fetch_monthly_s2.py (Cloud Score+ >= 0.6, monthly median).
Also fetches clear-observation counts for Jan-Oct 2026. Writes data/monthly_s2_late.npz.

    python meeting_2026-10-28/scripts/fetch_monthly_s2_late.py
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


def month(year, m, nbr=True):
    start = ee.Date.fromYMD(year, m, 1)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(BOX).filterDate(start, start.advance(1, "month"))
           .linkCollection(CS, ["cs_cdf"]).map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))))
    n = col.select("B8").count().unmask(0).rename(f"n_{year}_{m:02d}")
    if not nbr:
        return [n]
    return [col.median().normalizedDifference(["B8", "B12"]).unmask(-9).rename(f"nbr_{year}_{m:02d}"), n]


out = {}
for bands in ([b for y in (2024, 2025) for m in (11, 12) for b in month(y, m)],
              [b for m in range(1, 11) for b in month(2026, m, nbr=False)]):
    img = ee.Image.cat(bands).reproject("EPSG:5070", None, 30).toFloat()
    raw = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    for b in raw.dtype.names:
        a = np.asarray(raw[b]).astype("float32")
        out[b] = np.where(a == -9, np.nan, a) if b.startswith("nbr") else a
    print("fetched", len(raw.dtype.names), "bands", flush=True)
np.savez_compressed(DATA / "monthly_s2_late.npz", **out)

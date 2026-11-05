"""Monthly Sentinel-2 NBR, Jan-Oct 2025 and 2026, on the pilot grid (read-only; for dating 2026 change).

    python meeting_2026-10-28/scripts/fetch_monthly_s2.py

Cloud Score+ (>= 0.6) masked monthly medians; 2026 October ends Oct 27 (year to date). S2 was disabled in
the pilot's BULC-D runs, so this is independent of BULC-D's input (but it is still spectral evidence, not
a verified disturbance date). Writes data/monthly_s2.npz: nbr_{year}_{month} (NaN where no clear obs).
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


def month_nbr(year, month):
    start = ee.Date.fromYMD(year, month, 1)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(BOX).filterDate(start, start.advance(1, "month"))
           .linkCollection(CS, ["cs_cdf"]).map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))))
    return col.median().normalizedDifference(["B8", "B12"]).rename(f"nbr_{year}_{month:02d}")


out = {}
for year in (2025, 2026):
    img = ee.Image.cat([month_nbr(year, m) for m in range(1, 11)]).reproject("EPSG:5070", None, 30).unmask(-9)
    raw = ee.data.computePixels({"expression": img.toFloat(), "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    for b in raw.dtype.names:
        a = np.asarray(raw[b]).astype("float32")
        out[b] = np.where(a == -9, np.nan, a)
    print("fetched", year, flush=True)
np.savez_compressed(DATA / "monthly_s2.npz", **out)
print("valid share per month:", {k: round(float(np.isfinite(v).mean()), 2) for k, v in out.items()})

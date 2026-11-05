"""Snow in the evidence stream BULC-D actually uses (read-only).

    python meeting_2026-10-28/scripts/fetch_snow.py

bulcd's L8/L9 mask removes QA_PIXEL bits 0-4 only (fill, dilated cloud, cirrus, cloud, shadow); bit 5
(snow) is NOT masked, so snow-flagged observations enter both expectation and monitoring. Per pixel on the
pilot grid: count of clear (bits 0-4 = 0) L8+L9 observations and of those flagged snow (bit 5), per year
2018-2026, Jan 1 - May 31 and Oct 1 - Dec 28; plus USGS 3DEP 10 m elevation (mean to 30 m).
Writes data/snow.npz.
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
LANDSAT = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
           .filterBounds(BOX))


def counts(year, a, b, tag):
    col = LANDSAT.filterDate(f"{year}-{a}", f"{year}-{b}")

    def flags(img):
        qa = img.select("QA_PIXEL")
        clear = qa.bitwiseAnd(0b11111).eq(0)
        return ee.Image.cat(clear.rename("clear"), clear.And(qa.bitwiseAnd(1 << 5).neq(0)).rename("snow"))

    s = col.map(flags).sum().unmask(0)
    return s.rename([f"clear_{tag}{year}", f"snow_{tag}{year}"])


bands = [counts(y, "01-01", "06-01", "spring") for y in range(2018, 2027)]
bands += [counts(y, "10-01", "12-29", "fall") for y in range(2018, 2026)]
dem = ee.ImageCollection("USGS/3DEP/10m_collection").filterBounds(BOX).mosaic().select("elevation") \
    .setDefaultProjection("EPSG:5070", None, 10).reduceResolution(ee.Reducer.mean(), maxPixels=16).rename("elev")
out = {}
for img in (ee.Image.cat(bands).toInt16(), dem.toFloat()):  # two requests: the 50 MB request limit
    raw = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    out.update({b: np.asarray(raw[b]) for b in raw.dtype.names})
np.savez_compressed(DATA / "snow.npz", **out)
print("wrote", DATA / "snow.npz", len(out), "bands")

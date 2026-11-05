"""Independent evidence for the target-year question (read-only, no BULC-D runs, no assets written).

    python meeting_2026-10-28/scripts/fetch_reference.py

On the pilot's 666 x 666 EPSG:5070 grid:
  - Sentinel-2 SR composites (Cloud Score+ masked median), NBR + RGB, for the same windows in 2025 and
    2026: summer (Jul 1 - Sep 15) and late season (Sep 15 - Oct 27). BULC-D's pilot runs use Landsat 8/9
    only, so S2 is an independent sensor (but still spectral evidence, not verified reference data).
  - Hansen Global Forest Change v1.13 lossyear (through 2025) and treecover2000.
  - LCMS (latest product version) annual Change class for the most recent years available.
Writes data/reference.npz.
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
WINDOWS = {"summer": ("07-01", "09-16"), "late": ("09-15", "10-28")}


def pixels(image):
    raw = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": GRID})
    return {b: np.asarray(raw[b]) for b in raw.dtype.names}


def s2(year, window):
    a, b = WINDOWS[window]
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(BOX)
           .filterDate(f"{year}-{a}", f"{year}-{b}").linkCollection(cs, ["cs_cdf"])
           .map(lambda i: i.updateMask(i.select("cs_cdf").gte(0.6))))
    med = col.median()
    nbr = med.normalizedDifference(["B8", "B12"]).rename("nbr")
    n = col.select("B8").count().rename("n")
    tag = f"{window}{year}"
    img = ee.Image.cat([nbr, med.select(["B4", "B3", "B2"]), n]).reproject("EPSG:5070", None, 30).unmask(-9)
    return {f"{tag}_{k}": v for k, v in pixels(img.rename(["nbr", "B4", "B3", "B2", "n"])).items()}


out = {}
for year in (2025, 2026):
    for window in WINDOWS:
        out.update(s2(year, window))
        print("s2", year, window, flush=True)

gfc = ee.Image("UMD/hansen/global_forest_change_2025_v1_13").select(["lossyear", "treecover2000"])
out.update({f"hansen_{k}": v for k, v in pixels(gfc.unmask(0)).items()})
print("hansen")

lcms = ee.ImageCollection("projects/gtac-data-publish/assets/LCMS/Product_Version/2025-11")
years = sorted(set(lcms.filterBounds(BOX).aggregate_array("year").getInfo()))
print("lcms years", years[-4:])
for y in years[-3:]:
    img = lcms.filter(ee.Filter.eq("year", y)).filterBounds(BOX).first().select("Change").unmask(0)
    out[f"lcms_change_{y}"] = pixels(img.rename("c"))["c"]
np.savez_compressed(DATA / "reference.npz", **out)
print("wrote", DATA / "reference.npz", sorted(out))

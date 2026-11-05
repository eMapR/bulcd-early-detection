"""Benchmark: one 10 x 10 km tile, full-year 2026 (year to date), configs A, B, C. Separate from the Jun-Sep
benchmark of 2026-10-26 (regional_bench/bench-*); nothing there or in regional/ is touched.

    python meeting_2026-10-28/scripts/bench_fullyear_tile.py start   # starts 3 export tasks
    python meeting_2026-10-28/scripts/bench_fullyear_tile.py read    # reads EECU / wall time -> data/bench_fullyear.json

Tile r0056c0034 (the pilot's first tile, also used in the Jun-Sep benchmark). The image is the full-year
analysis image from expectation_compare_fullyear.py (outcome, decrease, increase, first detection, episodes,
observation counts): the same BULC-D run as the exported products, with a slightly different band set.
Writes new assets under regional_bench/fullyear-2026/ only.
"""
import json
import sys
import tempfile

import ee

from expectation_compare_fullyear import BASE, DATA, FIRST_DOY, LAST_DOY, RUNS, X0, Y1, image_for  # noqa: E402
from bulcd.config.loader import load_config  # noqa: E402

FOLDER = "projects/bulcd-python-rebuild/assets/regional_bench/fullyear-2026"
TILE, S = "r0056c0034", 333
PREFIX = "bench-fullyear"


def config(name):
    e_first, e_last, target = RUNS[name]
    cfg = json.loads(json.dumps(BASE))
    cfg["export"]["asset_folder"] = FOLDER
    for s in cfg["evidence"]["expectation"]["sensors"].values():
        s["first_year"], s["last_year"] = e_first, e_last + 1
        s["first_doy"], s["last_doy"] = FIRST_DOY, LAST_DOY
    for s in cfg["evidence"]["target"]["sensors"].values():
        s["first_year"], s["last_year"] = target, target + 1
        s["first_doy"], s["last_doy"] = FIRST_DOY, LAST_DOY
    box = ee.Geometry.Rectangle([X0 - 600, Y1 - 30 * S - 600, X0 + 30 * S + 600, Y1 + 600], "EPSG:5070", False)
    cfg["study_area"]["aoi_coordinates"] = box.transform("EPSG:4326", 0.1).coordinates().getInfo()[0]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)
    return load_config(f.name)


def start():
    try:
        ee.data.createAsset({"type": "IMAGE_COLLECTION"}, FOLDER)
    except ee.EEException as e:
        print("folder:", e)
    for k in "ABC":
        img = image_for(config(k + "26"))
        task = ee.batch.Export.image.toAsset(image=img, description=f"{PREFIX}-{k}_{TILE}",
                                             assetId=f"{FOLDER}/{k}_{TILE}", crs="EPSG:5070",
                                             crsTransform=[30, 0, X0, 0, -30, Y1], dimensions=f"{S}x{S}",
                                             maxPixels=int(1e13))
        task.start()
        print("started", task.status()["description"], task.id)


def read():
    out = {}
    for op in ee.data.listOperations():
        m = op["metadata"]
        if m.get("description", "").startswith(PREFIX):
            out[m["description"]] = {"state": m["state"], "eecu_s": m.get("batchEecuUsageSeconds"),
                                     "start": m.get("startTime"), "end": m.get("endTime")}
    print(json.dumps(out, indent=1))
    (DATA / "bench_fullyear.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"start": start, "read": read}[sys.argv[1]]()

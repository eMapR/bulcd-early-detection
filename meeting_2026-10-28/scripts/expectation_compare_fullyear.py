"""Full-year (year-to-date) variant of expectation_compare.py. The Jun-Sep results stay as they are.

    python meeting_2026-10-28/scripts/expectation_compare_fullyear.py [A26 B26 C26 A25 A24]

Same pilot config (config_json on the 2026 asset) except the DOY windows:
  - monitoring (L8+L9) AND expectation (L8): DOY 1-362 instead of 152-273. The expectation must cover the
    same part of the year as the monitoring, or winter/spring observations would be scored against a
    harmonic fitted to summer only. last_doy 362 keeps the last 4-day bin (DOY 361-364) inside the year,
    so no bin spills into the next January (that would put Jan 2026 data into B's 2024-2025 expectation).
  - A24 / A25: config A for target years 2024 / 2025, so "first confirmed year" is on the same full-year
    basis. 2026 runs are YEAR-TO-DATE: bins after the latest image are empty.
Live computePixels in 111 x 111 px blocks; no exports, no assets written.

Bands per run (data/fullyear/{run}.npz): outcome, decrease, increase (final), first_dec (year*1000+doy of
the first bin with P(decrease) > 0.65, any outcome; 0 = never), episodes (decrease episode count),
last_ep (code of the last episode start), n_exp, n_mon (bins with a valid observation).
"""
import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
from bulcd.config.loader import load_config  # noqa: E402
from bulcd.engine import run_bulcd  # noqa: E402
from bulcd.inputs import organize_inputs  # noqa: E402

from bulcd_early_detection.outputs import _episode_state, _outcome_from_result  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
OUT = DATA / "fullyear"
CACHE = OUT / "blocks"
CACHE.mkdir(parents=True, exist_ok=True)
ASSET = "projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-2026"
X0, Y1, N, B = -2153385.0, 2750565.0, 666, 111
FIRST_DOY, LAST_DOY = 1, 362
RUNS = {"A26": (2018, 2023, 2026), "B26": (2024, 2025, 2026), "C26": (2018, 2025, 2026),
        "A25": (2018, 2023, 2025), "A24": (2018, 2023, 2024)}
BANDS = ["outcome", "decrease", "increase", "first_dec", "episodes", "last_ep", "n_exp", "n_mon"]

TILE = ee.data.listAssets({"parent": ASSET})["assets"][0]["name"]
BASE = json.loads(ee.data.getAsset(TILE)["properties"]["config_json"])


def config_for(name, x0, y1):
    e_first, e_last, target = RUNS[name]
    cfg = json.loads(json.dumps(BASE))
    cfg["export"]["asset_folder"] = "unused"  # nothing is exported; the loader requires a value
    for s in cfg["evidence"]["expectation"]["sensors"].values():
        s["first_year"], s["last_year"] = e_first, e_last + 1  # bulcd's last_year is exclusive
        s["first_doy"], s["last_doy"] = FIRST_DOY, LAST_DOY
    for s in cfg["evidence"]["target"]["sensors"].values():
        s["first_year"], s["last_year"] = target, target + 1
        s["first_doy"], s["last_doy"] = FIRST_DOY, LAST_DOY
    box = ee.Geometry.Rectangle([x0 - 600, y1 - 30 * B - 600, x0 + 30 * B + 600, y1 + 600], "EPSG:5070", False)
    cfg["study_area"]["aoi_coordinates"] = box.transform("EPSG:4326", 0.1).coordinates().getInfo()[0]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)
    return load_config(f.name)


def image_for(config):
    result = run_bulcd(config)
    out = _outcome_from_result(result, config, 0.65, 0.75).select(["outcome", "decrease", "increase"])
    state = _episode_state(result.probability_stack, 0.65)

    def code(img):
        date = ee.Date(img.get("system:time_start"))
        value = date.get("year").multiply(1000).add(date.getRelative("day", "year").add(1))
        return ee.Image.constant(value).toInt32().rename("c").updateMask(img.select("decrease").gt(0.65))

    first = ee.ImageCollection(result.probability_stack.map(code)).min().unmask(0).rename("first_dec")
    inputs = organize_inputs(config)
    band = config.reduction.band
    n_exp = inputs.expectation_collection.select(band).count().rename("n_exp")
    n_mon = inputs.target_collection.select(band).count().rename("n_mon")
    return ee.Image.cat([out, first, state.select("count").rename("episodes"), state.select("last").rename("last_ep"),
                         n_exp, n_mon]).toFloat()


def block(name, r, c):
    out = CACHE / f"{name}_{r}_{c}.npz"
    if out.exists():
        return
    x0, y1 = X0 + 30 * B * c, Y1 - 30 * B * r
    img = image_for(config_for(name, x0, y1))
    grid = {"dimensions": {"width": B, "height": B}, "crsCode": "EPSG:5070",
            "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": x0, "shearY": 0, "scaleY": -30,
                                "translateY": y1}}
    t = time.time()
    for attempt in range(4):
        try:
            raw = ee.data.computePixels({"expression": img.unmask(-999).select(BANDS), "fileFormat": "NUMPY_NDARRAY",
                                         "grid": grid})
            break
        except ee.EEException as e:
            print(name, r, c, "retry", attempt, e, flush=True)
    else:
        raise RuntimeError(f"block {name} {r} {c} failed")
    np.savez(out, **{b: np.asarray(raw[b]) for b in BANDS})
    print("done", name, r, c, f"{time.time() - t:.0f}s", flush=True)


def assemble(name):
    full = {b: np.zeros((N, N), "float32") for b in BANDS}
    for r in range(N // B):
        for c in range(N // B):
            d = np.load(CACHE / f"{name}_{r}_{c}.npz")
            for b in BANDS:
                full[b][r * B:(r + 1) * B, c * B:(c + 1) * B] = d[b]
    np.savez_compressed(OUT / f"{name}.npz", **full)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--one"]:  # timing test: one block
        block(args[1], 2, 2)
        sys.exit()
    names = args or list(RUNS)
    jobs = [(n, r, c) for n in names for r in range(N // B) for c in range(N // B)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda j: block(*j), jobs))
    for n in names:
        assemble(n)
    print("assembled", names)

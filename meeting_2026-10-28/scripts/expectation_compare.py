"""Expectation-period experiment (Slide 6): 2026 monitoring under three expectation windows.

    A  2018-2023  (the pilot's own; recomputed live and checked against the asset)
    B  2024-2025  (recent only)
    C  2018-2025  (extended)

Everything else is the pilot's stored 2026 config (config_json on the asset): L8 expectation,
L8+L9 monitoring, Jun 1 - Sep 30, sensitivity 1, thresholds 0.65 / 0.75, 30 m on the pilot's
EPSG:5070 grid. Live computePixels in 111 x 111 px blocks; no exports, no assets written.

    python meeting_2026-10-28/scripts/expectation_compare.py [A B C]

Writes data/expectation_{A,B,C}.npz (outcome, p_decrease, p_increase, n_exp) and
data/expectation_blocks/ (per-block cache, so a rerun resumes).
"""
import json
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")
from bulcd.config.loader import load_config  # noqa: E402
from bulcd.inputs import organize_inputs  # noqa: E402

from bulcd_early_detection.outputs import outcome_image  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"
CACHE = DATA / "expectation_blocks"
CACHE.mkdir(parents=True, exist_ok=True)
ASSET = "projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-2026"
X0, Y1, N, B = -2153385.0, 2750565.0, 666, 111
CONFIGS = {"A": (2018, 2023), "B": (2024, 2025), "C": (2018, 2025)}
BANDS = ["outcome", "decrease", "increase", "n_exp"]

TILE = ee.data.listAssets({"parent": ASSET})["assets"][0]["name"]
BASE = json.loads(ee.data.getAsset(TILE)["properties"]["config_json"])


def config_for(name, x0, y1):
    first, last = CONFIGS[name]
    cfg = json.loads(json.dumps(BASE))
    cfg["export"]["asset_folder"] = "unused"  # nothing is exported; the loader requires a value
    for s in cfg["evidence"]["expectation"]["sensors"].values():
        s["first_year"], s["last_year"] = first, last + 1  # bulcd's last_year is exclusive
    box = ee.Geometry.Rectangle([x0 - 600, y1 - 30 * B - 600, x0 + 30 * B + 600, y1 + 600], "EPSG:5070", False)
    cfg["study_area"]["aoi_coordinates"] = box.transform("EPSG:4326", 0.1).coordinates().getInfo()[0]
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        json.dump(cfg, f)
    return load_config(f.name)


def block(name, r, c):
    out = CACHE / f"{name}_{r}_{c}.npz"
    if out.exists():
        return
    x0, y1 = X0 + 30 * B * c, Y1 - 30 * B * r
    config = config_for(name, x0, y1)
    n_exp = organize_inputs(config).expectation_collection.select(config.reduction.band).count().rename("n_exp")
    img = ee.Image.cat([outcome_image(config, 0.65, 0.75).select(["outcome", "decrease", "increase"]), n_exp])
    grid = {"dimensions": {"width": B, "height": B}, "crsCode": "EPSG:5070",
            "affineTransform": {"scaleX": 30, "shearX": 0, "translateX": x0, "shearY": 0, "scaleY": -30,
                                "translateY": y1}}
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
    print("done", name, r, c, flush=True)


def assemble(name):
    full = {b: np.zeros((N, N), "float32") for b in BANDS}
    for r in range(N // B):
        for c in range(N // B):
            d = np.load(CACHE / f"{name}_{r}_{c}.npz")
            for b in BANDS:
                full[b][r * B:(r + 1) * B, c * B:(c + 1) * B] = d[b]
    np.savez_compressed(DATA / f"expectation_{name}.npz", **full)


names = sys.argv[1:] or list(CONFIGS)
jobs = [(n, r, c) for n in names for r in range(N // B) for c in range(N // B)]
with ThreadPoolExecutor(max_workers=8) as pool:
    list(pool.map(lambda j: block(*j), jobs))
for n in names:
    assemble(n)
print("assembled", names)

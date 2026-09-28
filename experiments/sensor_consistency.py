"""Does adding Sentinel-2 to monitoring create change detections when the
expectation (baseline) model was built from Landsat 8 only?

Lead being tested (docs/findings.md, 2026-09-28): on the ~3 km^2
stockton_south_shore AOI, dropping S2 from monitoring cut decrease from
0.049 to 0.001 km^2. The notebook's baseline is L8-only (an EE memory
workaround) while monitoring is L8+L9+S2.

Design: every run uses the notebook's default controls and build_config()
(same season, years, threshold, matrix, sensitivity, masks); ONLY the
expectation/monitoring sensor sets change:

    L8 -> L8          consistent, single sensor
    L8 -> L8+L9       consistent sensor family (the notebook's "Landsat-only")
    L8 -> L8+L9+S2    current production setting (mixed)
    L8 -> S2          cross-sensor only
    S2 -> S2          consistent, S2 only
    L8+S2 -> L8+L9+S2 mixed, but the baseline includes S2

If the S2 detections are a cross-sensor artifact, they should appear when
the baseline lacks S2 (L8->S2, L8->L8+L9+S2) and shrink when the baseline
includes it (S2->S2, L8+S2->...). L8->S2 vs. L8->L8+L9 also separates
"S2 is a different sensor" from "S2 simply adds observations", since S2
alone has at least as many summer observations as L8+L9.

AOIs (notebooks/aois/): suspicious shoreline, stable interior forest, and
a known real disturbance (the July 2026 fire from replay_fire_2026.py).
Per AOI x variant: decrease/increase km^2 (water- and forest-masked, as
in the notebook) and the first-detection day-of-year distribution of
decrease pixels -- the early-June question.

Resumable: each (AOI, variant) row is appended to the CSV as it finishes;
re-running skips completed rows. Failures (e.g. EE memory limits on an S2
baseline) are recorded, not fatal.

    python experiments/sensor_consistency.py
"""

from __future__ import annotations

import copy
import csv
import sys
import time
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.engine import run_bulcd  # noqa: E402

from bulcd_early_detection import compare, drawing, outputs  # noqa: E402
from bulcd_early_detection.config import MonitoringControls, build_config  # noqa: E402
from bulcd_early_detection.outputs import DECREASE, INCREASE  # noqa: E402

OUTPUT_CSV = Path(__file__).parent / "output" / "sensor_consistency.csv"
AOI_DIR = Path(__file__).resolve().parents[1] / "notebooks" / "aois"

AOIS = [
    # (name, role) -- polygons saved in notebooks/aois/
    ("stockton_south_shore", "shoreline, suspicious"),
    ("shoreline_top_decrease", "shoreline, suspicious"),
    ("stockton_interior", "interior forest, stable"),
    ("interior_forest_quiet", "interior forest, stable"),
    ("fire_2026_wa", "known disturbance (fire, Jul 18-21 2026)"),
]

# name -> (expectation sensors, monitoring sensors)
VARIANTS = {
    "L8 -> L8": (("L8",), ("L8",)),
    "L8 -> L8+L9": (("L8",), ("L8", "L9")),
    "L8 -> L8+L9+S2": (("L8",), ("L8", "L9", "S2")),
    "L8 -> S2": (("L8",), ("S2",)),
    "S2 -> S2": (("S2",), ("S2",)),
    "L8+S2 -> L8+L9+S2": (("L8", "S2"), ("L8", "L9", "S2")),
}

EARLY_DAYS = 14  # "first two weeks of the season", as in docs/findings.md

FIELDS = ["aoi", "role", "variant", "expectation", "monitoring", "status", "error", "run_s",
          "forest_km2", "decrease_km2", "increase_km2", "decrease_pixels",
          "early_frac", "median_first_doy", "first_doy_p10", "first_doy_p90", "doy_hist"]


def with_sensors(config, expectation: tuple[str, ...], monitoring: tuple[str, ...]):
    """Copy of `config` with only the sensor sets changed. Every sensor's
    settings (years, season, cloud prefilter) are copied from the sensor
    build_config() already configured for that period, so nothing else
    differs between variants."""
    c = copy.deepcopy(config)
    for period, names in ((c.evidence.expectation, expectation), (c.evidence.target, monitoring)):
        template = next(iter(period.sensors.values()))
        period.sensors = {n: copy.deepcopy(period.sensors.get(n, template)) for n in names}
    return c


def fetch(config, area, grid, threshold: float) -> dict[str, np.ndarray]:
    """compare.fetch_run plus first-crossing day of year for each class."""
    result = run_bulcd(compare._with_masks(config, False, False))
    probs = result.final_probabilities.select(["decrease", "unchanged", "increase"]).unmask(-1)
    first_dec = outputs._first_crossing_doy(result.probability_stack, "decrease", threshold).unmask(-1)
    first_inc = outputs._first_crossing_doy(result.probability_stack, "increase", threshold).unmask(-1)
    from bulcd.engine import study_area_mask
    land = study_area_mask(compare._with_masks(config, True, False)).unmask(0).rename("land")
    forest = study_area_mask(compare._with_masks(config, False, True)).unmask(0).rename("forest")
    inside = ee.Image.constant(1).clip(area.geometry).unmask(0).rename("inside")
    image = ee.Image.cat(probs, land, forest, inside,
                         first_dec.rename("first_dec"), first_inc.rename("first_inc")).toFloat()
    arr = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    return {b: np.asarray(arr[b], dtype=float) for b in arr.dtype.names}


def summarize(run, controls, config) -> dict:
    classes = compare.classify(run, controls.decision_threshold,
                               config.study_area.mask_water, config.study_area.mask_non_forest)
    inside = run["inside"] > 0
    px_km2 = compare.PIXEL_M ** 2 / 1e6
    dec = (classes == DECREASE) & inside
    doys = run["first_dec"][dec]
    doys = doys[doys > 0]
    first_doy = int(time.strftime("%j", time.strptime(f"{controls.monitoring_year}-{controls.season_start}", "%Y-%m-%d")))
    hist = {}
    for d in doys.astype(int):
        hist[int(d)] = hist.get(int(d), 0) + 1
    return {
        "forest_km2": round(float(np.sum((run["forest"] > 0) & (run["land"] > 0) & inside)) * px_km2, 3),
        "decrease_km2": round(float(dec.sum()) * px_km2, 4),
        "increase_km2": round(float(np.sum((classes == INCREASE) & inside)) * px_km2, 4),
        "decrease_pixels": int(dec.sum()),
        "early_frac": round(float(np.mean(doys < first_doy + EARLY_DAYS)), 3) if doys.size else "",
        "median_first_doy": float(np.median(doys)) if doys.size else "",
        "first_doy_p10": float(np.percentile(doys, 10)) if doys.size else "",
        "first_doy_p90": float(np.percentile(doys, 90)) if doys.size else "",
        "doy_hist": " ".join(f"{k}:{v}" for k, v in sorted(hist.items())),
    }


def main() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUTPUT_CSV.exists():
        with OUTPUT_CSV.open() as f:
            done = {(r["aoi"], r["variant"]) for r in csv.DictReader(f) if r["status"] == "ok"}
    controls = MonitoringControls()
    new_file = not OUTPUT_CSV.exists()
    with OUTPUT_CSV.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for aoi_name, role in AOIS:
            area = drawing.study_area(aoi_name, AOI_DIR)
            grid = compare.pixel_grid(area.geometry)
            for vname, (exp, mon) in VARIANTS.items():
                if (aoi_name, vname) in done:
                    continue
                row = {"aoi": aoi_name, "role": role, "variant": vname,
                       "expectation": "+".join(exp), "monitoring": "+".join(mon)}
                t0 = time.time()
                try:
                    config = with_sensors(build_config(controls, **area.aoi), exp, mon)
                    run = fetch(config, area, grid, controls.decision_threshold)
                    row.update(status="ok", **summarize(run, controls, config))
                except Exception as e:  # recorded, not fatal (e.g. EE memory limit)
                    row.update(status="error", error=f"{type(e).__name__}: {e}"[:300])
                row["run_s"] = round(time.time() - t0)
                w.writerow(row)
                f.flush()
                print(f"{aoi_name:<24}{vname:<20}{row['status']:<6}{row['run_s']:>5}s  "
                      f"dec={row.get('decrease_km2', '')}  early={row.get('early_frac', '')}  "
                      f"{row.get('error', '')[:120]}", flush=True)


if __name__ == "__main__":
    main()

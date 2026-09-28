"""Side-by-side parameter comparison over one small study area.

Each BULC-D run's final probabilities are fetched ONCE as a pixel array
(ee.data.computePixels) on a fixed 30 m grid, then classified locally.
The decision threshold and the water/forest masks are applied after
BULC-D runs (bulcd.engine.run_bulcd masks final_probabilities only at the
end), so variants that differ only in those reuse the same run - no
extra Earth Engine computation. Only real parameter changes trigger a
new run.

Outputs are limited to the primary outcome map and area totals.
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass, field
from typing import Callable

import ee
import matplotlib.pyplot as plt
import numpy as np
from bulcd.config.schema import BULCDConfig
from bulcd.engine import run_bulcd, study_area_mask
from matplotlib.colors import to_rgb
from matplotlib.patches import Patch

from . import outputs
from .outputs import DECREASE, INCREASE, NOT_ANALYZED, OUTCOME_LABELS, UNCHANGED, StudyArea
from .render import OUTCOME_COLORS, OUTSIDE_COLOR, WATER_COLOR, scale_bar

PIXEL_M = 30
_BANDS = ["decrease", "unchanged", "increase", "land", "forest", "inside"]


@dataclass
class Variant:
    """One named configuration to compare.

    `controls`: overrides for MonitoringControls fields (e.g.
    {"decision_threshold": 0.9} or {"baseline_first_year": 2022}).
    `edit`: optional function that edits the built BULCDConfig in place
    (or returns a new one) - any advanced BULC-D parameter.
    `purpose`: what this variant tests; shown with the results.
    """

    name: str
    purpose: str
    controls: dict = field(default_factory=dict)
    edit: Callable[[BULCDConfig], BULCDConfig | None] | None = None


def _utm_crs(geometry: ee.Geometry) -> str:
    lon, lat = geometry.centroid(1).coordinates().getInfo()
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def pixel_grid(geometry: ee.Geometry) -> dict:
    """A 30 m UTM grid covering `geometry`, snapped to 30 m multiples."""
    crs = _utm_crs(geometry)
    ring = geometry.transform(crs, 1).bounds(1, crs).coordinates().get(0).getInfo()
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    x0 = np.floor(min(xs) / PIXEL_M) * PIXEL_M
    y1 = np.ceil(max(ys) / PIXEL_M) * PIXEL_M
    width = int(np.ceil((max(xs) - x0) / PIXEL_M))
    height = int(np.ceil((y1 - min(ys)) / PIXEL_M))
    return {
        "dimensions": {"width": width, "height": height},
        "affineTransform": {
            "scaleX": PIXEL_M, "shearX": 0, "translateX": float(x0),
            "shearY": 0, "scaleY": -PIXEL_M, "translateY": float(y1),
        },
        "crsCode": crs,
    }


def _run_key(config: BULCDConfig) -> str:
    """Identifies a BULC-D run: the full config minus the masks, which
    are applied locally afterwards."""
    d = dataclasses.asdict(config)
    for k in ("mask_water", "mask_non_forest"):
        d["study_area"].pop(k)
    return json.dumps(d, sort_keys=True, default=str)


def _with_masks(config: BULCDConfig, water: bool, forest: bool) -> BULCDConfig:
    return dataclasses.replace(
        config, study_area=dataclasses.replace(config.study_area, mask_water=water, mask_non_forest=forest)
    )


def fetch_run(config: BULCDConfig, area: StudyArea, grid: dict) -> dict[str, np.ndarray]:
    """Runs BULC-D once and downloads its final probabilities plus the
    water/forest/inside-area flags as 2-D arrays on `grid`."""
    result = run_bulcd(_with_masks(config, False, False))
    probs = result.final_probabilities.select(["decrease", "unchanged", "increase"]).unmask(-1)
    land = study_area_mask(_with_masks(config, True, False)).unmask(0).rename("land")
    forest = study_area_mask(_with_masks(config, False, True)).unmask(0).rename("forest")
    inside = ee.Image.constant(1).clip(area.geometry).unmask(0).rename("inside")
    image = ee.Image.cat(probs, land, forest, inside).toFloat()
    arr = ee.data.computePixels({"expression": image, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    return {b: np.asarray(arr[b], dtype=float) for b in _BANDS}


def classify(run: dict[str, np.ndarray], threshold: float, mask_water: bool, mask_non_forest: bool) -> np.ndarray:
    """Outcome codes per pixel, same rule as outputs.outcome_image();
    NaN outside the area, and on water when masked."""
    inside = run["inside"] > 0
    land = run["land"] > 0 if mask_water else np.ones_like(inside)
    analyzed = inside & land & (run["decrease"] >= 0)
    if mask_non_forest:
        analyzed &= run["forest"] > 0
    classes = np.full(inside.shape, np.nan)
    classes[inside & land] = NOT_ANALYZED
    classes[analyzed] = UNCHANGED
    classes[analyzed & (run["decrease"] > threshold)] = DECREASE
    classes[analyzed & (run["increase"] > threshold)] = INCREASE
    return classes


def run_comparison(area: StudyArea, controls, build, variants: list[Variant]) -> list[dict]:
    """Runs every variant over exactly `area`; returns one dict per
    variant with its outcome array and km^2 per class."""
    grid = pixel_grid(area.geometry)
    runs: dict[str, dict] = {}
    results = []
    for v in variants:
        c = dataclasses.replace(controls, **v.controls)
        config = build(c, **area.aoi)
        if v.edit is not None:
            config = v.edit(config) or config
        key = _run_key(config)
        if key in runs:
            print(f"{v.name}: reusing an earlier run (differs only in threshold/masks)")
        else:
            print(f"{v.name}: running BULC-D ...", end=" ", flush=True)
            t0 = time.time()
            runs[key] = fetch_run(config, area, grid)
            print(f"{time.time() - t0:.0f} s")
        classes = classify(runs[key], c.decision_threshold, config.study_area.mask_water, config.study_area.mask_non_forest)
        km2 = {OUTCOME_LABELS[k]: float(np.sum(classes == k)) * PIXEL_M**2 / 1e6 for k in OUTCOME_LABELS}
        results.append({"variant": v, "classes": classes, "inside": runs[key]["inside"] > 0, "km2": km2})
    return results


def _rgb(classes: np.ndarray, inside: np.ndarray) -> np.ndarray:
    rgb = np.empty(classes.shape + (3,))
    rgb[:] = to_rgb(OUTSIDE_COLOR)
    rgb[inside & np.isnan(classes)] = to_rgb(WATER_COLOR)
    for k, color in OUTCOME_COLORS.items():
        rgb[classes == k] = to_rgb(color)
    return rgb


def show_comparison(results: list[dict], title: str, save_to=None):
    """Outcome maps side by side (max 3 per row), one shared legend."""
    n = len(results)
    ncols = min(n, 3)
    nrows = int(np.ceil(n / ncols))
    h, w = results[0]["classes"].shape
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 4.6 * nrows * h / w + 0.9), dpi=110, squeeze=False)
    for ax in axes.flat[n:]:
        ax.set_axis_off()
    for ax, r in zip(axes.flat, results):
        ax.imshow(_rgb(r["classes"], r["inside"]), interpolation="nearest")
        ax.set_axis_off()
        dec, inc = r["km2"][OUTCOME_LABELS[DECREASE]], r["km2"][OUTCOME_LABELS[INCREASE]]
        ax.set_title(f"{r['variant'].name}\ndecrease {dec:.3f} km² · increase {inc:.3f} km²", fontsize=10, loc="left")
        scale_bar(ax, PIXEL_M / 1000, w)
    handles = [Patch(facecolor=OUTCOME_COLORS[k], edgecolor="#999", label=OUTCOME_LABELS[k]) for k in (DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED)]
    handles.append(Patch(facecolor=WATER_COLOR, edgecolor="#999", label="Water (masked)"))
    fig.legend(handles=handles, loc="lower center", ncol=5, frameon=False, fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97), h_pad=2.5)
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, bbox_inches="tight")
    plt.show()
    return fig


def comparison_table(results: list[dict]) -> str:
    """Markdown table: km^2 per outcome for each variant, and its purpose."""
    order = [DECREASE, INCREASE, UNCHANGED, NOT_ANALYZED]
    head = "| Variant | " + " | ".join(OUTCOME_LABELS[k] + " (km²)" for k in order) + " | What it tests |"
    rule = "|---|" + "---:|" * len(order) + "---|"
    rows = [
        f"| {r['variant'].name} | " + " | ".join(f"{r['km2'][OUTCOME_LABELS[k]]:.3f}" for k in order) + f" | {r['variant'].purpose} |"
        for r in results
    ]
    return "\n".join([head, rule, *rows])

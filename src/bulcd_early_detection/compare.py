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
from matplotlib.lines import Line2D
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


def pixel_grid(geometry: ee.Geometry) -> dict:
    """A 30 m UTM grid covering `geometry`, snapped to 30 m multiples."""
    crs = outputs.utm_crs(geometry)
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
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, (4.6 * h / w + 0.7) * nrows + 0.6), dpi=110, squeeze=False)
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


# ---------------------------------------------------------------- one-at-a-time parameter response
def _set_advanced(field_name: str, value: float):
    def edit(config):
        setattr(config.bulc_advanced_params, field_name, value)
    return edit


# Parameters swept one at a time (everything else at the notebook's defaults).
# (label, what it means, values, how to apply, default)
PARAMETER_SWEEPS = [
    ("Sensitivity", "scales every departure from normal", [0.5, 0.75, 1.0, 1.5, 2.0],
     lambda v: {"controls": {"sensitivity": v}}, 1.0),
    ("Decision threshold", "how sure before a change is mapped", [0.5, 0.6, 0.7, 0.8, 0.9, 0.95],
     lambda v: {"controls": {"decision_threshold": v}}, 0.5),
    ("Dampening", "weight of each single observation", [0.3, 0.5, 0.7, 0.9, 1.0],
     lambda v: {"edit": _set_advanced("dampening_factor", v)}, 0.5),
    ("Posterior leveler", "pull toward even odds after each update (1 = off)", [0.7, 0.8, 0.9, 0.95, 1.0],
     lambda v: {"edit": _set_advanced("posterior_leveler", v)}, 1.0),
]


def parameter_response(area: StudyArea, controls, build, sweeps=PARAMETER_SWEEPS) -> list[dict]:
    """Detected decrease/increase area as each parameter moves alone.
    Returns rows {parameter, value, is_default, decrease_km2, increase_km2}.
    Threshold values reuse one BULC-D run (it only re-reads probabilities)."""
    variants, meta = [], []
    for label, _, values, apply, default in sweeps:
        for v in values:
            variants.append(Variant(f"{label} = {v}", "", **apply(v)))
            meta.append((label, v, v == default))
    results = run_comparison(area, controls, build, variants)
    return [
        {"parameter": label, "value": v, "is_default": d,
         "decrease_km2": r["km2"][OUTCOME_LABELS[DECREASE]], "increase_km2": r["km2"][OUTCOME_LABELS[INCREASE]]}
        for (label, v, d), r in zip(meta, results)
    ]


def plot_parameter_response(rows: list[dict], title: str = "", sweeps=PARAMETER_SWEEPS, save_to=None):
    """Small multiples, one per parameter: detected decrease and increase
    area (km^2) against the parameter value; the default is marked."""
    fig, axes = plt.subplots(1, len(sweeps), figsize=(3.6 * len(sweeps), 3.4), dpi=110, sharey=True, squeeze=False)
    for ax, (label, meaning, *_rest) in zip(axes[0], sweeps):
        pr = [r for r in rows if r["parameter"] == label]
        xs = [r["value"] for r in pr]
        for key, cls in (("decrease_km2", DECREASE), ("increase_km2", INCREASE)):
            ax.plot(xs, [r[key] for r in pr], color=OUTCOME_COLORS[cls], lw=2, marker="o", ms=5)
        default = next(r for r in pr if r["is_default"])
        ax.axvline(default["value"], color="#999", lw=1, ls=":")
        ax.text(default["value"], 1.0, " default", transform=ax.get_xaxis_transform(), fontsize=8, color="#666", va="top")
        ax.set_title(label, fontsize=11, loc="left")
        ax.set_xlabel(meaning, fontsize=8, color="#555")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color="#e6e5e0", lw=0.8)
        ax.set_axisbelow(True)
    axes[0][0].set_ylabel("Area (km²)")
    handles = [Line2D([], [], color=OUTCOME_COLORS[DECREASE], lw=2, marker="o", label="Decrease detected"),
               Line2D([], [], color=OUTCOME_COLORS[INCREASE], lw=2, marker="o", label="Increase detected")]
    fig.legend(handles=handles, loc="lower center", ncol=2, frameon=False, fontsize=9)
    if title:
        fig.suptitle(title, x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, bbox_inches="tight")
    plt.show()
    return fig

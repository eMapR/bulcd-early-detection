"""Static map rendering for the monitoring layers.

Earth Engine renders each layer to a PNG (ee.Image.getThumbURL); matplotlib
adds the legend/colorbar, scale bar, and title. Static images rather than
an interactive map: they embed in the saved notebook, so a presentation
doesn't depend on a live Earth Engine connection.
"""

from __future__ import annotations

import datetime
import io
import math
import urllib.request
from pathlib import Path

import ee
import google.auth.transport.requests
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Patch

from .outputs import DECREASE, INCREASE, NOT_ANALYZED, OUTCOME_LABELS, UNCHANGED, StudyArea

# Outcome colors: a diverging pair (red = decrease, blue = increase) with
# a neutral gray midpoint for "unchanged"; context layers stay pale so
# change pixels carry the eye.
OUTCOME_COLORS = {
    DECREASE: "#e34948",
    UNCHANGED: "#bdbbb3",
    INCREASE: "#2a78d6",
    NOT_ANALYZED: "#e6e5e0",
}
WATER_COLOR = "#d4e4f1"
OUTSIDE_COLOR = "#f7f7f5"
BOUNDARY_COLOR = "#4a4a48"
# Purple, not blue, so it isn't read as "increase".
CONFIDENCE_RAMP = ["#e3d7f5", "#b79be6", "#8a63cf", "#6139a8", "#3f1d7a"]
# Earlier = darker: early-season detections are usually the most common,
# and the lightest steps would vanish against the pale land backdrop.
TIMING_RAMP = ["#7c2d12", "#c2410c", "#ec7a3a", "#f8b27c", "#fde0c5"]

THUMB_DIMENSIONS = 1400


def auth_token() -> str:
    creds = ee.data.get_persistent_credentials()
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def download_png(image: ee.Image, region: ee.Geometry, token: str, dimensions: int = THUMB_DIMENSIONS, attempts: int = 3) -> bytes:
    """PNG bytes of an already-visualized image (same authenticated
    getThumbURL idiom as ../BULC-D_rebuild/scripts/debug_disturbance_map.py)."""
    url = image.getThumbURL({"region": region, "dimensions": dimensions, "format": "png"})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(req).read()
        except (ConnectionResetError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise
            print(f"  download retry ({exc}) ...")


def reference_composite(region: ee.Geometry, start: str, end: str) -> ee.Image:
    """False-color (SWIR2/NIR/Red) Sentinel-2 median composite -
    independent of BULC-D's own evidence pipeline, purely visual context.
    Bare/burned ground reads orange-brown, vegetation green, water dark.

    S2_SR_HARMONIZED is raw DN (0-10000), not 0-1 reflectance - visualize
    with min=0, max=4000; dividing first saturates NIR (docs/findings.md,
    2026-09-20).
    """
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        .median()
        .select(["B12", "B8", "B4"])
    )


def _backdrop(region: ee.Geometry) -> ee.Image:
    """Pale land/water context (JRC Global Surface Water) for the areas
    outside the analyzed boundary."""
    water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).gt(50).clip(region)
    return water.visualize(min=0, max=1, palette=[OUTSIDE_COLOR[1:], WATER_COLOR[1:]])


def _boundary(geometry: ee.Geometry) -> ee.Image:
    return ee.Image().byte().paint(ee.FeatureCollection([ee.Feature(geometry)]), 1, 1).visualize(palette=[BOUNDARY_COLOR[1:]])


def _layer(layer: ee.Image, area: StudyArea, frame: ee.Geometry) -> ee.Image:
    return _backdrop(frame).blend(layer).blend(_boundary(area.geometry))


# Overview maps: a 30 m change is ~1 screen pixel or less at park scale,
# so change pixels can be grown by one DISPLAY pixel (kernel in output-grid
# pixels) to stay visible. Display only - area stats use exact pixels.
_ENLARGE_RADIUS_PX = 1.5


def _grow(image: ee.Image, reducer: str) -> ee.Image:
    grown = image.focalMax(_ENLARGE_RADIUS_PX, "circle", "pixels") if reducer == "max" else image.focalMin(_ENLARGE_RADIUS_PX, "circle", "pixels")
    return image.unmask(grown)


def _analyzed_land(outputs: ee.Image) -> ee.Image:
    """Unchanged + not-analyzed land in their outcome colors (context for
    layers that only draw change pixels)."""
    outcome = outputs.select("outcome")
    return outcome.updateMask(outcome.gte(UNCHANGED)).visualize(
        min=UNCHANGED, max=NOT_ANALYZED, palette=["eeede9", "eeede9", OUTCOME_COLORS[NOT_ANALYZED][1:]]
    )


def _changed(outputs: ee.Image) -> ee.Image:
    outcome = outputs.select("outcome")
    return outcome.eq(DECREASE).Or(outcome.eq(INCREASE))


def outcome_layer(outputs: ee.Image, area: StudyArea, frame: ee.Geometry, enlarge_changes: bool = False) -> ee.Image:
    outcome = outputs.select("outcome")
    palette = [OUTCOME_COLORS[k][1:] for k in (DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED)]
    vis = outcome.visualize(min=0, max=3, palette=palette)
    if enlarge_changes:
        for cls in (INCREASE, DECREASE):  # decrease drawn last, on top
            grown = outcome.eq(cls).selfMask().focalMax(_ENLARGE_RADIUS_PX, "circle", "pixels")
            vis = vis.blend(grown.visualize(palette=[OUTCOME_COLORS[cls][1:]]))
    return _layer(vis, area, frame)


def confidence_layer(outputs: ee.Image, area: StudyArea, frame: ee.Geometry, threshold: float, enlarge_changes: bool = False) -> ee.Image:
    """Probability of the mapped change, for change pixels only (unchanged
    pixels sit at ~1.0 almost everywhere, so mapping them adds nothing)."""
    conf = outputs.select("confidence").updateMask(_changed(outputs))
    if enlarge_changes:
        conf = _grow(conf, "max")
    vis = conf.visualize(min=threshold, max=1, palette=[c[1:] for c in CONFIDENCE_RAMP])
    return _layer(_analyzed_land(outputs).blend(vis), area, frame)


def timing_layer(outputs: ee.Image, area: StudyArea, frame: ee.Geometry, first_doy: int, last_doy: int, enlarge_changes: bool = False) -> ee.Image:
    doy = outputs.select("first_detection_doy")
    if enlarge_changes:
        doy = _grow(doy, "min")
    vis = doy.visualize(min=first_doy, max=last_doy, palette=[c[1:] for c in TIMING_RAMP])
    return _layer(_analyzed_land(outputs).blend(vis), area, frame)


def reference_layer(area: StudyArea, frame: ee.Geometry, start: str, end: str) -> ee.Image:
    # Per-band stretch (SWIR2, NIR, red): NIR over dense forest runs far
    # higher than the other two, and a shared 0-4000 range saturates it.
    img = reference_composite(frame, start, end).visualize(min=[0, 0, 0], max=[2500, 5000, 1500], gamma=1.2)
    return img.blend(_boundary(area.geometry))


def _scale_bar(ax, bbox_degrees: list[float], width_px: int) -> None:
    west, south, east, north = bbox_degrees
    km_per_px = (east - west) * 111.32 * math.cos(math.radians((south + north) / 2)) / width_px
    total_km = km_per_px * width_px
    length_km = next(n for n in (50, 20, 10, 5, 2, 1, 0.5, 0.2) if n <= total_km / 4)
    px = length_km / km_per_px
    x0, y0 = width_px * 0.03, ax.get_ylim()[0] * 0.96
    halo = [pe.withStroke(linewidth=5, foreground="white")]
    ax.plot([x0, x0 + px], [y0, y0], color="#222", lw=3, solid_capstyle="butt", path_effects=halo)
    ax.text(x0 + px / 2, y0 - 8, f"{length_km:g} km", ha="center", va="bottom", fontsize=9, color="#222",
            path_effects=[pe.withStroke(linewidth=3, foreground="white")])


def show_map(
    png: bytes,
    title: str,
    bbox_degrees: list[float],
    *,
    legend: dict[str, str] | None = None,
    colorbar: dict | None = None,
    save_to: Path | None = None,
):
    """Displays one map PNG with a title, scale bar, and either a
    categorical `legend` ({label: color}) or a `colorbar`
    ({"ramp", "vmin", "vmax", "label", "ticks", "ticklabels"})."""
    img = plt.imread(io.BytesIO(png), format="png")
    fig, ax = plt.subplots(figsize=(10, 10 * img.shape[0] / img.shape[1] + 0.8), dpi=110)
    ax.imshow(img)
    ax.set_axis_off()
    ax.set_title(title, loc="left", fontsize=13, color="#222")
    _scale_bar(ax, bbox_degrees, img.shape[1])
    if legend:
        handles = [Patch(facecolor=c, edgecolor="#999", label=l) for l, c in legend.items()]
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(1.01, 1), frameon=False, fontsize=10)
    if colorbar:
        cmap = LinearSegmentedColormap.from_list("ramp", colorbar["ramp"])
        sm = plt.cm.ScalarMappable(norm=Normalize(colorbar["vmin"], colorbar["vmax"]), cmap=cmap)
        cb = fig.colorbar(sm, ax=ax, fraction=0.035, pad=0.02)
        cb.set_label(colorbar["label"], fontsize=10)
        if "ticks" in colorbar:
            cb.set_ticks(colorbar["ticks"], labels=colorbar.get("ticklabels"))
        cb.outline.set_visible(False)
    fig.tight_layout()
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, bbox_inches="tight")
    plt.show()
    return fig


def outcome_legend() -> dict[str, str]:
    legend = {OUTCOME_LABELS[k]: OUTCOME_COLORS[k] for k in (DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED)}
    legend["Water / outside study area"] = WATER_COLOR
    return legend


def timing_colorbar(year: int, first_doy: int, last_doy: int) -> dict:
    """Colorbar spec with month-start ticks inside the season."""
    ticks, labels = [], []
    for month in range(1, 13):
        doy = datetime.date(year, month, 1).timetuple().tm_yday
        if first_doy <= doy <= last_doy:
            ticks.append(doy)
            labels.append(datetime.date(year, month, 1).strftime("%b %-d"))
    return {"ramp": TIMING_RAMP, "vmin": first_doy, "vmax": last_doy, "label": "First date detected", "ticks": ticks, "ticklabels": labels}


def confidence_colorbar(threshold: float) -> dict:
    ticks = sorted({threshold, 0.75, 0.9, 1.0} if threshold < 0.75 else {threshold, 1.0})
    return {"ramp": CONFIDENCE_RAMP, "vmin": threshold, "vmax": 1, "label": "Probability of mapped change", "ticks": ticks, "ticklabels": [f"{t:.2f}" for t in ticks]}

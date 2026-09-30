"""Notebook building blocks: the standard map set and tables, plus the
"one pixel's journey" teaching figure. Thin wrappers over outputs/render,
so the Apostle Islands walkthrough and "try your own area" share one
implementation.
"""

from __future__ import annotations

from pathlib import Path

import ee

from . import outputs, render
from .outputs import DECREASE, INCREASE, UNCHANGED, StudyArea


def frame_for(geometry: ee.Geometry, pad_m: float = 500) -> tuple[ee.Geometry, list[float]]:
    """Map extent (geometry bounds + padding) and its [W, S, E, N] bbox."""
    frame = geometry.bounds(1).buffer(pad_m, 100).bounds(1)
    ring = frame.coordinates().get(0).getInfo()
    return frame, ring[0] + ring[2]


def season_label(controls) -> str:
    return f"{controls.monitoring_start:%b %-d} – {controls.monitoring_end:%b %-d}, {controls.monitoring_year}"


def _marked(layer, marker):
    return render.with_marker(layer, *marker) if marker else layer


def outcome_map(results, area: StudyArea, frame, bbox, title: str, token: str, save_to=None, enlarge_changes=True,
                dimensions=render.THUMB_DIMENSIONS, marker: tuple[float, float] | None = None):
    png = render.download_png(_marked(render.outcome_layer(results, area, frame, enlarge_changes=enlarge_changes), marker),
                              frame, token, dimensions)
    return render.show_map(png, title, bbox, legend=render.outcome_legend(), save_to=save_to)


def area_table(results, region: ee.Geometry) -> tuple[str, dict]:
    """Markdown table of km^2 per outcome (land only) and the raw dict."""
    areas = outputs.area_summary(results, region)
    analyzed = sum(v for k, v in areas.items() if "not analyzed" not in k)
    rows = [
        f"| {k} | {v:,.2f} | {100 * v / analyzed:.1f}% |" if "not analyzed" not in k else f"| {k} | {v:,.2f} | — |"
        for k, v in areas.items()
    ]
    return "| Outcome | Area (km²) | Share of analyzed land |\n|---|---:|---:|\n" + "\n".join(rows), areas


def confidence_map(results, area, frame, bbox, title, token, threshold, save_to=None, enlarge_changes=True):
    png = render.download_png(render.confidence_layer(results, area, frame, threshold, enlarge_changes=enlarge_changes), frame, token)
    return render.show_map(png, title, bbox, colorbar=render.confidence_colorbar(threshold), save_to=save_to)


def timing_map(results, area, frame, bbox, title, token, controls, save_to=None, enlarge_changes=True):
    png = render.download_png(
        render.timing_layer(results, area, frame, controls.first_doy, controls.last_doy, enlarge_changes=enlarge_changes), frame, token
    )
    return render.show_map(
        png, title, bbox,
        colorbar=render.timing_colorbar(controls.monitoring_year, controls.first_doy, controls.last_doy), save_to=save_to,
    )


def reference_pair(area, frame, bbox, name: str, token: str, controls, out_dir=None, dimensions=render.THUMB_DIMENSIONS,
                   window: tuple[str, str] | None = None, marker: tuple[float, float] | None = None):
    """Sentinel-2 false color median for the last baseline year ("before")
    and the monitoring year ("after"). `window` = (MM-DD, MM-DD); default is
    the later half of the season."""
    mid = controls.monitoring_start + (controls.monitoring_end - controls.monitoring_start) / 2
    first, last = window or (f"{mid:%m-%d}", controls.season_end)
    for year, label in [(controls.baseline_last_year, "before"), (controls.monitoring_year, "after")]:
        start, end = f"{year}-{first}", f"{year}-{last}"
        png = render.download_png(_marked(render.reference_layer(area, frame, start, end), marker), frame, token, dimensions)
        render.show_map(png, f"{name}: Sentinel-2, {start} to {end} ({label})", bbox,
                        save_to=(Path(out_dir) / f"reference_{label}.png") if out_dir else None)


def _scene_date(image_id: str) -> str:
    return f"{image_id[:4]}-{image_id[4:6]}-{image_id[6:8]}"


def scene_series(area, frame, bbox, name: str, token: str, scenes: list[tuple[str, str]], out_dir=None, dimensions=800,
                 marker: tuple[float, float] | None = None):
    """Single-date Sentinel-2 false color, one map per (label, scene id)."""
    for label, image_id in scenes:
        png = render.download_png(_marked(render.scene_layer(area, image_id), marker), frame, token, dimensions)
        date = _scene_date(image_id)
        render.show_map(png, f"{name}: Sentinel-2, {date} ({label})", bbox,
                        save_to=(Path(out_dir) / f"scene_{date}.png") if out_dir else None)


def scene_row(area, frame, bbox, token: str, scenes: list[tuple[str, str]], suptitle: str = "", vis=render.TRUE_COLOR,
              clip: bool = True, save_to=None, dimensions=900, marker: tuple[float, float] | None = None):
    """Single-date Sentinel-2 scenes side by side at one extent and one
    stretch: (title, scene id) pairs, e.g. [("2024", id), ("2025", id)].
    The acquisition date is shown under each panel."""
    pngs = [render.download_png(_marked(render.scene_layer(area, image_id, vis, clip), marker), frame, token, dimensions)
            for _, image_id in scenes]
    subtitles = [f"Sentinel-2, {_scene_date(image_id)}" for _, image_id in scenes]
    return render.show_map_row(pngs, [t for t, _ in scenes], subtitles, bbox, suptitle, save_to)


def detection_year_map(timing, area, frame, bbox, title: str, token: str, years: list[int], save_to=None,
                       marker: tuple[float, float] | None = None):
    """First season in which P(decrease) crossed the threshold (see
    outputs.combine_season_timing)."""
    png = render.download_png(_marked(render.detection_year_layer(timing, area, frame, years), marker), frame, token)
    return render.show_map(png, title, bbox, legend=render.detection_year_legend(years), save_to=save_to)


def detection_year_table(timing, region, years: list[int]) -> str:
    summ = outputs.decrease_year_summary(timing, region, years)
    analyzed = sum(summ.values())
    detected = analyzed - summ["none"]
    rows = [f"| {y} | {summ[str(y)]:.2f} | {100 * summ[str(y)] / analyzed:.1f}% | {100 * summ[str(y)] / detected:.1f}% |" for y in years]
    rows.append(f"| No decrease detected | {summ['none']:.2f} | {100 * summ['none'] / analyzed:.1f}% | — |")
    return ("| First detected | Area (km²) | Share of analyzed land | Share of detected decrease |\n"
            "|---|---:|---:|---:|\n" + "\n".join(rows))


def nbr_rgb_map(area, frame, bbox, title: str, token: str, years: list[int], window=("07-01", "09-15"), save_to=None,
                marker: tuple[float, float] | None = None):
    """Temporal NBR composite (R, G, B = years), one fixed stretch; returns
    the stretch used."""
    nbrs = [outputs.annual_nbr(area.geometry, y, window) for y in years]
    low, high = outputs.nbr_stretch(nbrs, area.geometry)
    png = render.download_png(_marked(render.nbr_rgb_layer(nbrs, area, frame, low, high), marker), frame, token)
    render.show_map(png, title, bbox, legend=render.nbr_rgb_legend(years), save_to=save_to, legend_below=True)
    return low, high

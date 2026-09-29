"""Notebook building blocks: the standard map set and tables, plus the
"one pixel's journey" teaching figure. Thin wrappers over outputs/render,
so the Apostle Islands walkthrough and "try your own area" share one
implementation.
"""

from __future__ import annotations

import csv
import datetime
from pathlib import Path

import ee
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from . import outputs, render
from .outputs import DECREASE, INCREASE, UNCHANGED, StudyArea


def frame_for(geometry: ee.Geometry, pad_m: float = 500) -> tuple[ee.Geometry, list[float]]:
    """Map extent (geometry bounds + padding) and its [W, S, E, N] bbox."""
    frame = geometry.bounds(1).buffer(pad_m, 100).bounds(1)
    ring = frame.coordinates().get(0).getInfo()
    return frame, ring[0] + ring[2]


def season_label(controls) -> str:
    return f"{controls.monitoring_start:%b %-d} – {controls.monitoring_end:%b %-d}, {controls.monitoring_year}"


def outcome_map(results, area: StudyArea, frame, bbox, title: str, token: str, save_to=None, enlarge_changes=True, dimensions=render.THUMB_DIMENSIONS):
    png = render.download_png(render.outcome_layer(results, area, frame, enlarge_changes=enlarge_changes), frame, token, dimensions)
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


def confidence_map(results, area, frame, bbox, title, token, threshold, save_to=None):
    png = render.download_png(render.confidence_layer(results, area, frame, threshold, enlarge_changes=True), frame, token)
    return render.show_map(png, title, bbox, colorbar=render.confidence_colorbar(threshold), save_to=save_to)


def timing_map(results, area, frame, bbox, title, token, controls, save_to=None):
    png = render.download_png(
        render.timing_layer(results, area, frame, controls.first_doy, controls.last_doy, enlarge_changes=True), frame, token
    )
    return render.show_map(
        png, title, bbox,
        colorbar=render.timing_colorbar(controls.monitoring_year, controls.first_doy, controls.last_doy), save_to=save_to,
    )


def reference_pair(area, frame, bbox, name: str, token: str, controls, out_dir=None, dimensions=render.THUMB_DIMENSIONS,
                   window: tuple[str, str] | None = None):
    """Sentinel-2 false color median for the last baseline year ("before")
    and the monitoring year ("after"). `window` = (MM-DD, MM-DD); default is
    the later half of the season."""
    mid = controls.monitoring_start + (controls.monitoring_end - controls.monitoring_start) / 2
    first, last = window or (f"{mid:%m-%d}", controls.season_end)
    for year, label in [(controls.baseline_last_year, "before"), (controls.monitoring_year, "after")]:
        start, end = f"{year}-{first}", f"{year}-{last}"
        png = render.download_png(render.reference_layer(area, frame, start, end), frame, token, dimensions)
        render.show_map(png, f"{name}: Sentinel-2, {start} to {end} ({label})", bbox,
                        save_to=(Path(out_dir) / f"reference_{label}.png") if out_dir else None)


def scene_series(area, frame, bbox, name: str, token: str, scenes: list[tuple[str, str]], out_dir=None, dimensions=800):
    """Single-date Sentinel-2 false color, one map per (label, scene id)."""
    for label, image_id in scenes:
        png = render.download_png(render.scene_layer(area, image_id), frame, token, dimensions)
        date = f"{image_id[:4]}-{image_id[4:6]}-{image_id[6:8]}"
        render.show_map(png, f"{name}: Sentinel-2, {date} ({label})", bbox,
                        save_to=(Path(out_dir) / f"scene_{date}.png") if out_dir else None)


def pixel_journey(csv_path: Path, event_start: datetime.date, event_end: datetime.date, threshold: float = 0.5, save_to=None):
    """Two panels for one pixel through a monitoring season: each clear
    observation's departure from normal (z-score), and the three outcome
    probabilities as BULC-D updates them. Reads a Milestone 1 replay CSV."""
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    dates = [datetime.date.fromisoformat(r["observation_date"]) for r in rows]
    valid = [(d, float(r["zscore"])) for d, r in zip(dates, rows) if r["valid"] == "True"]
    probs = {k: [float(r[f"{k}_probability"]) for r in rows] for k in ("decrease", "unchanged", "increase")}
    colors = {"decrease": render.OUTCOME_COLORS[DECREASE], "unchanged": "#8a887f", "increase": render.OUTCOME_COLORS[INCREASE]}

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6.2), dpi=110, sharex=True, gridspec_kw={"height_ratios": [1, 1.4]})
    for ax in (ax1, ax2):
        ax.axvspan(event_start, event_end + datetime.timedelta(days=1), color="#f3c9c1", lw=0)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="y", color="#e6e5e0", lw=0.8)
        ax.set_axisbelow(True)

    ax1.axhline(0, color="#999", lw=1)
    ax1.plot([d for d, _ in valid], [z for _, z in valid], "o", ms=6, color="#333", mec="white", mew=1.5)
    ax1.set_ylabel("Departure from normal\n(z-score)")
    ax1.set_title("One pixel at a real 2026 fire: evidence (top) and BULC-D's updated probabilities (bottom)", loc="left", fontsize=11)
    ax1.text(event_end + datetime.timedelta(days=3), ax1.get_ylim()[0] * 0.35, f"fire ({event_start:%b %-d}–{event_end:%-d})",
             fontsize=9, color="#9b3b2c")
    ax1.text(dates[-1] + datetime.timedelta(days=2), -10, "(capped at −10)", va="center", fontsize=8, color="#777")

    for k in ("decrease", "unchanged", "increase"):
        ax2.step(dates, probs[k], where="post", lw=2, color=colors[k], label=f"P({k})")
    ax2.legend(loc="center right", bbox_to_anchor=(1.0, 0.72), frameon=False, fontsize=9)
    ax2.axhline(threshold, color="#555", lw=1, ls="--")
    ax2.text(dates[0], threshold + 0.02, f"decision threshold ({threshold})", fontsize=8, color="#555")
    ax2.set_ylim(0, 1.02)
    ax2.set_ylabel("Probability")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    ax2.set_xlim(dates[0] - datetime.timedelta(days=3), dates[-1] + datetime.timedelta(days=14))
    fig.tight_layout()
    if save_to is not None:
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, bbox_inches="tight")
    plt.show()
    return fig

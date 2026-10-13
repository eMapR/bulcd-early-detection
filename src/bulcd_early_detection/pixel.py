"""Pixel history: one location's observations and BULC-D probabilities.

The data side of a future "click a pixel on the map" inspector (see
docs/PROJECT_STATE.md, "Future GUI requirements"): pixel_history() takes
any (lon, lat) and a BULC-D config and returns plain rows, so the same
call can serve a notebook figure or a GUI panel. plot_pixel_history()
is the notebook rendering of those rows.

Read-only interpretation of bulcd outputs: observed and expected (fitted)
NBR and z-scores from bulcd.inputs.organize_inputs(), probabilities from
bulcd.engine.run_bulcd(). Nothing here changes the detection.
"""

from __future__ import annotations

import bisect
import csv
import datetime
import math
from pathlib import Path

import ee
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from bulcd.config.schema import BULCDConfig
from bulcd.engine import run_bulcd
from bulcd.inputs import organize_inputs
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from .config import class_thresholds
from .render import OUTCOME_COLORS
from .outputs import DECREASE, INCREASE, UNCHANGED

CLASSES = ("decrease", "unchanged", "increase")
CLASS_COLORS = {"decrease": OUTCOME_COLORS[DECREASE], "unchanged": "#8a887f", "increase": OUTCOME_COLORS[INCREASE]}


def utm_crs_for(lon: float, lat: float) -> str:
    """UTM zone EPSG code for a coordinate (same rule as outputs.utm_crs)."""
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


def _table(collection: ee.ImageCollection, point: ee.Geometry, crs: str, scale: int = 30) -> dict[int, dict]:
    # Sample on the SAME 30 m UTM grid the products are exported on. Earth Engine's
    # default grid for computed images differs, and in patchy areas it can pick a
    # neighboring pixel (found 2026-09-30: ~10 m offset gave a different pixel).
    region = collection.getRegion(point, scale, crs).getInfo()
    header, rows = region[0], region[1:]
    t = header.index("time")
    return {row[t]: {h: v for h, v in zip(header, row)} for row in rows}


def supported_class(zscore: float | None, bin_cuts: list[float], matrix: list[list[float]]) -> str | None:
    """Which outcome one observation's evidence favors: its z-score bin's
    transition-matrix row, largest likelihood."""
    if zscore is None:
        return None
    row = matrix[bisect.bisect_right(bin_cuts, zscore)]
    return CLASSES[max(range(3), key=lambda i: row[i])]


def pixel_history(config: BULCDConfig, lon: float, lat: float) -> list[dict]:
    """One row per observation bin (bulcd timestamps bins at their END):
    date, observed and expected NBR, z-score (None where no clear
    observation), the class that evidence supports, and P(decrease /
    unchanged / increase) after the update. One monitoring run."""
    point = ee.Geometry.Point([lon, lat])
    crs = utm_crs_for(lon, lat)
    organized = organize_inputs(config)
    fitted = _table(organized.expectation_fitted_collection.select(["nbr", "fitted"]), point, crs)
    zscores = _table(organized.lof_zscore, point, crs)
    probs = _table(run_bulcd(config).probability_stack, point, crs)
    band = config.reduction.band
    matrix = config.bulc_advanced_params.custom_transition_matrix
    rows = []
    for t in sorted(probs):
        z = zscores.get(t, {}).get("zscore")
        f = fitted.get(t, {})
        rows.append({
            "date": datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).date(),
            "observed": f.get(band) if z is not None else None,
            "expected": f.get("fitted"),
            "zscore": z,
            "supports": supported_class(z, config.bin_cuts, matrix),
            **{c: probs[t][c] for c in CLASSES},
        })
    return rows


def first_crossing(rows: list[dict], threshold: float, cls: str = "decrease") -> datetime.date | None:
    return next((r["date"] for r in rows if r[cls] is not None and r[cls] > threshold), None)


def detection_episodes(rows: list[dict], threshold: float, cls: str = "decrease") -> list[dict]:
    """Detection episodes in one run's rows: an episode starts at a row where
    P(cls) > threshold after one at or below it (the run starts below), and
    ends at the next row at or below it ("end" None = still above at the last
    row). Rows without an observation carry the previous probability, so they
    never start or end one. No smoothing or minimum duration. Row form of
    outputs.decrease_episode_bands(); gee/inspector.js detectionEpisodes()."""
    episodes, above = [], False
    for r in rows:
        now = r[cls] is not None and r[cls] > threshold
        if now and not above:
            episodes.append({"start": r["date"], "end": None})
        elif above and not now:
            episodes[-1]["end"] = r["date"]
        above = now
    return episodes


def episode_notes(rows: list[dict], threshold: float, cls: str = "decrease") -> list[str]:
    """One sentence on the detection episodes (detection_episodes()): count,
    each episode's dates, and the first and last detection."""
    eps = detection_episodes(rows, threshold, cls)
    if not eps:
        return []
    spans = "; ".join(f"{e['start']} to " + (f"{e['end']} (ended)" if e["end"] else "season end (still above)")
                      for e in eps)
    return [f"{cls} detection episodes above {threshold}: {len(eps)} ({spans}); first detection {eps[0]['start']}, "
            f"last detection {eps[-1]['start']}"]


def crossing_notes(rows: list[dict], threshold: float, increase_threshold: float | None = None) -> list[str]:
    """One sentence per change class that crossed its threshold (decrease:
    `threshold`; increase: `increase_threshold`, default `threshold`), saying
    whether it finished the season above it (only that counts)."""
    t = class_thresholds(threshold, increase_threshold)
    notes = []
    for cls in ("decrease", "increase"):
        crossed = first_crossing(rows, t[cls], cls)
        if not crossed:
            continue
        finished = rows[-1][cls] > t[cls]
        notes.append(f"{cls} first crossed its threshold ({t[cls]}) on {crossed}, " +
                     (f"finished the season as {cls} (counts as detected)" if finished
                      else "finished below its threshold (does not count)"))
    if not notes:
        notes.append("never crossed a threshold (" + (str(t["decrease"]) if t["decrease"] == t["increase"] else
                                                      f"decrease {t['decrease']}, increase {t['increase']}") + ")")
    return notes


def history_from_replay_csv(path: Path, bin_cuts: list[float], matrix: list[list[float]]) -> list[dict]:
    """Rows in pixel_history() form from a Milestone 1 replay CSV
    (experiments/output/*.csv) - no observed/expected values there."""
    with open(path) as f:
        out = []
        for r in csv.DictReader(f):
            z = float(r["zscore"]) if r["valid"] == "True" and r["zscore"] else None
            out.append({
                "date": datetime.date.fromisoformat(r["observation_date"]), "observed": None, "expected": None,
                "zscore": z, "supports": supported_class(z, bin_cuts, matrix),
                **{c: float(r[f"{c}_probability"]) for c in CLASSES},
            })
    return out


def plot_pixel_history(seasons: dict[str, list[dict]], threshold: float = 0.5, title: str = "",
                       classes: tuple[str, ...] = ("decrease",), show_nbr: bool = True, save_to=None,
                       increase_threshold: float | None = None):
    """One column per monitoring season (label -> rows), sharing y-axes.

    Laid out like the legacy GUI's "Target Year vs. Fit of Expectation" and
    "Probability Through Time" charts. Top: observed NBR (a line broken where
    there is no clear observation) against the expected seasonal fit, if
    available, else the z-score; each observation dot colored by the class its
    evidence favors. Bottom: probability of `classes` (decrease by default) at
    each observation's own date - unlike the legacy chart, which plots each
    posterior one step late - with each change class's threshold (decrease:
    `threshold`; increase: `increase_threshold`, default `threshold`) and its
    first crossing marked.
    """
    t = class_thresholds(threshold, increase_threshold)
    have_nbr = show_nbr and any(r["observed"] is not None for rows in seasons.values() for r in rows)
    change = [c for c in classes if c != "unchanged"]
    # One dotted grey line for a shared threshold; otherwise one per change class, in its color.
    if len({t[c] for c in change}) <= 1:
        threshold_lines = [(t[change[0]] if change else threshold, "#555")]
        threshold_labels = [f"decision threshold ({threshold_lines[0][0]})"]
    else:
        threshold_lines = [(t[c], CLASS_COLORS[c]) for c in change]
        threshold_labels = [f"{c} threshold ({t[c]})" for c in change]
    n = len(seasons)
    fig, axes = plt.subplots(2, n, figsize=(max(4.2 * n + 1.2, 8.5), 6.2), dpi=110, sharey="row", squeeze=False,
                             gridspec_kw={"height_ratios": [1, 1.2]})
    for col, (label, rows) in enumerate(seasons.items()):
        top, bot = axes[0][col], axes[1][col]
        dates = [r["date"] for r in rows]
        obs = [r for r in rows if r["zscore"] is not None]
        key = "observed" if have_nbr else "zscore"
        if have_nbr:
            top.plot(dates, [r["expected"] for r in rows], color="#555", lw=1.8)
        else:
            top.axhline(0, color="#999", lw=1)
        top.plot(dates, [math.nan if r["zscore"] is None else r[key] for r in rows], color="#b9b7ae", lw=1.2, zorder=2)
        top.scatter([r["date"] for r in obs], [r[key] for r in obs], s=30, c=[CLASS_COLORS[r["supports"]] for r in obs],
                    edgecolors="white", linewidths=1.1, zorder=3)
        # Shade every period above the threshold: a first crossing need not stay above it.
        for cls in change:
            vals = [r[cls] for r in rows]
            bot.fill_between(dates, t[cls], vals, where=[v is not None and v > t[cls] for v in vals], step="post",
                             color=CLASS_COLORS[cls], alpha=0.15, lw=0)
        for cls in classes:
            bot.step(dates, [r[cls] for r in rows], where="post", lw=2, color=CLASS_COLORS[cls])
            bot.plot(dates, [r[cls] for r in rows], ls="", marker="o", ms=2.5, color=CLASS_COLORS[cls])
        for value, color in threshold_lines:
            bot.axhline(value, color=color, lw=1, ls=":")
        notes = []
        for cls in change:
            crossed = first_crossing(rows, t[cls], cls)
            if crossed:
                bot.axvline(crossed, color=CLASS_COLORS[cls], lw=1)
            eps = detection_episodes(rows, t[cls], cls)
            if len(eps) > 1:   # last detection: start of the most recent episode
                bot.axvline(eps[-1]["start"], color=CLASS_COLORS[cls], lw=1, ls="--")
            notes.append((f"{cls} first crossed {crossed:%Y-%m-%d}" if crossed else f"{cls} never > {t[cls]}") +
                         (f", last {eps[-1]['start']:%Y-%m-%d} ({len(eps)} episodes)" if len(eps) > 1 else ""))
        bot.set_title(" · ".join(notes), loc="left", fontsize=9, color="#444")
        top.set_title(label, fontsize=11)
        bot.set_ylim(0, 1.02)
        for ax in (top, bot):
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.grid(axis="y", color="#e6e5e0", lw=0.8)
            ax.set_axisbelow(True)
        bot.xaxis.set_major_locator(mdates.MonthLocator())
        bot.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        top.tick_params(labelbottom=False)
    axes[0][0].set_ylabel("NBR" if have_nbr else "Departure from normal\n(z-score)")
    axes[1][0].set_ylabel("Probability")
    handles = [Line2D([], [], marker="o", ls="", color=CLASS_COLORS[c], mec="white", ms=7, label=f"observation favors {c}") for c in CLASSES]
    if have_nbr:
        handles.append(Line2D([], [], color="#555", lw=1.8, label="expected (baseline fit)"))
        handles.append(Line2D([], [], color="#b9b7ae", lw=1.2, label="observed NBR"))
    handles += [Line2D([], [], color=CLASS_COLORS[c], lw=2, marker="o", ms=3, label=f"P({c})") for c in classes]
    handles += [Line2D([], [], color=color, ls=":", label=label) for (_, color), label in zip(threshold_lines, threshold_labels)]
    handles += [Patch(facecolor=CLASS_COLORS[c], alpha=0.15, label=f"P({c}) above its threshold") for c in change]
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 4), frameon=False, fontsize=9)
    if title:
        fig.suptitle(title, x=0.01, ha="left", fontsize=12)
    fig.tight_layout(rect=(0, 0.1 + 0.03 * (len(handles) > 8), 1, 0.97))
    if save_to is not None:
        Path(save_to).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, bbox_inches="tight")
    plt.show()
    return fig


def representative_pixel(mask: ee.Image, region: ee.Geometry, crs: str, scale: int = 30) -> tuple[float, float]:
    """A rule-based (not hand-picked) example location: the pixel of `mask`
    nearest the center of mask's largest connected patch inside `region`.
    Returns (lon, lat)."""
    m = mask.selfMask().rename("m")
    patches = m.reduceToVectors(geometry=region, crs=crs, scale=scale, geometryType="polygon",
                                eightConnected=False, maxPixels=1e10)
    largest = ee.Feature(patches.map(lambda f: f.set("a", f.geometry().area(1))).sort("a", False).first())
    center = largest.geometry().centroid(1)
    pts = m.sample(largest.geometry(), scale, projection=crs, geometries=True)
    best = ee.Feature(pts.map(lambda f: f.set("d", f.geometry().distance(center, 1))).sort("d").first())
    lon, lat = best.geometry().coordinates().getInfo()
    return lon, lat

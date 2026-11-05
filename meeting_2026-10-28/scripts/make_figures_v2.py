"""Revised meeting figures, organized by research question (read-only; uses existing results only).

    python meeting_2026-10-28/scripts/make_figures_v2.py

Writes figures_v2/*.png (2666 x 1500) and data/figures_v2_numbers.json. The original figures/ are untouched.

All BULC-D results here are the FULL-YEAR runs (expectation and monitoring DOY 1-362; 2026 = year to date
through Oct 27, 2026): data/fullyear/{A26,B26,C26,A25,A24}.npz from expectation_compare_fullyear.py.
Independent checks (never used by BULC-D):
  - Hansen Global Forest Change v1.13 loss year (through 2025)       data/reference.npz
  - Sentinel-2 NBR change 2025 -> 2026 (late season and monthly)    data/reference.npz, data/monthly_s2.npz
These are other satellite products, not field-verified disturbance dates.
"""
import datetime as dt
import json

import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from make_figures import (DATA, DEC, GRID, HERE, INK, INK2, LAND, MUTED, PX_KM2, WATER, base_map, figure, land,
                          north_arrow, overlay, pilot, scale_bar, swatch, tile_lines)

OUT = HERE / "figures_v2"
OUT.mkdir(exist_ok=True)
CFG = {"A": "#6250d6", "B": "#1baf7a", "C": "#eb6834"}            # validated all-pairs (dataviz)
CFG_NAME = {"A": "A: 2018–2023", "B": "B: 2024–2025", "C": "C: 2018–2025"}
OLD, Y25, Y26, NOREC = "#2a78d6", "#eda100", "#e34948", "#52514e"  # validated all-pairs (dataviz) + neutral
SOFT = "#f6f5f2"

F = {k: np.load(DATA / "fullyear" / f"{k}.npz") for k in ("A26", "B26", "C26", "A25", "A24")}
R = np.load(DATA / "reference.npz")
M = np.load(DATA / "monthly_s2.npz")
EX = json.loads((DATA / "examples.json").read_text())
o = {k: np.where(land, F[k + "26"]["outcome"], -1).astype(int) for k in "ABC"}
o24, o25 = (np.where(land, F[k]["outcome"], -1) for k in ("A24", "A25"))
dyear = np.where(o24 == 0, 2024, np.where(o25 == 0, 2025, np.where(o["A"] == 0, 2026, 0)))  # BULC-D, config A
loss = R["hansen_lossyear"].astype(int)
dl = R["late2026_nbr"] - R["late2025_nbr"]
older = land & (loss >= 18) & (loss <= 25)
likely26 = land & (dl < -0.2) & ~older                     # independent "likely 2026 disturbance"
stable = land & (loss == 0) & (np.abs(dl) < 0.05)
HANSEN_GROUPS = [("2018–2021", (loss >= 18) & (loss <= 21)), ("2022–2023", (loss >= 22) & (loss <= 23)),
                 ("2024", loss == 24), ("2025", loss == 25)]


def km2(m):
    return float(m.sum() * PX_KM2)


def pct(m, within):
    within = within & land
    return float(100 * (m & within).sum() / max(1, within.sum()))


def save(fig, name):
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)
    print("wrote", OUT / name)


def header(fig, question, title, subtitle):
    fig.text(0.04, 0.965, question, fontsize=13, color=MUTED, va="top", fontweight="bold")
    fig.text(0.04, 0.93, title, fontsize=23, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.865, subtitle, fontsize=14, color=INK2, va="top", linespacing=1.35)


def footer(fig, text, y=0.05):
    fig.text(0.04, y, text, fontsize=10, color=MUTED, va="top", linespacing=1.4)


def box(fig, x, y, w, h, fc=SOFT, ec=GRID, ls="-"):
    fig.patches.append(mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006", transform=fig.transFigure,
                                               fc=fc, ec=ec, ls=ls))


def bar_style(ax, xmax=None):
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)


# ---------------------------------------------------------------- numbers
# Month-level independent change date for likely-2026 pixels: first month whose S2 NBR is >= 0.25 below
# the same month of 2025 and stays >= 0.2 below the next month (or in the late-season composite).
d_month = np.stack([M[f"nbr_2026_{m:02d}"] - M[f"nbr_2025_{m:02d}"] for m in range(1, 11)])
hit = (d_month < -0.25) & np.concatenate([d_month[1:] < -0.2, (dl < -0.2)[None]], 0)
s2_month = np.where(hit.any(0), hit.argmax(0) + 1, 0)


def timing(k):
    fd = F[k + "26"]["first_dec"]
    bm = np.where(fd > 0, np.minimum((fd % 1000 - 1) // 30.4 + 1, 12), 0).astype(int)
    m = likely26 & (o[k] == 0) & (s2_month > 0) & (bm > 0) & (fd // 1000 == 2026)
    d = bm[m] - s2_month[m]
    return {"n_km2": km2(m), "early2": float(100 * np.mean(d <= -2)), "early1": float(100 * np.mean(d == -1)),
            "same": float(100 * np.mean(d == 0)), "late1": float(100 * np.mean(d == 1)),
            "late2": float(100 * np.mean(d >= 2))}


def composition(k):
    dec = o[k] == 0
    return {"older_2018_2024": km2(dec & land & (loss >= 18) & (loss <= 24)), "older_2025": km2(dec & (loss == 25)),
            "likely_2026": km2(dec & likely26), "no_record": km2(dec & ~older & ~likely26)}


def flagged(k, m):
    return pct(o[k] == 0, m)


N_ = {
    "decrease_km2": {k: km2(o[k] == 0) for k in "ABC"},
    "exp_obs": {k: float(np.median(F[k + "26"]["n_exp"][land])) for k in "ABC"},
    "mon_bins_2026": float(np.median(F["A26"]["n_mon"][land])),
    "flagged_by_hansen_group": {k: {g: flagged(k, m) for g, m in HANSEN_GROUPS} for k in "ABC"},
    "hansen_group_km2": {g: km2(m & land) for g, m in HANSEN_GROUPS},
    "flagged_older_2022_2024": {k: flagged(k, (loss >= 22) & (loss <= 24)) for k in "ABC"},
    "increase_on_2018_2023_loss": {k: pct(o[k] == 2, (loss >= 18) & (loss <= 23)) for k in "ABC"},
    "likely26_km2": km2(likely26),
    "likely26_detected": {k: pct(o[k] == 0, likely26) for k in "ABC"},
    "stable_flagged": {k: pct(o[k] == 0, stable) for k in "ABC"},
    "composition_km2": {k: composition(k) for k in "ABC"},
    "detection_year_km2": {y: km2((o["A"] == 0) & (dyear == y)) for y in (2024, 2025, 2026)},
    "hansen2024_first_detected": {y: pct(dyear == y, loss == 24) for y in (2024, 2025, 2026, 0)},
    "hansen2025_first_detected": {y: pct(dyear == y, loss == 25) for y in (2024, 2025, 2026, 0)},
    "first2026_no_earlier_hansen": pct(~older, (o["A"] == 0) & (dyear == 2026)),
    "timing_vs_s2_month": {k: timing(k) for k in "ABC"},
    "spring_false_episodes_km2": {},
}
for k in "ABC":
    d = F[k + "26"]
    sp = (d["episodes"] > 0) & (o[k] != 0) & (d["first_dec"] > 0) & (d["first_dec"] % 1000 < 152)
    N_["spring_false_episodes_km2"][k] = km2(sp & land)
(DATA / "figures_v2_numbers.json").write_text(json.dumps(N_, indent=1, default=float))
print(json.dumps(N_, indent=1, default=float))
FOOT_RUN = ("Oregon Coast Range pilot, 400 km², 30 m. BULC-D on Landsat 8/9 NBR; full-year expectation and "
            "monitoring; 2026 = year to date (Jan 1–Oct 27). No forest mask.")


# ---------------------------------------------------------------- example-pixel helpers
def series(ex):
    past = [(dt.datetime.utcfromtimestamp(p["t"] / 1000).date(), p["nbr"]) for p in ex["past"]]
    mon = {k: [(dt.date.fromisoformat(r["date"]), r) for r in ex["monitoring"][k]] for k in "AB"}
    now = [(d, r["observed"]) for d, r in mon["A"] if r["observed"] is not None]
    return past, mon, now


def expected_curve(mon_rows, years):
    pts = [(d, r["expected"]) for d, r in mon_rows if r["expected"] is not None]
    out = []
    for y in years:
        out.append([(d.replace(year=y), v) for d, v in pts])
    return out


def timeline_axes(ax):
    ax.set_xlim(dt.date(2018, 1, 1), dt.date(2027, 1, 1))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylim(-0.4, 1.0)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for lab in ax.get_xticklabels():
        lab.set_horizontalalignment("left")


# ---------------------------------------------------------------- 01 the problem
def fig01_problem():
    ex = EX["gap2024"]
    past, mon, now = series(ex)
    fig = figure()
    header(fig, "THE PROBLEM", "A harvest from 2024 still looks like a new disturbance in 2026",
           "BULC-D compares each new satellite observation with what is \"normal\" for that place and time of year. "
           "If \"normal\" is learned\nfrom years before a disturbance, the disturbance keeps standing out in every "
           "later year.")
    ax = fig.add_axes([0.085, 0.2, 0.6, 0.5])
    ax.axvspan(dt.date(2018, 1, 1), dt.date(2024, 1, 1), color=CFG["A"], alpha=0.08, lw=0)
    ax.axvspan(dt.date(2024, 1, 1), dt.date(2026, 1, 1), fc="none", ec=MUTED, hatch="///", alpha=0.35, lw=0)
    ax.axvspan(dt.date(2026, 1, 1), dt.date(2027, 1, 1), color=Y26, alpha=0.08, lw=0)
    for curve in expected_curve(mon["A"], range(2018, 2024)) + expected_curve(mon["A"], [2026]):
        ax.plot(*zip(*curve), color=CFG["A"], lw=2.2)
    ax.scatter(*zip(*past), s=14, color=MUTED, zorder=3)
    ax.scatter(*zip(*now), s=26, color=INK, zorder=3)
    timeline_axes(ax)
    ax.set_ylabel("Vegetation index (NBR)", fontsize=13)
    ax.text(dt.date(2021, 1, 1), 0.93, "\"Normal\" learned from 2018–2023", ha="center", va="top", fontsize=12.5,
            color=CFG["A"], fontweight="bold")
    ax.text(dt.date(2025, 1, 1), 0.93, "Gap: not used", ha="center", va="top", fontsize=12.5, color=INK2)
    ax.text(dt.date(2026, 7, 1), 0.93, "2026", ha="center", va="top", fontsize=12.5, color=Y26, fontweight="bold")
    drop = next(d for d, v in past if d.year == 2024 and v < 0.4)
    ax.annotate(f"Harvest\n(independent record:\nHansen, {ex['hansen_lossyear']})", xy=(drop, 0.25),
                xytext=(dt.date(2022, 8, 1), -0.25), fontsize=11.5, color=INK, ha="center",
                arrowprops=dict(arrowstyle="->", color=INK2, lw=1.3))
    ax.annotate("2026 observations sit far\nbelow \"normal\" → BULC-D:\n\"decrease\" in 2026", xy=(dt.date(2026, 4, 15), 0.15),
                xytext=(dt.date(2025, 6, 15), 0.5), fontsize=11.5, color=INK, ha="center",
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=2),
                arrowprops=dict(arrowstyle="->", color=INK2, lw=1.3))
    hs = [plt.Line2D([], [], color=CFG["A"], lw=2.2), plt.Line2D([], [], ls="", marker="o", color=MUTED, ms=5),
          plt.Line2D([], [], ls="", marker="o", color=INK, ms=6)]
    ax.legend(hs, ["\"normal\" (BULC-D's expectation)", "observations 2018–2025", "observations 2026"],
              loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=11.5, frameon=False)

    box(fig, 0.72, 0.2, 0.25, 0.5)
    fig.text(0.735, 0.68, "Why this matters", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.735, 0.635, "We want early warning of\ndisturbances happening in 2026.\n\nBut with 2018–2023 as "
             "\"normal\",\nthis 2024 harvest is still\nflagged in 2026, and would be\nflagged again in 2027, "
             "2028 …\n\nIn the pilot, most of the area\nflagged in 2026 is older change\nlike this.",
             fontsize=12.5, color=INK2, va="top", linespacing=1.35)
    footer(fig, f"One pilot pixel ({ex['lon']:.5f}, {ex['lat']:.5f}), the center of a uniform patch. Points: Landsat 8/9 NBR "
                "in 4-day bins. Harvest year from Hansen Global Forest Change\n(an independent satellite product, not "
                "field-verified).\n" + FOOT_RUN, y=0.11)
    save(fig, "01_problem_old_disturbance_looks_new.png")


# ---------------------------------------------------------------- 02 how we tested
def fig02_method():
    fig = figure()
    header(fig, "HOW WE TESTED IT", "Same region, same 2026 data, three versions of \"normal\"",
           "We ran BULC-D three times on the same 400 km² area, changing only the years it learns \"normal\" from "
           "(the expectation period).")
    ax = fig.add_axes([0.13, 0.5, 0.5, 0.25])
    years = list(range(2018, 2027))
    spans = {"A": (2018, 2023), "B": (2024, 2025), "C": (2018, 2025)}
    for i, k in enumerate("ABC"):
        y = 2 - i
        a, b = spans[k]
        for yr in years:
            if a <= yr <= b:
                ax.add_patch(mpatches.Rectangle((yr, y - 0.35), 0.96, 0.7, color=CFG[k]))
            elif yr < 2026 and yr > b:
                ax.add_patch(mpatches.Rectangle((yr, y - 0.35), 0.96, 0.7, fc="white", ec=MUTED, hatch="///", lw=0.8))
            elif yr == 2026:
                ax.add_patch(mpatches.Rectangle((yr, y - 0.35), 0.96, 0.7, fc="white", ec=Y26, lw=2.5))
        ax.text(2017.85, y, CFG_NAME[k], ha="right", va="center", fontsize=14, fontweight="bold", color=INK)
    for yr in years:
        ax.text(yr + 0.48, 2.65, str(yr), ha="center", va="bottom", fontsize=12, color=INK2)
    ax.set_xlim(2018, 2027)
    ax.set_ylim(-0.5, 3.1)
    ax.axis("off")
    swatch(fig, 0.13, 0.45, MUTED, "", alpha=0)
    fig.patches.append(mpatches.Rectangle((0.13, 0.439), 0.012, 0.022, transform=fig.transFigure, fc=CFG["A"]))
    fig.text(0.147, 0.45, "expectation period (\"normal\")", fontsize=12, color=INK, va="center")
    fig.patches.append(mpatches.Rectangle((0.37, 0.439), 0.012, 0.022, transform=fig.transFigure, fc="white",
                                          ec=MUTED, hatch="///"))
    fig.text(0.387, 0.45, "gap (not used)", fontsize=12, color=INK, va="center")
    fig.patches.append(mpatches.Rectangle((0.5, 0.439), 0.012, 0.022, transform=fig.transFigure, fc="white", ec=Y26,
                                          lw=2))
    fig.text(0.517, 0.45, "2026 (Jan 1–Oct 27)", fontsize=12, color=INK, va="center")
    fig.text(0.04, 0.39, "Everything else is identical: Landsat 8/9, the NBR vegetation index,\nfull-year "
             "observations, the same thresholds. A is the setting used so far;\nB uses only the most recent years; "
             "C uses all years before 2026.", fontsize=12.5, color=INK2, va="top", linespacing=1.4)
    box(fig, 0.04, 0.12, 0.59, 0.135, fc="white", ec=MUTED)
    fig.text(0.055, 0.24, "Independent checks (never used by BULC-D)", fontsize=12.5, fontweight="bold", color=INK,
             va="top")
    fig.text(0.055, 0.205, "• Hansen Global Forest Change: the year forest loss was recorded, through 2025\n"
             "• Sentinel-2, a different satellite: how much NBR dropped from 2025 to 2026\n"
             "Both are satellite estimates, not field-verified disturbance dates.", fontsize=11.5, color=INK2,
             va="top", linespacing=1.35)

    box(fig, 0.67, 0.12, 0.3, 0.64)
    fig.text(0.685, 0.74, "Terms used in this deck", fontsize=14, fontweight="bold", color=INK, va="top")
    terms = [("Expectation period", "the years BULC-D learns \"normal\" from"),
             ("Decrease", "BULC-D is ≥ 65% confident the vegetation is\nbelow normal at the latest observation"),
             ("Detection date", "when BULC-D first crossed that 65% line\n(the algorithm's date)"),
             ("Disturbance date", "when the disturbance happened, from\nindependent data (below)"),
             ("Gap", "years between the expectation period\nand 2026, used by neither")]
    y = 0.69
    for t, d in terms:
        fig.text(0.685, y, t, fontsize=12, fontweight="bold", color=INK, va="top")
        fig.text(0.685, y - 0.032, d, fontsize=11.5, color=INK2, va="top", linespacing=1.3)
        y -= 0.032 + 0.032 * (d.count("\n") + 1) + 0.03
    footer(fig, FOOT_RUN + "\nThe 2026 year-to-date runs end at the latest available image; November–December "
           "observations could still change the 2026 result.", y=0.1)
    save(fig, "02_how_we_tested.png")


# ---------------------------------------------------------------- 03 Q1 processing
def fig03_processing():
    fig = figure()
    header(fig, "Q1 · CAN BULC-D PROCESS LARGE REGIONS EFFICIENTLY AND CONSISTENTLY?",
           "A 400 km² pilot ran in minutes and gave identical results when rerun",
           "The area is split into 10 × 10 km tiles that run independently in Google Earth Engine.")
    ax = fig.add_axes([0.04, 0.17, 0.355, 0.355 * 13.333 / 7.5])
    base_map(ax, image=True)
    overlay(ax, o["A"] == 0, DEC)
    tile_lines(ax, labels=False)
    scale_bar(ax)
    north_arrow(ax)
    fig.text(0.04, 0.155, "Red: 2026 decrease (expectation A). Dashed lines: the four\n10 km tiles. "
             "Background: Sentinel-2, summer 2026.", fontsize=11, color=INK2, va="top", linespacing=1.3)
    stats = [("400 km²", "processed as 4 tiles, 12 tile-seasons\nexported as Earth Engine products"),
             ("1–4 min", "per tile per season as a batch export;\nall 16 exports succeeded"),
             ("100%", "of 443,427 pixels identical when the\nexported product was recomputed"),
             ("< 10 min", "for all 5 full-year runs in this deck\n(400 km² each, computed on request)")]
    for i, (big, txt) in enumerate(stats):
        x, y = 0.45 + (i % 2) * 0.265, 0.78 - (i // 2) * 0.235
        box(fig, x, y - 0.19, 0.25, 0.2)
        fig.text(x + 0.012, y, big, fontsize=30, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.012, y - 0.085, txt, fontsize=12, color=INK2, va="top", linespacing=1.3)
    fig.text(0.45, 0.31, "What this does not show yet", fontsize=13.5, fontweight="bold", color=INK, va="top")
    fig.text(0.45, 0.275, "• Regions larger than 400 km² (cost per 100 km² was steady across 1–16 tiles in\n"
             "  benchmarks, but a full ecoregion run has not been done).\n"
             "• The full regional validation run on islay: results not retrieved for this meeting.\n"
             "• The exported products use Jun–Sep monitoring; the full-year runs were not exported.",
             fontsize=11.5, color=INK2, va="top", linespacing=1.35)
    footer(fig, "Identical results: live recomputation of the exported 2026 pilot product (Jun–Sep settings) matched on "
                "every land pixel; a 1,600-pixel spot check across\ntile seams also matched for 2024–2026. "
                "Benchmarks 2026-10-26: about 110–200 Earth Engine compute-seconds per 100 km² (Earth Engine's unit of "
                "processing cost).", y=0.08)
    save(fig, "03_Q1_processing.png")


# ---------------------------------------------------------------- 04 Q2 new vs older
def fig04_new_vs_old():
    fig = figure()
    total = N_["decrease_km2"]["A"]
    dy = N_["detection_year_km2"]
    header(fig, "Q2 · CAN BULC-D DISTINGUISH NEW DISTURBANCES FROM OLDER ONES?",
           f"Yes, with a detection year: only {100 * dy[2026] / total:.0f}% of the 2026 decrease is new",
           "Running BULC-D for 2024, 2025 and 2026 gives each 2026 decrease pixel a detection year: the first year "
           "BULC-D flagged it.")
    ax = fig.add_axes([0.04, 0.1, 0.38, 0.38 * 13.333 / 7.5])
    base_map(ax)
    cols = {2024: OLD, 2025: Y25, 2026: Y26}
    for y in (2024, 2025, 2026):
        overlay(ax, (o["A"] == 0) & (dyear == y), cols[y])
    scale_bar(ax)
    north_arrow(ax)
    ax.set_title("2026 decrease (expectation A), by BULC-D detection year", loc="left", fontsize=13, color=INK, pad=6)
    fig.text(0.47, 0.75, f"{total:.1f} km² flagged as decrease in 2026", fontsize=15, color=INK2, va="top")
    labels = {2024: "first detected 2024 or earlier", 2025: "first detected 2025", 2026: "first detected 2026 (new)"}
    y = 0.69
    for yr in (2024, 2025, 2026):
        fig.patches.append(mpatches.Rectangle((0.47, y - 0.05), 0.022, 0.045, transform=fig.transFigure, fc=cols[yr]))
        fig.text(0.5, y, f"{100 * dy[yr] / total:.0f}%", fontsize=28, fontweight="bold", color=INK, va="top")
        fig.text(0.575, y - 0.002, labels[yr], fontsize=14, color=INK, va="top")
        fig.text(0.575, y - 0.037, f"{dy[yr]:.1f} km²", fontsize=12, color=INK2, va="top")
        y -= 0.095
    box(fig, 0.47, 0.1, 0.5, 0.29)
    fig.text(0.485, 0.37, "Checked against independent records (Hansen forest loss)", fontsize=13.5,
             fontweight="bold", color=INK, va="top")
    h24, h25 = N_["hansen2024_first_detected"], N_["hansen2025_first_detected"]
    fig.text(0.485, 0.325,
             f"• Land Hansen records as disturbed in 2024: BULC-D first detected {h24[2024]:.0f}% in 2024.\n"
             f"• Land Hansen records as disturbed in 2025: BULC-D first detected {h25[2025]:.0f}% in 2025.\n"
             f"• Of BULC-D's new 2026 detections, {N_['first2026_no_earlier_hansen']:.0f}% have no earlier Hansen loss.\n\n"
             "\"2024 or earlier\" includes older change: 2024 is the first year we ran.\n"
             "Detection year is BULC-D's date, not a verified disturbance date.",
             fontsize=12, color=INK2, va="top", linespacing=1.4)
    footer(fig, "Detection year: earliest of the full-year runs for 2024, 2025 and 2026 (each against the 2018–2023 "
                "expectation) that ended as decrease.\nHansen Global Forest Change v1.13 (through 2025). " + FOOT_RUN,
           y=0.065)
    save(fig, "04_Q2_new_vs_older.png")


# ---------------------------------------------------------------- 05 Q3 why (example pixels)
def fig05_examples():
    fig = figure()
    header(fig, "Q3 · HOW DOES THE EXPECTATION PERIOD AFFECT DETECTION?",
           "A disturbance stops being flagged once \"normal\" has absorbed it",
           "Three real pixels, each judged against two versions of \"normal\": A (2018–2023) and B (2024–2025).")
    cases = [("gap2024", "Harvested in 2024", "B's \"normal\" already\nincludes the harvested\nstand: 2026 looks normal"),
             ("late2025", "Harvested in 2025", "B's \"normal\" is mostly\npre-harvest (2024, early\n2025): 2026 stands out"),
             ("new2026", "New in 2026", "Both versions of\n\"normal\" are intact\nforest: both flag it")]
    verdict = {0: "decrease", 1: "no change", 2: "increase"}
    tops = [0.76, 0.53, 0.30]
    for i, (case, name, why) in enumerate(cases):
        ex = EX[case]
        past, mon, now = series(ex)
        top = tops[i]
        ax = fig.add_axes([0.235, top - 0.175, 0.57, 0.175])
        ax.axvspan(dt.date(2026, 1, 1), dt.date(2027, 1, 1), color=Y26, alpha=0.07, lw=0)
        ax.scatter(*zip(*past), s=9, color=MUTED, zorder=3)
        ax.scatter(*zip(*now), s=16, color=INK, zorder=3)
        for k, years in (("A", range(2018, 2024)), ("B", (2024, 2025))):
            for curve in expected_curve(mon[k], years) + expected_curve(mon[k], [2026]):
                ax.plot(*zip(*curve), color=CFG[k], lw=2, zorder=4)
        timeline_axes(ax)
        ax.set_yticks([0, 0.5])
        if i < 2:
            ax.set_xticklabels([])
        if i == 1:
            ax.set_ylabel("NBR", fontsize=12)
        fig.text(0.04, top - 0.005, name, fontsize=14, fontweight="bold", color=INK, va="top")
        src = (f"independent record:\nHansen loss {ex['hansen_lossyear']}" if ex["hansen_lossyear"]
               else "independent record:\nSentinel-2 drop 2025→26,\nno Hansen loss")
        fig.text(0.04, top - 0.045, src, fontsize=10.5, color=INK2, va="top", linespacing=1.3)
        for j, k in enumerate("AB"):
            v = verdict[ex["outcome"][k]]
            col = DEC if v == "decrease" else LAND
            fig.text(0.825, top - 0.012 - j * 0.05, f"{k}: {v}", fontsize=12.5, fontweight="bold",
                     color="white" if v == "decrease" else INK, va="top", bbox=dict(fc=col, ec="none", pad=3))
        fig.text(0.825, top - 0.115, why, fontsize=10.5, color=INK2, va="top", linespacing=1.25)
    hs = [plt.Line2D([], [], color=CFG["A"], lw=2), plt.Line2D([], [], color=CFG["B"], lw=2),
          plt.Line2D([], [], ls="", marker="o", color=MUTED, ms=4), plt.Line2D([], [], ls="", marker="o", color=INK, ms=5)]
    fig.legend(hs, ["\"normal\" under A (2018–2023)", "\"normal\" under B (2024–2025)", "NBR 2018–2025",
                    "NBR 2026"], loc="lower left", bbox_to_anchor=(0.23, 0.765), ncol=4, fontsize=11.5, frameon=False)
    footer(fig, "Each \"normal\" curve is BULC-D's fitted seasonal expectation, drawn in every year it was learned from "
                "and in 2026. NBR: a vegetation index that drops\nsharply after harvest or fire. Landsat 8/9, 4-day bins. "
                "Example pixels are centers of uniform patches. " + FOOT_RUN.split(". BULC-D")[0] + ".", y=0.065)
    save(fig, "05_Q3_why_expectation_matters.png")


# ---------------------------------------------------------------- 06 Q3 maps
def older_share(k):
    c = N_["composition_km2"][k]
    return 100 * (c["older_2018_2024"] + c["older_2025"]) / sum(c.values())


def fig06_maps():
    fig = figure()
    comp = N_["composition_km2"]
    header(fig, "Q3 · HOW DOES THE EXPECTATION PERIOD AFFECT DETECTION?",
           f"Older disturbances make up {older_share('A'):.0f}% of A's 2026 map, {older_share('B'):.0f}% of B's",
           "Each map shows what BULC-D flags as decrease in 2026, colored by when independent records say the "
           "disturbance happened.")
    cats = [("older_2018_2024", OLD, "older: disturbed 2018–2024 (Hansen)"),
            ("older_2025", Y25, "disturbed 2025 (Hansen)"),
            ("likely_2026", Y26, "likely 2026 (Sentinel-2 drop)"),
            ("no_record", NOREC, "no independent record")]
    masks = {"older_2018_2024": land & (loss >= 18) & (loss <= 24), "older_2025": loss == 25, "likely_2026": likely26,
             "no_record": ~older & ~likely26}
    w = 0.27
    h = w * 13.333 / 7.5
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * 0.315, 0.25, w, h])
        base_map(ax)
        for key, col, _ in cats:
            overlay(ax, (o[k] == 0) & masks[key], col)
        ax.set_title(f"{CFG_NAME[k]} · {N_['decrease_km2'][k]:.1f} km² flagged", loc="left", fontsize=14.5, fontweight="bold",
                     color=INK, pad=6)
        if i == 0:
            scale_bar(ax)
        # stacked share bar under each map
        bx = fig.add_axes([0.04 + i * 0.315, 0.2, w, 0.03])
        left = 0
        tot = sum(comp[k].values())
        for key, col, _ in cats:
            v = 100 * comp[k][key] / tot
            bx.barh(0, v, left=left, color=col, height=1, edgecolor="white", lw=1.5)
            if v >= 8:
                bx.text(left + v / 2, 0, f"{v:.0f}%", ha="center", va="center", fontsize=11.5,
                        color="white" if key != "older_2025" else INK, fontweight="bold")
            left += v
        bx.set_xlim(0, 100)
        bx.axis("off")
    for i, (key, col, lab) in enumerate(cats):
        swatch(fig, [0.04, 0.33, 0.55, 0.77][i], 0.15, col, lab, fontsize=12)
    footer(fig, "Bars: share of each map's 2026 decrease area. Hansen Global Forest Change v1.13 loss year (through "
                "2025); \"likely 2026\": Sentinel-2 NBR dropped ≥ 0.2 from late 2025\nto late 2026 with no Hansen loss "
                "2018–2025. Independent satellite estimates, not field-verified. Fewer flagged km² is not the same as "
                "more accurate.\n" + FOOT_RUN, y=0.11)
    save(fig, "06_Q3_maps_by_expectation.png")


# ---------------------------------------------------------------- 07 Q4 older disturbances
def fig07_older():
    fig = figure()
    fb = N_["flagged_by_hansen_group"]
    header(fig, "Q4 · DOES A SHORTER, MORE RECENT EXPECTATION REDUCE DETECTIONS OF EARLIER DISTURBANCES?",
           "Yes for 2022–2024 disturbances, but not for last year's",
           "Share of land disturbed in each period (independent record: Hansen) that BULC-D still flags as "
           "decrease in 2026.")
    ax = fig.add_axes([0.07, 0.3, 0.6, 0.45])
    groups = [g for g, _ in HANSEN_GROUPS]
    xs = np.arange(len(groups))
    where = {"A": {"2018–2021": "in", "2022–2023": "in", "2024": "gap", "2025": "gap"},
             "B": {"2018–2021": "before", "2022–2023": "before", "2024": "in", "2025": "last yr"},
             "C": {"2018–2021": "in", "2022–2023": "in", "2024": "in", "2025": "last yr"}}
    for j, k in enumerate("ABC"):
        vals = [fb[k][g] for g in groups]
        x = xs + (j - 1) * 0.27
        ax.bar(x, vals, width=0.25, color=CFG[k], edgecolor="white", lw=1.5)
        for xx, v, g in zip(x, vals, groups):
            ax.text(xx, v + 1.5, f"{v:.0f}%", ha="center", fontsize=11.5, color=INK, fontweight="bold")
            ax.text(xx, -5, where[k][g], ha="center", va="top", fontsize=9.5, color=INK2)
    ax.set_xticks(xs, [f"Disturbed {g}\n({N_['hansen_group_km2'][g]:.0f} km²)" for g in groups], fontsize=12.5)
    ax.tick_params(axis="x", pad=24, length=0)
    ax.set_ylim(0, 110)
    ax.set_yticks([0, 25, 50, 75, 100], ["0", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("still flagged as decrease in 2026", fontsize=12.5)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for j, k in enumerate("ABC"):
        swatch(fig, 0.07 + j * 0.16, 0.8, CFG[k], CFG_NAME[k], fontsize=12.5)
    fig.text(0.07, 0.165, "Small labels under the bars: where that disturbance year falls for each version: inside the "
             "expectation period (\"in\";\n\"last yr\" = its final year), in the gap, or before it.", fontsize=11,
             color=INK2, va="top", linespacing=1.3)
    box(fig, 0.71, 0.2, 0.26, 0.58)
    fig.text(0.725, 0.76, "What this shows", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.725, 0.715,
             "• Disturbances in the gap are\n  almost always re-flagged (A: 96–97%).\n\n"
             "• A disturbance inside the\n  expectation stops being flagged\n  only when \"normal\" contains\n"
             "  enough years after it:\n  B drops 2024 harvests (10%)\n  but still flags 2025 ones (84%).\n\n"
             "• C adds 2024–2025 to a mostly\n  pre-disturbance \"normal\", so it\n  still flags 85–95% of them.\n\n"
             "• Old disturbances (2018–2021)\n  have mostly regrown: rarely\n  flagged by any version.",
             fontsize=12, color=INK2, va="top", linespacing=1.3)
    footer(fig, "Disturbed years from Hansen Global Forest Change v1.13 (independent satellite product, not "
                "field-verified).\n" + FOOT_RUN, y=0.08)
    save(fig, "07_Q4_older_disturbances.png")


# ---------------------------------------------------------------- 08 Q5 missing 2026
def fig08_missing():
    fig = figure()
    det = N_["likely26_detected"]
    comp = N_["composition_km2"]
    header(fig, "Q5 · DOES CHANGING THE EXPECTATION PERIOD MAKE US MISS GENUINE 2026 DISTURBANCES?",
           f"No sign of it: all three detect about 9 in 10 likely 2026 disturbances",
           f"Test set: {N_['likely26_km2']:.1f} km² where an independent satellite (Sentinel-2) shows a strong drop "
           "from 2025 to 2026\nand no earlier loss is recorded.")
    ax = fig.add_axes([0.07, 0.24, 0.38, 0.46])
    ks = list("ABC")
    ax.bar(range(3), [det[k] for k in ks], color=[CFG[k] for k in ks], width=0.6, edgecolor="white", lw=2)
    for i, k in enumerate(ks):
        ax.text(i, det[k] + 2, f"{det[k]:.0f}%", ha="center", fontsize=20, fontweight="bold", color=INK)
    ax.set_xticks(range(3), [CFG_NAME[k] for k in ks], fontsize=13)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 50, 100], ["0", "50%", "100%"])
    ax.set_title("Likely 2026 disturbances that BULC-D flags", loc="left", fontsize=14.5, pad=10)
    bar_style(ax)
    bx = fig.add_axes([0.55, 0.24, 0.38, 0.46])
    vals = [comp[k]["no_record"] for k in ks]
    bx.bar(range(3), vals, color=[CFG[k] for k in ks], width=0.6, edgecolor="white", lw=2)
    for i, v in enumerate(vals):
        bx.text(i, v + 0.12, f"{v:.1f} km²", ha="center", fontsize=16, fontweight="bold", color=INK)
    bx.set_xticks(range(3), [CFG_NAME[k] for k in ks], fontsize=13)
    bx.set_ylim(0, max(vals) * 1.3)
    bx.set_ylabel("km²", fontsize=12.5)
    bx.set_title("Flagged area with no independent record", loc="left", fontsize=14.5, pad=10)
    bar_style(bx)
    fig.text(0.55, 0.175, "Could be false alarms, or real change too small or subtle for\nthe checks. We can't tell yet.",
             fontsize=11.5, color=INK2, va="top")
    fig.text(0.07, 0.175, "B flags slightly more of them, not fewer.", fontsize=11.5, color=INK2, va="top")
    footer(fig, "\"Likely 2026\": Sentinel-2 NBR ≥ 0.2 lower in late 2026 than late 2025, and no Hansen loss 2018–2025. "
                "It covers strong, harvest-like change only;\nsubtle or small 2026 disturbances are not tested here. "
                "Not field-verified.\n" + FOOT_RUN, y=0.095)
    save(fig, "08_Q5_missing_2026.png")


# ---------------------------------------------------------------- 09 Q6 timing
def fig09_timing():
    fig = figure()
    t = N_["timing_vs_s2_month"]["A"]
    header(fig, "Q6 · HOW ACCURATELY CAN BULC-D IDENTIFY WHEN DISTURBANCES OCCURRED?",
           "Usually the right year, and within a month for most 2026 disturbances",
           "BULC-D's detection date compared with dates from independent satellite records (not field-verified).")
    fig.text(0.04, 0.775, "Which year?", fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.74, "Compared with Hansen's forest-loss year", fontsize=12, color=INK2, va="top")
    h24, h25 = N_["hansen2024_first_detected"], N_["hansen2025_first_detected"]
    tiles = [(f"{h24[2024]:.0f}%", "of 2024 disturbances (Hansen)\nwere first detected by BULC-D\nin 2024",
              f"{h24[2025]:.0f}% a year later, {h24[0]:.0f}% not detected"),
             (f"{h25[2025]:.0f}%", "of 2025 disturbances (Hansen)\nwere first detected by BULC-D\nin 2025",
              f"{h25[2024]:.0f}% a year earlier, {h25[0]:.0f}% not detected")]
    for i, (big, txt, rest) in enumerate(tiles):
        y = 0.67 - i * 0.26
        box(fig, 0.04, y - 0.22, 0.36, 0.23)
        fig.text(0.055, y, big, fontsize=34, fontweight="bold", color=INK, va="top")
        fig.text(0.18, y - 0.01, txt, fontsize=12.5, color=INK2, va="top", linespacing=1.3)
        fig.text(0.055, y - 0.165, rest, fontsize=11, color=INK2, va="top")

    fig.text(0.47, 0.775, "Which month? (2026 disturbances)", fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.47, 0.74, "BULC-D's first detection vs the month Sentinel-2 first shows the drop (expectation A)",
             fontsize=12, color=INK2, va="top")
    ax = fig.add_axes([0.5, 0.27, 0.46, 0.4])
    cats = [("early2", "2+ months\nearly"), ("early1", "1 month\nearly"), ("same", "same\nmonth"),
            ("late1", "1 month\nlate"), ("late2", "2+ months\nlate")]
    cols = [Y25, MUTED, NOREC, MUTED, "#c9c7bf"]
    vals = [t[k] for k, _ in cats]
    ax.bar(range(5), vals, color=cols, width=0.62, edgecolor="white", lw=2)
    for i, v in enumerate(vals):
        ax.text(i, v + 1.2, f"{v:.0f}%", ha="center", fontsize=15, fontweight="bold", color=INK)
    ax.set_xticks(range(5), [c[1] for c in cats], fontsize=12)
    ax.set_ylim(0, 58)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    bar_style(ax)
    ax.annotate("likely seasonal false\nalarms: March–April\ncrossings before a\nsummer change", xy=(0, vals[0] + 5.5),
                xytext=(-0.35, 20), fontsize=11, color=INK, ha="left",
                arrowprops=dict(arrowstyle="->", color=INK2, lw=1.2))
    tb, tc = N_["timing_vs_s2_month"]["B"], N_["timing_vs_s2_month"]["C"]
    fig.text(0.5, 0.18, f"{t['same'] + t['late1']:.0f}% within a month (same month or one month later).\nB and C are "
             f"nearly identical ({tb['same']:.0f}% / {tc['same']:.0f}% same month).", fontsize=12, color=INK2, va="top",
             linespacing=1.35)
    footer(fig, "Year: Hansen Global Forest Change loss year vs BULC-D's first year flagged (expectation A; full-year runs "
                "2024, 2025, 2026). Month: first month whose Sentinel-2 NBR\nis ≥ 0.25 below the same month of 2025 and "
                "stays down, vs BULC-D's first crossing (4-day bin end dates). Early crossings are associated with snowy springs "
                "in the expectation\nyears (2026's spring was almost snow-free). " + FOOT_RUN.split(". BULC-D")[0] + ".",
           y=0.085)
    save(fig, "09_Q6_timing.png")


# ---------------------------------------------------------------- 10 Q7 tradeoffs
def fig10_tradeoffs():
    fig = figure()
    fb = N_["flagged_by_hansen_group"]
    header(fig, "Q7 · WHAT ARE THE TRADEOFFS BETWEEN EXPECTATION PERIODS?",
           "Each version of \"normal\" answers a slightly different question",
           "None is \"most accurate\" on this evidence: they trade isolation of 2026 change against data volume "
           "and side effects.")
    rows = [
        ("Observations behind \"normal\" (per pixel)", {k: f"{N_['exp_obs'][k]:.0f}" for k in "ABC"}, None),
        ("2022–2024 disturbances still flagged in 2026", {k: f"{N_['flagged_older_2022_2024'][k]:.0f}%" for k in "ABC"},
         "lower = better isolation of 2026"),
        ("2025 disturbances still flagged in 2026", {k: f"{fb[k]['2025']:.0f}%" for k in "ABC"}, None),
        ("Likely 2026 disturbances flagged", {k: f"{N_['likely26_detected'][k]:.0f}%" for k in "ABC"},
         "higher = more sensitive"),
        ("Flagged area with no independent record", {k: f"{N_['composition_km2'][k]['no_record']:.1f} km²" for k in "ABC"},
         "false alarm or subtle change?"),
        ("Regrowing 2018–2023 disturbances shown as \"increase\"",
         {k: f"{N_['increase_on_2018_2023_loss'][k]:.0f}%" for k in "ABC"}, "a side effect"),
        ("Spring false alarms that later clear", {k: f"{N_['spring_false_episodes_km2'][k]:.1f} km²" for k in "ABC"},
         "do not reach the map"),
    ]
    x_lab, xs = 0.04, {"A": 0.47, "B": 0.585, "C": 0.70}
    y = 0.77
    for k in "ABC":
        fig.text(xs[k], y, CFG_NAME[k], fontsize=13.5, fontweight="bold", color=CFG[k], ha="center", va="top")
    y -= 0.06
    for i, (lab, vals, note) in enumerate(rows):
        if i % 2 == 0:
            fig.patches.append(mpatches.Rectangle((0.035, y - 0.04), 0.93, 0.05, transform=fig.transFigure, fc=SOFT,
                                                  ec="none"))
        fig.text(x_lab, y, lab, fontsize=12.5, color=INK, va="top")
        for k in "ABC":
            fig.text(xs[k], y, vals[k], fontsize=14, color=INK, ha="center", va="top", fontweight="bold")
        if note:
            fig.text(0.77, y, note, fontsize=10.5, color=INK2, va="top")
        y -= 0.05
    summ = [("A", "Most stable \"normal\". Keeps re-flagging disturbances from the last few years, so it needs the "
                  "detection year (Q2) to separate new change."),
            ("B", "Best isolates 2026 change, with no loss of 2026 sensitivity in this test. Rests on fewer observations,\n"
                  "still flags last year's disturbances, and shows regrowing stands as \"increase\"."),
            ("C", "Most observations, but behaves much like A: adding 2024–2025 to a mostly older \"normal\" removes "
                  "few recent disturbances.")]
    y = 0.31
    for k, s in summ:
        fig.text(0.04, y, f"{k}:", fontsize=13, fontweight="bold", color=CFG[k], va="top")
        fig.text(0.06, y, s, fontsize=12, color=INK2, va="top", linespacing=1.35)
        y -= 0.05 + 0.03 * s.count("\n")
    footer(fig, "All numbers from this deck's earlier figures (independent checks: Hansen loss year through 2025; "
                "Sentinel-2 change 2025→2026; not field-verified).\n" + FOOT_RUN, y=0.08)
    save(fig, "10_Q7_tradeoffs.png")


# ---------------------------------------------------------------- 11 open questions
def fig11_open():
    fig = figure()
    header(fig, "WHAT WE STILL DON'T KNOW", "Open questions and proposed next steps",
           "The results above use independent satellite products as a check. They are not an accuracy assessment.")
    cols = [("Open questions", [
        "How accurate is each version against field or high-resolution\nreference data? (No reference sample yet.)",
        "Does a recent expectation also catch subtle or small 2026\ndisturbances? (Our 2026 test covers strong drops only.)",
        "What happens in a snowy target year? (2026 was nearly\nsnow-free; snow is not masked in BULC-D's input.)",
        "Do these results hold outside a harvest-dominated, 400 km²\nCoast Range area, and over a full ecoregion?",
        "Is B's \"increase\" on regrowing stands a problem for users?"]),
        ("Proposed next steps (not started)", [
            "Reference sample: 50–100 pixels per class, interpreted\nwith dated high-resolution imagery.",
            "Repeat with 2025 as the target year, where Hansen covers\nthe whole area as an independent check.",
            "Test masking the snow flag in expectation and monitoring.",
            "Run a second region and a full ecoregion export.",
            "Decide the reporting rule: detection year with A, a recent\nexpectation like B, or both."])]
    for i, (title, items) in enumerate(cols):
        x = 0.04 + i * 0.48
        box(fig, x, 0.12, 0.45, 0.65, fc=SOFT if i == 0 else "white", ec=GRID if i == 0 else MUTED)
        fig.text(x + 0.02, 0.75, title, fontsize=15, fontweight="bold", color=INK, va="top")
        y = 0.69
        for it in items:
            fig.text(x + 0.02, y, "•", fontsize=13, color=INK, va="top")
            fig.text(x + 0.04, y, it, fontsize=12.5, color=INK2, va="top", linespacing=1.3)
            y -= 0.035 * (it.count("\n") + 1) + 0.04
    save(fig, "11_open_questions.png")


if __name__ == "__main__":
    for f in (fig01_problem, fig02_method, fig03_processing, fig04_new_vs_old, fig05_examples, fig06_maps,
              fig07_older, fig08_missing, fig09_timing, fig10_tradeoffs, fig11_open):
        f()

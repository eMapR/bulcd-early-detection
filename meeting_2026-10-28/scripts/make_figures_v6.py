"""Meeting figures v6: the v5 results in plain language (read-only; no numbers change).

    python meeting_2026-10-28/scripts/make_figures_v6.py

All data, classes and numbers come from make_figures_v5 (imported, not recomputed); this file only changes
wording and layout. Writes figures_v6/*.png and data/figures_v6_numbers.json (a copy of the v5 numbers).
Earlier figure folders are untouched.

Slide anatomy: research question / plain-English finding (title) / figure / one-two sentence explanation /
short limitation / one-line source. Methods and definitions: appendix A4; timing details: appendix A5.
"""
import json
import textwrap

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

import make_figures_v5 as v5
from make_figures import DATA, EXT_KM, GRID, HERE, INK, INK2, MUTED, base_map, figure, overlay, swatch

OUT = HERE / "figures_v6"
OUT.mkdir(exist_ok=True)
N_ = v5.N_
(DATA / "figures_v6_numbers.json").write_text(json.dumps(N_, indent=1, default=float))
flag, CLS, COL = v5.flag, v5.CLS, v5.COL
HIST, Y25, S26, NONE, SOFT = v5.HIST, v5.Y25, v5.S26, v5.NONE, v5.SOFT
NB = N_["flagged_by_class_km2"]

APPROACH = {"A": "2018–2023", "B": "2024–2025", "C": "2018–2025"}
LAB = {"hist": "Older forest loss (2018–2024)", "y2025": "2025 forest loss",
       "s26": "2026 vegetation decline in Sentinel-2", "none": "Not seen in other data"}
SOURCE = ("Oregon Coast Range pilot, 400 km² · BULC-D on Landsat 8/9, whole-year monitoring · 2026 data through "
          "Oct 27 · Forest loss: Hansen GFC v1.13 · Methods: appendix A4")


def save(fig, name):
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)
    print("wrote", OUT / name)


def slide(q, question, title):
    """Question line, finding as title (wraps to two lines). Returns the y just below the title."""
    fig = figure()
    chip = fig.text(0.04, 0.955, f" Q{q} ", fontsize=13, fontweight="bold", color="white", va="top",
                    bbox=dict(boxstyle="round,pad=0.35", fc=INK, ec="none"))
    fig.canvas.draw()
    x = fig.transFigure.inverted().transform(chip.get_window_extent())[1, 0] + 0.012
    fig.text(x, 0.955, question, fontsize=14, color=INK2, va="top", fontweight="bold")
    lines = textwrap.wrap(title, 66)
    fig.text(0.04, 0.9, "\n".join(lines), fontsize=22, fontweight="bold", color=INK, va="top", linespacing=1.15)
    return fig, 0.9 - 0.068 * len(lines)


def explain(fig, text, limitation=None, y=0.2):
    """Explanation (wrapped) and an optional limitation, bottom-anchored above the source line."""
    fig.text(0.04, y, "\n".join(textwrap.wrap(text.replace("\n", " "), 125)), fontsize=13.5, color=INK, va="top",
             linespacing=1.35)
    if limitation:
        lines = textwrap.wrap(limitation.replace("\n", " "), 130)
        ly = 0.05 + 0.03 * len(lines)
        fig.text(0.04, ly, "Limitation", fontsize=11.5, fontweight="bold", color=MUTED, va="top")
        fig.text(0.125, ly, "\n".join(lines), fontsize=11.5, color=MUTED, va="top", linespacing=1.35)
    fig.text(0.04, 0.025, SOURCE, fontsize=9.5, color=MUTED, va="center")


def name(k):
    return f"{k}: normal = {APPROACH[k]}"


def detected(k, r, c):
    return flag[k][r - 3:r + 4, c - 3:c + 4].mean() > 0.5


# ---------------------------------------------------------------- Q1
def q1():
    fig, y = slide(1, "Can BULC-D process large regions efficiently?",
                   "BULC-D processes 100 km² in a few minutes, but larger regions still need testing.")
    fig.text(0.04, y - 0.01, "Three approaches, differing only in the years used to define normal conditions "
             "(the \"expectation period\"):", fontsize=13, color=INK2, va="top")
    b = N_["bench_fullyear_tile"]
    for i, k in enumerate("ABC"):
        x = 0.04 + i * 0.31
        fig.patches.append(mpatches.FancyBboxPatch((x, 0.33), 0.29, 0.36, boxstyle="round,pad=0.006",
                                                   transform=fig.transFigure, fc=SOFT, ec=GRID))
        fig.text(x + 0.02, 0.665, k, fontsize=26, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.06, 0.66, f"Normal conditions\nbased on {APPROACH[k]}", fontsize=13, color=INK2, va="top",
                 linespacing=1.25)
        fig.text(x + 0.02, 0.555, f"{b[k]['minutes']:.1f} min", fontsize=40, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.02, 0.42, f"per 100 km²\n{b[k]['eecu_s']:.0f} Earth Engine compute-seconds", fontsize=12.5,
                 color=INK2, va="top")
    explain(fig, "Processing a 100 km² area took approximately 2–4 minutes, depending on the years used to define "
                 "normal conditions.\nWe have not yet measured processing time across an entire region.",
            "One 100 km² tile was timed. Time for a whole region (Earth Engine task limits, tile-to-tile variation) "
            "is untested.", y=0.26)
    save(fig, "Q1_regional_processing.png")


# ---------------------------------------------------------------- Q2
def q2(style="fill", fname="Q2_new_vs_older.png"):
    fig, y = slide(2, "Can BULC-D distinguish new disturbances from older ones?",
                   "BULC-D detects vegetation changes, but cannot directly determine when they happened.")
    fig.text(0.04, y - 0.005, "Same 6 × 6 km area. Colored: vegetation decrease detected in 2026, colored by what "
             "forest-loss data and Sentinel-2 imagery show there.", fontsize=12.5, color=INK2, va="top")
    w, gap, top = 0.225, 0.02, y - 0.075
    h = w * 13.333 / 7.5
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * (w + gap), top - h, w, h])
        v5.map_panel(ax, k, style)
        ax.set_title(name(k), loc="left", fontsize=13.5, fontweight="bold", color=INK, pad=5)
        for n, (r, c, _) in enumerate(v5.EXAMPLES, 1):
            ax.text((c + 0.5) * 0.03, EXT_KM - (r + 0.5) * 0.03, str(n), ha="center", va="center", fontsize=11,
                    fontweight="bold", color=INK, zorder=8, bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec=INK))
    # legend + examples on the right
    x0 = 0.04 + 3 * (w + gap) + 0.005
    fig.text(x0, top, "Colors", fontsize=12.5, fontweight="bold", color=INK, va="top")
    shown = ("hist", "y2025", "s26", "none") if style == "fill" else ("hist", "y2025", "s26")
    for j, c in enumerate(shown):
        swatch(fig, x0, top - 0.05 - j * 0.04, COL[c], LAB[c].replace(" in Sentinel-2", "\n(Sentinel-2)"),
               fontsize=11)
    ey = top - 0.25
    fig.text(x0, ey, "Example stands", fontsize=12.5, fontweight="bold", color=INK, va="top")
    names = ["Cut in 2024", "Cut in 2025", "2026 decline"]
    for n, ((r, c, _), lab) in enumerate(zip(v5.EXAMPLES, names), 1):
        yy = ey - 0.045 - (n - 1) * 0.06
        fig.text(x0 + 0.008, yy, str(n), fontsize=11, fontweight="bold", color=INK, va="center", ha="center",
                 bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec=INK))
        fig.text(x0 + 0.022, yy + 0.008, lab, fontsize=11.5, fontweight="bold", color=INK, va="center")
        fig.text(x0 + 0.022, yy - 0.019, "   ".join(f"{k} {'✓' if detected(k, r, c) else '✗'}" for k in "ABC"),
                 fontsize=11.5, color=INK2, va="center")
    explain(fig, "Older forest loss can continue to appear as a change in 2026. Using more recent years to define "
                 "normal conditions reduces these\nolder detections, but does not eliminate them.",
            "Forest-loss years (Hansen) and Sentinel-2 declines show that change happened; they are not verified "
            "disturbance dates.", y=0.175)
    save(fig, fname)


# ---------------------------------------------------------------- Q3
def q3():
    fig, y = slide(3, "How does the expectation period affect detection?",
                   "The years used to define normal conditions strongly affect which disturbances are detected.")
    s = N_["share_flagged_by_loss_year"]
    fig.text(0.04, y - 0.005, "% of each year's forest loss still detected as a vegetation decrease in 2026. "
             "Shaded: years used to define normal conditions.", fontsize=12.5, color=INK2, va="top")
    years = list(range(2018, 2027))
    ax = fig.add_axes([0.13, 0.27, 0.83, y - 0.36])
    ax.set_xlim(2017.5, 2026.5)
    ax.set_ylim(-0.5, 2.62)
    ax.axis("off")
    for row, k in enumerate("ABC"):
        yy = 2 - row
        a, b = v5.NORMAL[k]
        ax.add_patch(mpatches.FancyBboxPatch((a - 0.45, yy - 0.42), b - a + 0.9, 0.84, boxstyle="round,pad=0.02",
                                             fc="#e9e7e1", ec="none"))
        fig.text(0.04, ax.transData.transform((0, yy))[1] / fig.bbox.height, k, fontsize=20, fontweight="bold",
                 color=INK, va="center")
        for yr in years:
            v, col = (N_["s26_flagged"][k]["pct"], S26) if yr == 2026 else (s[k][yr], Y25 if yr == 2025 else HIST)
            ax.add_patch(mpatches.Circle((yr, yy + 0.08), 0.27, fc="white", ec=GRID, lw=1))
            ax.add_patch(mpatches.Circle((yr, yy + 0.08), max(0.27 * np.sqrt(v / 100), 0.02), fc=col, ec="none"))
            ax.text(yr, yy - 0.25, f"{v:.0f}%", fontsize=13, color=INK, fontweight="bold", ha="center", va="center")
    for yr in years[:-1]:
        ax.text(yr, 2.55, str(yr), ha="center", fontsize=13, color=INK)
    ax.text(2026, 2.55, "2026\ndecline", ha="center", fontsize=12, color=S26, fontweight="bold", va="bottom")
    ax.axvline(2025.5, color=INK2, lw=1, ls=(0, (3, 3)), ymin=0.05, ymax=0.93)
    explain(fig, "When normal conditions are based on older imagery, more recent forest loss continues to appear as "
                 "a change.\nIncluding imagery collected after a disturbance can reduce these repeated detections.",
            "Forest-loss years from Hansen data; the 2026 column is vegetation declines seen in Sentinel-2 imagery.",
            y=0.2)
    save(fig, "Q3_expectation_period_effect.png")


# ---------------------------------------------------------------- Q4
def q4():
    fig, y = slide(4, "Does a shorter, more recent expectation period reduce older detections?",
                   "Using recent imagery reduces detections of older forest loss, but last year's loss remains a "
                   "problem.")
    panels = [("Older forest loss (2018–2024)\nstill detected in 2026", N_["hist_flagged"], HIST),
              ("2025 forest loss\nstill detected in 2026", N_["y2025_flagged"], Y25)]
    for p, (title, vals, col) in enumerate(panels):
        x = 0.06 + p * 0.47
        ax = fig.add_axes([x, 0.34, 0.38, y - 0.46])
        for i, k in enumerate("ABC"):
            v = vals[k]["pct"]
            ax.bar(i, v, width=0.62, color=col, alpha=1 if k == "B" else 0.45, edgecolor=INK if k == "B" else "none",
                   lw=2)
            ax.text(i, v + 3, f"{v:.0f}%", ha="center", va="bottom", fontsize=28 if k == "B" else 18,
                    fontweight="bold", color=INK)
        ax.set_xticks(range(3), [f"{k}\n{APPROACH[k]}" for k in "ABC"], fontsize=13)
        ax.set_ylim(0, 118)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="x", length=0)
        ax.set_title(title, loc="left", fontsize=15, fontweight="bold", color=INK, pad=10)
    explain(fig, f"Using 2024–2025 to define normal conditions reduced detections of forest loss from 2018–2024 "
                 f"from {N_['hist_flagged']['A']['pct']:.0f}% to {N_['hist_flagged']['B']['pct']:.0f}%.\nHowever, "
                 f"{N_['y2025_flagged']['B']['pct']:.0f}% of forest loss from 2025 was still detected as a decrease in "
                 "2026: normal conditions\ninclude only about one year after a 2025 harvest.",
            "About 1 km² of older forest loss also declined again in 2026 (possible repeat disturbance). Per-year "
            "table: appendix A1.", y=0.23)
    save(fig, "Q4_older_detections.png")


# ---------------------------------------------------------------- Q5
def q5():
    fig, y = slide(5, "Does changing the expectation period cause us to miss new disturbances?",
                   "All three approaches detect about 90% of strong vegetation declines observed in 2026.")
    fig.text(0.04, y - 0.005, f"Strong 2026 vegetation declines in Sentinel-2 imagery ({N_['class_km2']['s26']:.1f} "
             "km²): % detected by BULC-D as a vegetation decrease in 2026.", fontsize=12.5, color=INK2, va="top")
    ax = fig.add_axes([0.08, 0.33, 0.5, y - 0.44])
    for i, k in enumerate("ABC"):
        v = N_["s26_flagged"][k]["pct"]
        ax.bar(i, v, width=0.62, color=S26)
        ax.text(i, v + 3, f"{v:.0f}%", ha="center", va="bottom", fontsize=26, fontweight="bold", color=INK)
    ax.set_xticks(range(3), [f"{k}\n{APPROACH[k]}" for k in "ABC"], fontsize=13)
    ax.set_ylim(0, 118)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="x", length=0)
    x0 = 0.65
    fig.text(x0, y - 0.09, "The same declines?", fontsize=15, fontweight="bold", color=INK, va="top")
    for j, (v, lab, col) in enumerate(((N_["s26_all_three"], "detected by all three", S26),
                                       (100 - N_["s26_all_three"] - N_["s26_none"], "by one or two", "#f2a4a0"),
                                       (N_["s26_none"], "by none", GRID))):
        yy = y - 0.17 - j * 0.085
        fig.text(x0, yy, f"{v:.0f}%", fontsize=30 if j == 0 else 22, fontweight="bold", color=INK, va="center")
        fig.patches.append(mpatches.Rectangle((x0 + 0.1, yy - 0.012), 0.012, 0.024, transform=fig.transFigure,
                                              fc=col, ec=MUTED, lw=0.6))
        fig.text(x0 + 0.118, yy, lab, fontsize=13, color=INK2, va="center")
    explain(fig, "Changing the years used to define normal conditions had little effect on detecting strong vegetation "
                 "declines independently observed\nin Sentinel-2 imagery. However, we have not established how well the "
                 "approaches detect subtle disturbances.",
            f"Strong declines only (not all 2026 disturbances); {N_['s26_first_seen_pct']['late_2025']:.0f}% were already "
            "visible in Nov–Dec 2025. Areas detected but not seen in other data\n"
            f"(A {NB['A']['none']:.1f}, B {NB['B']['none']:.1f}, C {NB['C']['none']:.1f} km²) may be subtle change or "
            "false alarms.", y=0.215)
    save(fig, "Q5_new_disturbances.png")


# ---------------------------------------------------------------- Q6 / Q7 categories
CATS = [("before_change", "Before change was visible", "#b8322f", "white"),
        ("in_window", "Same month", INK2, "white"),
        ("next_month", "1 month later", "#8db8e8", INK),
        ("later", "2+ months later", "#1f5fa8", "white"),
        ("not_flagged", "Not yet detected", GRID, INK)]


def cat_bar(fig, x, y, w, h, vals, minlab=6, fs=12):
    ax = fig.add_axes([x, y, w, h])
    left = 0
    for key, _, col, tc in CATS:
        v = vals[key]
        ax.barh(0, v, left=left, color=col, height=1, edgecolor="white", lw=1.5)
        if v >= minlab:
            ax.text(left + v / 2, 0, f"{v:.0f}%", ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)
        left += v
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")


def cat_legend(fig, y, order=None):
    xs = [0.04, 0.235, 0.355, 0.5, 0.65]
    for j, (key, lab, col, _) in enumerate(CATS):
        swatch(fig, xs[j], y, col, lab, fontsize=12)


# ---------------------------------------------------------------- Q6
def q6():
    fig, y = slide(6, "Can full-year monitoring detect disturbances earlier?",
                   "Most spring and summer changes are detected within a month, but winter changes take longer.")
    fig.text(0.04, y - 0.005, "When BULC-D first detected each 2026 vegetation decline, compared with the month it "
             "first became visible in Sentinel-2 imagery.", fontsize=12.5, color=INK2, va="top")
    cat_legend(fig, y - 0.065)
    ts = N_["timing_by_season"]
    top = y - 0.13
    for i, s_ in enumerate(v5.SEASONS):
        yy = top - i * 0.097
        fig.text(0.04, yy, f"First visible\n{s_}", fontsize=13.5, fontweight="bold", color=INK, va="center",
                 linespacing=1.15)
        for r, k in enumerate("ABC"):
            fig.text(0.19, yy + 0.026 - r * 0.026, k, fontsize=11, color=INK2, va="center", fontweight="bold")
            cat_bar(fig, 0.205, yy + 0.015 - r * 0.026, 0.755, 0.022, ts[k][s_], minlab=7, fs=10.5)
    explain(fig, "BULC-D detected most spring and summer vegetation declines within approximately one month of when "
                 "they first appeared in Sentinel-2\nimagery. Changes first observed in January and February were "
                 "generally not detected until March or later.",
            "Compared with the first month the decline was visible, not the actual disturbance date. No comparison "
            "with summer-only monitoring was\nmade. Sep–Oct changes may be too recent to detect by Oct 27. Winter "
            "details: appendix A5.", y=0.215)
    save(fig, "Q6_how_quickly.png")


# ---------------------------------------------------------------- Q7
def q7():
    fig, y = slide(7, "How accurately can BULC-D identify when disturbances occurred?",
                   "About 80% of vegetation declines are detected within a month of when they appear in satellite "
                   "imagery.")
    ax = fig.add_axes([0.04, y - 0.25, 0.92, 0.22])
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.15, 1)
    ax.axis("off")
    ax.plot([0.3, 11.7], [0.5, 0.5], color=GRID, lw=3, solid_capstyle="round")
    ax.add_patch(mpatches.Rectangle((4.2, 0.36), 2.6, 0.28, fc="#e9e7e1", ec="none"))
    ax.text(5.5, 0.5, "actual disturbance date:\nunknown", ha="center", va="center", fontsize=11.5, color=INK2)
    for xx, lab in ((4.2, "Sentinel-2:\nlast month unchanged"), (6.8, "Sentinel-2:\nfirst month changed")):
        ax.plot([xx, xx], [0.3, 0.7], color=INK, lw=2)
        ax.text(xx, 0.76, lab, ha="center", va="bottom", fontsize=11.5, color=INK)
    for xx, key in ((2.2, "before_change"), (5.5, "in_window"), (7.9, "next_month"), (10.0, "later")):
        col, lab = [(c[2], c[1]) for c in CATS if c[0] == key][0]
        ax.plot(xx, 0.16, marker="v", ms=14, color=col, mec="white")
        ax.text(xx, 0.0, lab, ha="center", va="top", fontsize=11.5, color=col if key != "next_month" else INK2,
                fontweight="bold")
    ax.text(0.3, 0.16, "First time BULC-D\ndetected a change:", fontsize=11.5, color=INK, va="center")
    cat_legend(fig, y - 0.3)
    tv = N_["timing_vs_window"]
    for i, k in enumerate("ABC"):
        yy = y - 0.375 - i * 0.06
        fig.text(0.04, yy, k, fontsize=16, fontweight="bold", color=INK, va="center")
        cat_bar(fig, 0.07, yy - 0.021, 0.89, 0.042, tv[k], minlab=2.5)
    explain(fig, "BULC-D generally identifies changes close to when Sentinel-2 first observes them. However, satellite "
                 "imagery does not provide the exact\ndisturbance date, so we cannot yet measure true dating accuracy.",
            "These are first detection dates, which may not persist as a confirmed decrease. "
            f"{N_['s26_first_seen_pct']['late_2025']:.0f}% of the declines were already visible\nin Nov–Dec 2025 "
            "and are left out here; BULC-D detects them in March–April 2026 (appendix A5).", y=0.215)
    save(fig, "Q7_timing_accuracy.png")


# ---------------------------------------------------------------- appendix
def a_header(title):
    fig = figure()
    fig.text(0.04, 0.94, title, fontsize=20, fontweight="bold", color=INK, va="top")
    return fig


def a1_table():
    fig = a_header("Appendix A1 · % of each year's forest loss still detected as a vegetation decrease in 2026")
    s = N_["share_flagged_by_loss_year"]
    cols = ["Forest loss year (Hansen)", "km²", "A  2018–2023", "B  2024–2025", "C  2018–2025"]
    xs = [0.06, 0.3, 0.42, 0.59, 0.76]
    for x, c in zip(xs, cols):
        fig.text(x, 0.83, c, fontsize=13.5, fontweight="bold", color=INK, va="center")
    rows = [(str(y), N_["loss_year_km2"][y], [s[k][y] for k in "ABC"]) for y in range(2018, 2026)]
    rows.append(("2026 decline (Sentinel-2)", N_["class_km2"]["s26"], [N_["s26_flagged"][k]["pct"] for k in "ABC"]))
    rows.append(("Not seen in other data", N_["class_km2"]["none"],
                 [100 * NB[k]["none"] / N_["class_km2"]["none"] for k in "ABC"]))
    for i, (lab, km, vals) in enumerate(rows):
        yy = 0.77 - i * 0.055
        if i % 2 == 0:
            fig.patches.append(mpatches.Rectangle((0.05, yy - 0.024), 0.88, 0.048, transform=fig.transFigure,
                                                  fc=SOFT, ec="none"))
        fig.text(xs[0], yy, lab, fontsize=13, color=INK, va="center")
        fig.text(xs[1], yy, f"{km:.1f}", fontsize=13, color=INK, va="center")
        for x, v in zip(xs[2:], vals):
            fig.text(x, yy, f"{v:.1f}%", fontsize=13, color=INK, va="center")
    fig.text(0.04, 0.13, "Last row: all other land; its detected share could be subtle real change or false alarms "
             "and is not testable here. Possible repeat disturbance (older\nforest loss that also declined in 2026): "
             f"A {N_['repeat_candidates_km2']['A']:.1f}, B {N_['repeat_candidates_km2']['B']:.1f}, "
             f"C {N_['repeat_candidates_km2']['C']:.1f} km².", fontsize=11.5, color=INK2, va="top", linespacing=1.35)
    fig.text(0.04, 0.03, SOURCE, fontsize=9.5, color=MUTED, va="center")
    save(fig, "A1_table_by_loss_year.png")


def a2_maps():
    fig = a_header("Appendix A2 · Whole pilot: vegetation decrease detected in 2026")
    w = 0.28
    h = w * 13.333 / 7.5
    x0, x1, y0, y1 = v5.window()
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * 0.31, 0.83 - h, w, h])
        base_map(ax)
        for c in ("hist", "y2025", "s26", "none"):
            overlay(ax, flag[k] & CLS[c], COL[c])
        ax.add_patch(mpatches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=INK, lw=1.2, ls=(0, (3, 2))))
        ax.set_title(name(k), loc="left", fontsize=14, fontweight="bold", color=INK, pad=6)
    for j, c in enumerate(("hist", "y2025", "s26", "none")):
        swatch(fig, [0.04, 0.29, 0.45, 0.72][j], 0.27, COL[c], LAB[c], fontsize=12)
    fig.text(0.04, 0.2, "Dashed box: the Q2 area. Light gray: land with no decrease detected; white: water. No forest "
             "mask.", fontsize=11.5, color=INK2, va="top")
    fig.text(0.04, 0.03, SOURCE, fontsize=9.5, color=MUTED, va="center")
    save(fig, "A2_whole_area_maps.png")


def a4_methods():
    fig = a_header("Appendix A4 · Methods, definitions and data")
    blocks = [
        ("BULC-D runs", "Landsat 8/9 surface reflectance, normalized burn ratio (NBR). Normal conditions (the "
         "\"expectation period\") are learned from the whole year\nof the listed years; 2026 is monitored Jan 1–Oct 27 "
         "(data available on Oct 27, 2026). \"Vegetation decrease detected in 2026\" = the 2026 result\nends as a "
         "decrease (P(decrease) > 0.65, confirmed rule). No forest mask; water masked. 30 m pixels, 4-day "
         "observation windows."),
        ("Forest loss years", "Hansen Global Forest Change v1.13 (through 2025): older forest loss = loss year "
         "2018–2024; 2025 forest loss = loss year 2025. Annual product;\nit is not a verified disturbance date."),
        ("2026 vegetation decline", "Sentinel-2 (Cloud Score+ ≥ 0.6) NBR fell by ≥ 0.2 between Sep 15–Oct 27, "
         "2025 and the same dates in 2026, with no Hansen loss 2018–2025.\nA strong decline only; not a verified "
         "disturbance. Sentinel-2 was not used by these BULC-D runs."),
        ("Timing (Q6, Q7)", "First time BULC-D detected a change = first 4-day window in 2026 with P(decrease) > 0.65 "
         "(may not persist). Sentinel-2 first month changed =\nfirst month whose monthly median NBR is ≥ 0.25 below the "
         "same month a year earlier and still ≥ 0.2 below the next month. Last month\nunchanged = latest earlier month "
         "within 0.1 of the year before. Monthly medians: about ±1 month."),
        ("Processing (Q1)", "One Earth Engine batch export of tile r0056c0034 (10 × 10 km) per approach, 2026-10-28, "
         "to a separate benchmark folder. Minutes depend on the\nshared queue. Scaling to 10,000 km² (100 tiles: A ≈ "
         "14, B ≈ 5, C ≈ 17 compute-hours) is an untested multiplication."),
    ]
    yy = 0.85
    for head, body in blocks:
        fig.text(0.04, yy, head, fontsize=13.5, fontweight="bold", color=INK, va="top")
        fig.text(0.27, yy, "\n".join(textwrap.wrap(body.replace("\n", " "), 112)), fontsize=11.5, color=INK2,
                 va="top", linespacing=1.35)
        yy -= 0.16
    fig.text(0.04, 0.03, SOURCE.split(" · Methods")[0], fontsize=9.5, color=MUTED, va="center")
    save(fig, "A4_methods.png")


def a5_timing():
    fig = a_header("Appendix A5 · Timing details: winter changes and changes visible in late 2025")
    ax = fig.add_axes([0.06, 0.4, 0.42, 0.42])
    fd = v5.F["A26"]["first_dec"]
    doy = fd[v5.S26_2026 & (fd // 1000 == 2026)] % 1000
    ax.hist(doy, bins=np.arange(1, 125, 4), color=INK2, edgecolor="white", lw=0.5)
    for d in v5.CLEAR_LANDSAT:
        ax.axvline((np.datetime64(d) - np.datetime64("2026-01-01")).astype(int) + 1, color=HIST, lw=1.8, ymax=0.12)
    ax.set_xlim(1, 121)
    ax.set_xticks([1, 32, 60, 91, 121], ["Jan", "Feb", "Mar", "Apr", "May"], fontsize=12)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_title("A: first detections of 2026 declines, Jan–Apr", loc="left", fontsize=14, fontweight="bold",
                 color=INK)
    fig.text(0.06, 0.32, "\n".join(textwrap.wrap(
             "Blue ticks: Landsat images at least half clear (Jan 19, Feb 4–5, Mar 16, Apr 9, 18, 25–26). "
             "Nothing is detected before Mar 16, although clear images exist on Jan 19 and Feb 4–5. Not yet "
             "explained (possible reasons: few clear views, or winter normal conditions that allow more "
             "variation).", 78)),
             fontsize=11.5, color=INK2, va="top", linespacing=1.35)
    sf, lm = N_["s26_first_seen_pct"], N_["late2025_first_bulcd_month"]
    tv = N_["timing_vs_window"]
    fig.text(0.54, 0.82, "When the 2026 declines first became visible", fontsize=14, fontweight="bold", color=INK,
             va="top")
    fig.text(0.54, 0.77, f"Nov–Dec 2025: {sf['late_2025']:.1f}%   (not 2026 disturbances)\n"
             f"Jan 2026: {sf['jan_2026']:.1f}%   (may be late Dec or Jan)\nFeb–Oct 2026: {sf['feb_oct_2026']:.1f}%\n"
             f"No monthly change found: {sf['not_found']:.1f}%", fontsize=12.5, color=INK2, va="top", linespacing=1.5)
    fig.text(0.54, 0.57, "Changes visible in Nov–Dec 2025", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.54, 0.52, "First detected by BULC-D in March–April 2026:\n"
             f"A {lm['A']['Mar'] + lm['A']['Apr']:.0f}%, B {lm['B']['Mar'] + lm['B']['Apr']:.0f}%, "
             f"C {lm['C']['Mar'] + lm['C']['Apr']:.0f}%.\nA 2026 detection alone cannot separate\nlate-2025 from "
             "early-2026 change.", fontsize=12.5, color=INK2, va="top", linespacing=1.4)
    fig.text(0.54, 0.37, "Detected before the change was visible", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.54, 0.32, f"A {tv['A']['before_change']:.1f}%, B {tv['B']['before_change']:.1f}%, "
             f"C {tv['C']['before_change']:.1f}%; median "
             f"{N_['before_change_months_early_median']['A']:.0f} months early (B: "
             f"{N_['before_change_months_early_median']['B']:.0f}).\nPossible false early detections,\nor change "
             "Sentinel-2 did not show.", fontsize=12.5, color=INK2, va="top", linespacing=1.4)
    fig.text(0.04, 0.03, SOURCE, fontsize=9.5, color=MUTED, va="center")
    save(fig, "A5_timing_details.png")


if __name__ == "__main__":
    q1()
    q2()
    q3()
    q4()
    q5()
    q6()
    q7()
    a1_table()
    a2_maps()
    q2(style="outline", fname="A3_map_treatment_alternative.png")
    a4_methods()
    a5_timing()

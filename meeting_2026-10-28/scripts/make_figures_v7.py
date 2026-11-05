"""Figures v7: slides rebuilt around the Sept 30 meeting discussion (read-only; no new BULC-D runs).

    python meeting_2026-10-28/scripts/make_figures_v7.py

Reuses the arrays and masks loaded by make_figures_v5.py (full-year A/B/C runs, Hansen, Sentinel-2).
The only new numbers are the multi-year first-detection breakdown by evidence class, written to
data/figures_v7_numbers.json. The question-to-evidence mapping is in figures_v7/MEETING_MAPPING.md.
"""
import json
import textwrap

import matplotlib.patches as mpatches
import numpy as np

import make_figures_v5 as v5
from make_figures import DATA, EXT_KM, GRID, HERE, INK, INK2, MUTED, figure, overlay, swatch

OUT = HERE / "figures_v7"
OUT.mkdir(exist_ok=True)

flag, CLS, COL, km2, pct = v5.flag, v5.CLS, v5.COL, v5.km2, v5.pct
FIRST = v5.first_year_A  # first detection year: first of 2024 / 2025 / 2026 ending as decrease (expectation 2018-2023)
N_ = v5.N_

EVID = ("s26", "y2025", "hist", "none")
LAB = {"s26": "2026 decline (Sentinel-2)", "y2025": "2025 forest loss (Hansen)",
       "hist": "Older forest loss, 2018–2024 (Hansen)", "none": "Not seen in other data"}
SOURCE = ("Oregon Coast Range pilot, 400 km², 30 m · BULC-D on Landsat 8/9, full-year monitoring (2026 through Oct 27) · "
          "Forest loss: Hansen GFC v1.13")

# What each approach reports as "new in 2026"
REPORT = {
    "orig": flag["A"],                        # single-year run, expectation 2018-2023
    "multi": flag["A"] & (FIRST == 2026),     # same expectation; first detection year 2026 (runs for 2024-2026)
    "recent": flag["B"],                      # expectation 2024-2025
}
NUM = {k: {"km2": km2(m), **{c: km2(m & CLS[c]) for c in EVID},
           "s26_captured_pct": pct(m, CLS["s26"])} for k, m in REPORT.items()}
for n in NUM.values():  # each category's share of the area mapped as 2026 change (categories partition it)
    n["share_pct"] = {c: 100 * n[c] / n["km2"] for c in EVID}
NUM["first_year_check"] = N_["year_check_A"]
(DATA / "figures_v7_numbers.json").write_text(json.dumps(NUM, indent=1, default=float))


def save(fig, name):
    fig.savefig(OUT / name, dpi=200)
    v5.plt.close(fig)
    print("wrote", OUT / name)


def chip(fig, x, y, text, color, fs=11):
    """Filled label; returns its right edge in figure coordinates."""
    t = fig.text(x, y, f" {text} ", fontsize=fs, fontweight="bold", color="white", va="center",
                 bbox=dict(boxstyle="round,pad=0.3", fc=color, ec="none"))
    fig.canvas.draw()
    return fig.transFigure.inverted().transform(t.get_window_extent())[1, 0]


def slide(section, title, source=SOURCE):
    """Section label and a short title. Returns the y below the header."""
    fig = figure()
    fig.text(0.04, 0.945, section.upper(), fontsize=13, color=MUTED, va="center", fontweight="bold")
    fig.text(0.04, 0.905, title, fontsize=27 if len(title) <= 56 else 23, fontweight="bold", color=INK, va="top")
    if source:
        fig.text(0.04, 0.025, source, fontsize=9, color=MUTED, va="center")
    return fig, 0.8


def bullets(fig, x, y, items, width, fs=16, gap=0.03):
    """Bulleted lines; returns the y below the last one."""
    for t in items:
        t = fit(t, width - 0.025, fs)
        fig.text(x, y, "•", fontsize=fs, color=INK, va="top")
        fig.text(x + 0.022, y, t, fontsize=fs, color=INK, va="top", linespacing=1.3)
        y -= 0.042 * nlines(t) * fs / 16 + gap
    return y


def callout(fig, x, y, w, text, fs=12.5):
    """Key-finding box with a dark left rule; returns its bottom."""
    t = fit(text, w - 0.03, fs, bold=True)
    h = 0.032 * nlines(t) * fs / 12.5 + 0.03
    fig.patches.append(mpatches.Rectangle((x, y - h), w, h, transform=fig.transFigure, fc="#f3f2ee", ec="none"))
    fig.patches.append(mpatches.Rectangle((x, y - h), 0.004, h, transform=fig.transFigure, fc=INK, ec="none"))
    fig.text(x + 0.016, y - 0.015, t, fontsize=fs, fontweight="bold", color=INK, va="top", linespacing=1.3)
    return y - h


def wrap(s, n):
    return "\n".join(textwrap.fill(p, n) for p in s.split("\n"))


def fit(s, width, fs, bold=False):
    """Wrap to a width given as a fraction of the 13.333 in slide (DejaVu Sans, ~0.6 em per character)."""
    return wrap(s, max(10, int(width * 13.333 * 72 / (fs * (0.64 if bold else 0.58)))))


def nlines(s):
    return s.count("\n") + 1


def rule(fig, y, x0=0.04, x1=0.96):
    fig.add_artist(v5.plt.Line2D([x0, x1], [y, y], transform=fig.transFigure, color=GRID, lw=1))


def map_panel(ax, mask):
    """Lightened 2026 imagery; the area an approach reports as new in 2026, colored by what other data show."""
    x0, x1, y0, y1 = v5.window()
    ax.imshow(0.45 + 0.55 * v5.IMG26.mean(-1, keepdims=True).repeat(3, -1) * 0.9, extent=(0, EXT_KM, 0, EXT_KM),
              interpolation="nearest")
    for c in EVID:
        overlay(ax, mask & CLS[c], COL[c], alpha=0.9)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(INK)
        s.set_linewidth(1.2)


def pct_label(p):
    return f"{p:.1f}%" if p < 1 else f"{p:.0f}%"


def stack(fig, x, y, w, h, k, vmax):
    """Horizontal stacked bar of reported km² by evidence class, scaled to vmax km² (so bars stay proportional
    across panels). Each segment is labeled with its share of that bar's total: inside where it fits, otherwise
    above the bar with a short leader, nudged right so neighboring labels don't overlap."""
    ax = fig.add_axes([x, y, w, h])
    left, above = 0, []
    for c in EVID:
        v = NUM[k][c]
        ax.barh(0, v, left=left, color=COL[c], height=1, ec="white", lw=0.8)
        share = NUM[k]["share_pct"][c]
        seg_w = w * v / vmax  # segment width in figure coordinates
        cx = x + w * (left + v / 2) / vmax
        if seg_w >= 0.025:
            fig.text(cx, y + h / 2, pct_label(share), fontsize=9.5, fontweight="bold", va="center", ha="center",
                     color=INK if c == "y2025" else "white")
        else:
            above.append((cx, share, c))
        left += v
    ax.set_xlim(0, vmax)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    lx_min = x
    for cx, share, c in above:
        lx = max(cx, lx_min + 0.012)
        ly = y + h + 0.018
        fig.add_artist(v5.plt.Line2D([cx, cx, lx], [y + h, y + h + 0.007, ly - 0.004], transform=fig.transFigure,
                                     color=COL[c], lw=1.2))
        fig.text(lx, ly, pct_label(share), fontsize=9, fontweight="bold", color=INK, va="bottom", ha="center")
        lx_min = lx + 0.016


# Slide text is kept to the takeaway. The explanations a presenter needs are in figures_v7/SPEAKER_NOTES.md.

# ---------------------------------------------------------------- 0: introduction
def s0():
    fig = figure()
    fig.text(0.06, 0.74, "BULC-D: Follow-up Results", fontsize=40, fontweight="bold", color=INK, va="top")
    rule(fig, 0.6, x0=0.06, x1=0.6)
    qs = ["Can we distinguish new disturbances from older ones?",
          "How does the expectation period affect detection?",
          "Is BULC-D responding correctly?"]
    y = 0.52
    for i, q in enumerate(qs, 1):
        fig.text(0.06, y, str(i), fontsize=26, fontweight="bold", color=INK, va="top")
        fig.text(0.11, y - 0.003, q, fontsize=21, color=INK, va="top")
        y -= 0.12
    save(fig, "00_introduction.png")


# ---------------------------------------------------------------- 1: disturbance timing
def s1():
    fig, y = slide("1 · Disturbance timing", "Tracking first detections helps identify recent changes")
    panels = [
        ("orig", "Single-year run", "Expectation 2018–2023"),
        ("multi", "Multi-year detection", "Expectation 2018–2023\nfirst detected in 2026"),
        ("recent", "Recent expectation", "Expectation 2024–2025"),
    ]
    w, gap = 0.205, 0.025
    top = y - 0.01
    h = w * 13.333 / 7.5 * 0.98
    vmax = max(NUM[k]["km2"] for k in REPORT)
    for i, (k, t, sub) in enumerate(panels):
        x = 0.04 + i * (w + gap)
        fig.text(x, top, t, fontsize=15, fontweight="bold", color=INK, va="top")
        fig.text(x, top - 0.04, sub, fontsize=10.5, color=INK2, va="top", linespacing=1.2)
        mt = top - 0.095
        aw = h * 7.5 / 13.333
        ax = fig.add_axes([x + (w - aw) / 2, mt - h, aw, h])
        map_panel(ax, REPORT[k])
        by = mt - h - 0.068
        stack(fig, x, by, w, 0.032, k, vmax)
        fig.text(x, by - 0.014, f"{NUM[k]['km2']:.1f} km²", fontsize=16, color=INK, va="top", fontweight="bold")
    x0, cw = 0.73, 0.24
    ly = top - 0.01
    for j, c in enumerate(EVID):
        swatch(fig, x0, ly - j * 0.04, COL[c], LAB[c].replace(", 2018–2024", "\n2018–2024"), fontsize=10.5)
    callout(fig, x0, ly - 4 * 0.04 - 0.04, cw,
            f"Multi-year detection reduces the area flagged as 2026 vegetation decrease by "
            f"{100 * (1 - NUM['multi']['km2'] / NUM['orig']['km2']):.0f}% ({NUM['orig']['km2']:.1f} → "
            f"{NUM['multi']['km2']:.1f} km²), helping separate newly detected changes from older disturbances.",
            fs=13)
    fig.text(0.04, 0.07, "First detection is not necessarily the disturbance date.", fontsize=11.5, color=INK2,
             va="top", style="italic")
    save(fig, "01_disturbance_timing.png")


# ---------------------------------------------------------------- 2: expectation period
def s2():
    fig, y = slide("2 · Expectation period", "Reference years strongly affect detection")
    s = N_["share_flagged_by_loss_year"]
    years = list(range(2018, 2027))
    fig.text(0.04, y + 0.01, "Forest loss still detected in 2026, by loss year", fontsize=14, color=INK2, va="top")
    ax = fig.add_axes([0.105, 0.13, 0.55, y - 0.18])
    ax.set_xlim(2017.5, 2026.6)
    ax.set_ylim(-0.6, 2.8)
    ax.axis("off")
    for row, k in enumerate("ABC"):
        yy = 2 - row
        a, b = v5.NORMAL[k]
        ax.add_patch(mpatches.FancyBboxPatch((a - 0.46, yy - 0.5), b - a + 0.92, 0.95, boxstyle="round,pad=0.02",
                                             fc="#e9e7e1", ec="none"))
        ax.text(2017.25, yy + 0.08, k, fontsize=19, fontweight="bold", color=INK, ha="right", va="center")
        ax.text(2017.25, yy - 0.3, f"{a}–{b}", fontsize=9.5, color=INK2, ha="right", va="center")
        for yr in years:
            v, col = (N_["s26_flagged"][k]["pct"], COL["s26"]) if yr == 2026 else \
                (s[k][yr], COL["y2025"] if yr == 2025 else COL["hist"])
            ax.add_patch(mpatches.Circle((yr, yy + 0.1), 0.3, fc="white", ec=GRID, lw=1))
            ax.add_patch(mpatches.Circle((yr, yy + 0.1), max(0.3 * np.sqrt(v / 100), 0.025), fc=col, ec="none"))
            ax.text(yr, yy - 0.32, f"{v:.0f}%", fontsize=12, color=INK, fontweight="bold", ha="center", va="center")
    for yr in years[:-1]:
        ax.text(yr, 2.62, str(yr), ha="center", fontsize=11.5, color=INK)
    ax.text(2026, 2.55, "2026\ndecline", ha="center", fontsize=11, color=COL["s26"], fontweight="bold", va="bottom")
    ax.axvline(2025.5, color=INK2, lw=1, ls=(0, (3, 3)), ymin=0.05, ymax=0.93)
    fig.patches.append(mpatches.FancyBboxPatch((0.04, 0.075), 0.022, 0.03, boxstyle="round,pad=0.002",
                                               transform=fig.transFigure, fc="#e9e7e1", ec="none"))
    fig.text(0.07, 0.09, "Shaded years = expectation period", fontsize=12, color=INK2, va="center")
    lo, hi = (f(N_["s26_flagged"][k]["pct"] for k in "ABC") for f in (min, max))
    cy = callout(fig, 0.69, y - 0.08, 0.27, f"Recent vegetation decline detection remains consistent "
                 f"({lo:.0f}–{hi:.0f}%) across expectation periods, while detection of older disturbances varies "
                 f"substantially.", fs=14)
    note = fit("Recent decline was defined as a Sentinel-2 NBR decrease of ≥0.20 in 2026, compared with pre-decline "
               "conditions.", 0.27, 11)
    fig.text(0.69, cy - 0.03, note, fontsize=11, color=INK2, va="top", linespacing=1.3)
    fig.text(0.69, cy - 0.045 - 0.026 * nlines(note), fit(f"{lo:.0f}–{hi:.0f}% = share of the observed Sentinel-2 "
             "decline area also detected by BULC-D, not independently validated accuracy.", 0.27, 11), fontsize=11,
             color=INK2, va="top", style="italic", linespacing=1.3)
    save(fig, "02_expectation_period.png")


# ---------------------------------------------------------------- 3: algorithm behavior
def s3():
    fig, y = slide("3 · Algorithm behavior", "Implementation verified; detection accuracy still needs testing",
                   source=None)
    cols = [
        ("Implementation", ["Matches original BULC-D."]),
        ("Sensitivity", ["Parameter setting explains weak response in tests.",
                         "Original meeting pixel still needs checking."]),
        ("Seasonal effects", ["Snowmelt can trigger temporary detections.",
                              "End-of-season filtering reduces brief detections."]),
    ]
    cw, gx = 0.28, 0.04
    top = y - 0.12
    for i, (head, items) in enumerate(cols):
        x = 0.04 + i * (cw + gx)
        fig.text(x, top, head, fontsize=20, fontweight="bold", color=INK, va="top")
        rule(fig, top - 0.065, x, x + cw)
        bullets(fig, x, top - 0.1, items, cw, fs=18, gap=0.04)
    save(fig, "03_algorithm_behavior.png")


# ---------------------------------------------------------------- 4: conclusions
def s4():
    fig = figure()
    fig.text(0.04, 0.905, "Conclusions and Next Steps", fontsize=27, fontweight="bold", color=INK, va="top")
    for x, head, items in [
        (0.04, "Findings", ["BULC-D captures about 90% of strong 2026 Sentinel-2 declines.",
                            "First-detection tracking reduces older detections.",
                            "Expectation periods strongly influence results.",
                            "Algorithm verified; accuracy remains untested."]),
        (0.53, "Next steps", ["Close the remaining gap, aiming for 99% detection.",
                              "Test the proposed 2-of-3 reference-year comparison.",
                              "Revisit the September meeting pixel.",
                              "Validate detection accuracy and timing."]),
    ]:
        fig.text(x, 0.72, head, fontsize=20, fontweight="bold", color=INK, va="top")
        rule(fig, 0.655, x, x + 0.43)
        bullets(fig, x, 0.61, items, 0.43, fs=17, gap=0.035)
    save(fig, "04_findings_next_steps.png")


if __name__ == "__main__":
    print(json.dumps(NUM, indent=1, default=float))
    s0()
    s1()
    s2()
    s3()
    s4()

"""Meeting figures v3 (prototype: Figures 4 and 5). Read-only; uses existing results only.

    python meeting_2026-10-28/scripts/make_figures_v3.py

Writes figures_v3/*.png (2666 x 1500) and data/figures_v3_numbers.json. figures/ and figures_v2/ are untouched.

BULC-D results: full-year runs (expectation and monitoring DOY 1-362; 2026 = year to date through Oct 27),
data/fullyear/{A26,B26,C26}.npz. "Flagged" = 2026 outcome decrease (confirmed rule).
Every flagged pixel is classed by independent evidence BULC-D never used, never by BULC-D's own dates:
  earlier   Hansen GFC v1.13 forest loss 2018-2024
  y2025     Hansen forest loss 2025
  s2_2026   Sentinel-2 NBR fell >= 0.2 from late 2025 to late 2026 (Sep 15-Oct 27 composites), no Hansen
            loss 2018-2025: independently SUPPORTED 2026 change; its timing is not verified
  none      no independent record of change
Hansen takes precedence: an earlier-loss pixel that also declines in 2026 stays in its Hansen class (counted
in the numbers file as possible repeat disturbance).
"""
import json

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from make_figures import DATA, EXT_KM, GRID, HERE, INK, INK2, MUTED, PX_KM2, base_map, figure, land, overlay, swatch

OUT = HERE / "figures_v3"
OUT.mkdir(exist_ok=True)
CFG_NAME = {"A": "A · normal = 2018–2023", "B": "B · normal = 2024–2025", "C": "C · normal = 2018–2025"}
CFG_SHORT = {"A": "A  (2018–2023)", "B": "B  (2024–2025)", "C": "C  (2018–2025)"}
EARLY, Y25, S26, NONE = "#2a78d6", "#eda100", "#e34948", "#52514e"  # validated all-pairs (dataviz) + neutral
SOFT = "#f6f5f2"

F = {k: np.load(DATA / "fullyear" / f"{k}26.npz") for k in "ABC"}
R = np.load(DATA / "reference.npz")
flag = {k: land & (F[k]["outcome"] == 0) for k in "ABC"}
loss = R["hansen_lossyear"].astype(int)
dl = R["late2026_nbr"] - R["late2025_nbr"]
hansen = land & (loss >= 18) & (loss <= 25)
CLASS = {"earlier": land & (loss >= 18) & (loss <= 24),
         "y2025": land & (loss == 25),
         "s2_2026": land & (dl < -0.2) & ~hansen}
CLASS["none"] = land & ~hansen & ~CLASS["s2_2026"]
CLASS_STYLE = [("earlier", EARLY, "Forest loss recorded 2018–2024"),
               ("y2025", Y25, "Forest loss recorded 2025"),
               ("s2_2026", S26, "Declined in 2026 in Sentinel-2, no earlier loss record"),
               ("none", NONE, "No independent record of change")]
ROWS = [("2018–2021", (loss >= 18) & (loss <= 21)), ("2022–2023", (loss >= 22) & (loss <= 23)),
        ("2024", loss == 24), ("2025", loss == 25)]
# where each Hansen year falls relative to each version's "normal" (the 2026 monitoring year is always after it)
WHERE = {"A": ["inside normal", "inside normal", "gap: after normal", "gap: after normal"],
         "B": ["before normal", "before normal", "inside normal", "inside normal (its last year)"],
         "C": ["inside normal", "inside normal", "inside normal", "inside normal (its last year)"]}
WIN = (270, 110, 200)  # zoom window: row, col, size in pixels (6 x 6 km); densest mix of the three cases


def km2(m):
    return float((m & land).sum() * PX_KM2)


def pct(m, within):
    return float(100 * (m & within & land).sum() / max(1, (within & land).sum()))


def save(fig, name):
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)
    print("wrote", OUT / name)


def header(fig, title, subtitle):
    fig.text(0.04, 0.94, title, fontsize=21, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.875, subtitle, fontsize=14, color=INK2, va="top", linespacing=1.35)


def footer(fig, text, y=0.05):
    fig.text(0.04, y, text, fontsize=10, color=MUTED, va="top", linespacing=1.4)


N_ = {
    "flagged_km2": {k: km2(flag[k]) for k in "ABC"},
    "flagged_by_class_km2": {k: {c: km2(flag[k] & m) for c, m in CLASS.items() if c != "none"} | {
        "none": km2(flag[k] & CLASS["none"])} for k in "ABC"},
    "class_km2": {c: km2(m) for c, m in CLASS.items()},
    "row_km2": {g: km2(m) for g, m in ROWS},
    "row_flagged_pct": {k: {g: pct(flag[k], m) for g, m in ROWS} for k in "ABC"},
    "row_flagged_km2": {k: {g: km2(flag[k] & m) for g, m in ROWS} for k in "ABC"},
    "earlier_all_flagged_pct": {k: pct(flag[k], hansen) for k in "ABC"},
    "earlier_all_flagged_km2": {k: km2(flag[k] & hansen) for k in "ABC"},
    "s2_2026_flagged_pct": {k: pct(flag[k], CLASS["s2_2026"]) for k in "ABC"},
    "s2_2026_flagged_km2": {k: km2(flag[k] & CLASS["s2_2026"]) for k in "ABC"},
    "repeat_candidates_km2": {k: km2(flag[k] & hansen & (dl < -0.2)) for k in "ABC"},
    "window_rc_size": WIN,
}
(DATA / "figures_v3_numbers.json").write_text(json.dumps(N_, indent=1))
FOOT_RUN = ("Oregon Coast Range pilot, 400 km², 30 m pixels. BULC-D on Landsat 8/9, whole year used to learn normal "
            "and to monitor; 2026 = Jan 1–Oct 27. No forest mask.")
FOOT_EVID = ("Forest loss years: Hansen Global Forest Change v1.13 (through 2025). Sentinel-2 decline: burn ratio "
             "(NBR) fell by ≥ 0.2, Sep 15–Oct 27 2025 to same dates 2026.\nBoth are independent satellite "
             "products BULC-D never used. They support that change happened; neither is a verified disturbance date.")


# ---------------------------------------------------------------- Figure 4: same place, three answers
def fig04_maps():
    fig = figure()
    nb = N_["flagged_by_class_km2"]
    header(fig, "Same stands, three answers: A re-flags past harvests, B mostly does not",
           "Colored areas are what BULC-D flags as a 2026 decrease. The color says what independent satellite "
           "records show happened there.")
    r, c, s = WIN
    x0, x1 = c * 0.03, (c + s) * 0.03
    y1 = EXT_KM - r * 0.03
    y0 = y1 - s * 0.03
    w, gap, top = 0.258, 0.025, 0.81
    h = w * 13.333 / 7.5
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * (w + gap), top - h, w, h])
        base_map(ax)
        for key, col, _ in CLASS_STYLE:
            overlay(ax, flag[k] & CLASS[key], col)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_title(CFG_NAME[k], loc="left", fontsize=14.5, fontweight="bold", color=INK, pad=6)
        if i == 0:  # 1 km scale bar
            ax.add_patch(mpatches.Rectangle((x0 + 0.25, y0 + 0.3), 1, 0.08, color=INK, zorder=6))
            ax.text(x0 + 0.75, y0 + 0.45, "1 km", ha="center", va="bottom", fontsize=11, color=INK, zorder=6)
    # locator: the whole pilot, window outlined
    lx = 0.04 + 3 * (w + gap) - 0.012
    loc = fig.add_axes([lx + 0.01, top - 0.16, 0.08, 0.08 * 13.333 / 7.5])
    base_map(loc)
    for s_ in loc.spines.values():
        s_.set_linewidth(0.8)
    loc.add_patch(mpatches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=S26, lw=1.6))
    fig.text(lx + 0.01, top - 0.17, "Red box: window\nshown, within the\n20 × 20 km pilot", fontsize=10, color=INK2, va="top")

    # legend
    ly = top - h - 0.04
    for j, (key, col, lab) in enumerate(CLASS_STYLE):
        swatch(fig, [0.04, 0.40, 0.04, 0.40][j], ly - 0.037 * (j // 2), col, lab, fontsize=12)
    # whole-area bars, one shared km² scale
    by = ly - 0.13
    fig.text(0.04, by + 0.045, "Flagged area in the whole 400 km² pilot (km²)", fontsize=12.5, color=INK,
             fontweight="bold", va="bottom")
    xmax = max(N_["flagged_km2"].values())
    for i, k in enumerate("ABC"):
        bx = fig.add_axes([0.04 + i * (w + gap), by - 0.01, w, 0.045])
        left = 0
        for key, col, _ in CLASS_STYLE:
            v = nb[k][key]
            bx.barh(0, v, left=left, color=col, height=1, edgecolor="white", lw=1.5)
            if v >= 2.2:
                bx.text(left + v / 2, 0, f"{v:.0f}", ha="center", va="center", fontsize=11.5, fontweight="bold",
                        color=INK if key == "y2025" else "white")
            left += v
        bx.text(left + 0.4, 0, f"{left:.0f} km²", va="center", fontsize=12, color=INK, fontweight="bold")
        bx.set_xlim(0, xmax * 1.22)
        bx.set_ylim(-0.5, 0.5)
        bx.axis("off")
    footer(fig, FOOT_EVID + "\n" + FOOT_RUN + "\nFewer flagged km² is not by itself more accurate.", y=0.105)
    save(fig, "04_same_place_three_answers.png")


# ---------------------------------------------------------------- Figure 5: earlier vs 2026
def fig05_grid():
    fig = figure()
    header(fig, "All three catch ~90% of supported 2026 declines; they differ on past loss",
           "For each kind of place (rows), the share that BULC-D flags as a 2026 decrease under each version of "
           "\"normal\" (columns).")
    col_x = [0.30, 0.52, 0.74]
    cw = 0.17
    for k, x in zip("ABC", col_x):
        fig.text(x, 0.80, CFG_SHORT[k], fontsize=15, fontweight="bold", color=INK, va="bottom")
    rows = [(f"Forest loss recorded {g}", m, EARLY if g != "2025" else Y25, WHERE, i) for i, (g, m) in enumerate(ROWS)]
    ys = [0.715, 0.63, 0.545, 0.46]

    def cell(x, y, v, km, col, tag=None, big=False):
        ax = fig.add_axes([x, y - 0.018, cw, 0.036])
        ax.barh(0, 100, color=GRID, height=1)
        ax.barh(0, v, color=col, height=1)
        ax.set_xlim(0, 100)
        ax.set_ylim(-0.5, 0.5)
        ax.axis("off")
        fig.text(x + cw + 0.006, y, f"{v:.0f}%", fontsize=15 if big else 14, fontweight="bold", color=INK,
                 va="center")
        fig.text(x, y - 0.026, f"{km:.1f} km²" + (f"  ·  {tag}" if tag else ""), fontsize=10, color=INK2, va="top")

    fig.text(0.04, 0.775, "PAST DISTURBANCES: flagging these is not new 2026 change", fontsize=11.5, color=MUTED,
             fontweight="bold", va="bottom")
    for (lab, m, col, where, i), y in zip(rows, ys):
        fig.text(0.04, y, lab, fontsize=13.5, color=INK, va="center")
        fig.text(0.04, y - 0.026, f"{N_['row_km2'][ROWS[i][0]]:.1f} km² in the pilot", fontsize=10, color=INK2,
                 va="top")
        for k, x in zip("ABC", col_x):
            cell(x, y, N_["row_flagged_pct"][k][ROWS[i][0]], N_["row_flagged_km2"][k][ROWS[i][0]], col,
                 tag=where[k][i])
    y = 0.375
    fig.lines.append(plt.Line2D([0.04, 0.96], [y + 0.04, y + 0.04], transform=fig.transFigure, color=GRID, lw=1))
    fig.text(0.04, y, "All past forest loss, 2018–2025", fontsize=13.5, color=INK, va="center", fontweight="bold")
    fig.text(0.04, y - 0.026, f"{km2(hansen):.1f} km² in the pilot", fontsize=10, color=INK2, va="top")
    for k, x in zip("ABC", col_x):
        cell(x, y, N_["earlier_all_flagged_pct"][k], N_["earlier_all_flagged_km2"][k], MUTED, big=True)

    y = 0.235
    fig.text(0.04, y + 0.06, "SUPPORTED 2026 CHANGE: flagging these is the goal", fontsize=11.5, color=MUTED,
             fontweight="bold", va="bottom")
    fig.text(0.04, y, "Declined in 2026 in Sentinel-2,\nno earlier loss record", fontsize=13.5, color=INK,
             va="center", fontweight="bold", linespacing=1.15)
    fig.text(0.04, y - 0.042, f"{km2(CLASS['s2_2026']):.1f} km² in the pilot", fontsize=10, color=INK2, va="top")
    for k, x in zip("ABC", col_x):
        cell(x, y, N_["s2_2026_flagged_pct"][k], N_["s2_2026_flagged_km2"][k], S26, big=True)
    footer(fig, "Gray tags: where that loss year falls relative to the years each version learns \"normal\" from "
                "(\"gap\" = between the end of normal and 2026).\nNot shown: flagged area with no independent record "
                f"(A {N_['flagged_by_class_km2']['A']['none']:.1f}, B {N_['flagged_by_class_km2']['B']['none']:.1f}, "
                f"C {N_['flagged_by_class_km2']['C']['none']:.1f} km²): false alarms or subtle real change, "
                "unknown which. Only strong declines tested.\n" + FOOT_EVID + "\n" + FOOT_RUN, y=0.125)
    save(fig, "05_past_vs_2026.png")


if __name__ == "__main__":
    fig04_maps()
    fig05_grid()
    print(json.dumps(N_, indent=1))

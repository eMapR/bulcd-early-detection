"""Meeting figures v5: seven slides, one per research question, plus a short appendix (read-only).

    python meeting_2026-10-28/scripts/make_figures_v5.py

Writes figures_v5/*.png (2666 x 1500) and data/figures_v5_numbers.json. Earlier figure folders are untouched.
v5 = v4 with Q6/Q7 rebuilt around detection timing and small wording changes to Q1, Q2, Q4, Q5.

BULC-D results: full-year runs for A, B, C (expectation and monitoring DOY 1-362; 2026 = year to date through
Oct 27), data/fullyear/{A26,B26,C26}.npz; A24/A25 (config A, earlier target years) for the year check in Q7.
"Flagged" = 2026 outcome decrease (confirmed rule). "Detection date" = start of the final decrease episode
(last_ep; bin END date), i.e. when the detection that is still standing began.
Independent evidence (never used by BULC-D; satellite estimates, not verified disturbance dates):
  historical forest loss   Hansen GFC v1.13 loss year 2018-2024
  2025 forest loss         Hansen loss year 2025
  2026 spectral decline    Sentinel-2 NBR fell >= 0.2 from late 2025 to late 2026 (Sep 15-Oct 27 composites),
                           no Hansen loss 2018-2025
  S2 decline month         first 2026 month whose S2 NBR is >= 0.25 below the same month of 2025 and stays
                           >= 0.2 below in the next month (monthly medians, data/monthly_s2.npz)
Benchmark (Q1): data/bench_fullyear.json from bench_fullyear_tile.py (one tile, full year, A/B/C).
Timing (Q6, Q7), per 2026-spectral-decline pixel, on a month index Nov 2025 .. Oct 2026 (data/monthly_s2.npz and
data/monthly_s2_late.npz; each month compared with the same month a year earlier):
  first observed change   first month >= 0.25 below, still >= 0.2 below the next month (or the late composite)
  last unchanged month    latest earlier month within 0.1 of the year before
  actual disturbance      unknown; somewhere between the two (monthly medians, so +/- about a month)
  first BULC-D detection  first 4-day window with P(decrease) > 0.65 in 2026 (first_dec, any outcome)
"""
import json

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from make_figures import DATA, EXT_KM, GRID, HERE, INK, INK2, LAND, MUTED, PX_KM2, WATER, base_map, figure, land, \
    overlay, swatch

OUT = HERE / "figures_v5"
OUT.mkdir(exist_ok=True)
NAMES = {"A": "A · normal = 2018–2023", "B": "B · normal = 2024–2025", "C": "C · normal = 2018–2025"}
SHORT = {"A": "A (2018–2023)", "B": "B (2024–2025)", "C": "C (2018–2025)"}
NORMAL = {"A": (2018, 2023), "B": (2024, 2025), "C": (2018, 2025)}
CFG = {"A": "#6250d6", "B": "#1baf7a", "C": "#eb6834"}            # validated all-pairs (dataviz)
HIST, Y25, S26, NONE = "#2a78d6", "#eda100", "#e34948", "#52514e"  # validated all-pairs (dataviz) + neutral
SOFT = "#f6f5f2"
LAB = {"hist": "Historical forest loss (2018–2024)", "y2025": "2025 forest loss",
       "s26": "2026 spectral decline", "none": "No independent record"}

F = {k: np.load(DATA / "fullyear" / f"{k}.npz") for k in ("A26", "B26", "C26", "A25", "A24")}
R = np.load(DATA / "reference.npz")
M = np.load(DATA / "monthly_s2.npz")
ML = np.load(DATA / "monthly_s2_late.npz")
RGB = np.load(DATA / "rgb_2023_2024.npz")
BENCH = json.loads((DATA / "bench_fullyear.json").read_text())
flag = {k: land & (F[k + "26"]["outcome"] == 0) for k in "ABC"}
loss = R["hansen_lossyear"].astype(int)
dl = R["late2026_nbr"] - R["late2025_nbr"]
hansen = land & (loss >= 18) & (loss <= 25)
CLS = {"hist": land & (loss >= 18) & (loss <= 24), "y2025": land & (loss == 25),
       "s26": land & (dl < -0.2) & ~hansen}
CLS["none"] = land & ~hansen & ~CLS["s26"]
COL = {"hist": HIST, "y2025": Y25, "s26": S26, "none": NONE}
WIN = (270, 110, 200)  # zoom window (row, col, size px = 6 x 6 km); densest mix of the three evidence classes

# S2 decline month (1-10) for 2026 spectral-decline pixels; 0 = no monthly decline found
dm = np.stack([M[f"nbr_2026_{m:02d}"] - M[f"nbr_2025_{m:02d}"] for m in range(1, 11)])
hit = (dm < -0.25) & np.concatenate([dm[1:] < -0.2, (dl < -0.2)[None]], 0)
s2_month = np.where(hit.any(0), hit.argmax(0) + 1, 0)
det_doy = {k: np.where(flag[k] & (F[k + "26"]["last_ep"] // 1000 == 2026), F[k + "26"]["last_ep"] % 1000, 0)
           for k in "ABC"}
MONTH_END = np.cumsum([31, 28, 31, 30, 31, 30, 31, 31, 30, 31])  # 2026 is not a leap year
MLAB = ["Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]  # index 0..11
# Landsat 8/9 scenes over the pilot, Jan-Apr 2026, at least half clear (QA bits 0-4); Earth Engine query 2026-10-28
CLEAR_LANDSAT = ["2026-01-19", "2026-02-04", "2026-02-05", "2026-03-16", "2026-04-09", "2026-04-18", "2026-04-25",
                 "2026-04-26"]

# independent change timing (month index 0 = Nov 2025 ... 11 = Oct 2026)
dmon = np.stack([ML["nbr_2025_11"] - ML["nbr_2024_11"], ML["nbr_2025_12"] - ML["nbr_2024_12"]] + list(dm))
seen = (dmon < -0.25) & np.concatenate([dmon[1:] < -0.2, (dl < -0.2)[None]], 0)
S2_FIRST = np.where(seen.any(0), seen.argmax(0), -1)
_idx = np.arange(12)[:, None, None]
_unch = (dmon > -0.1) & (_idx < S2_FIRST[None])
S2_LAST_UNCH = np.where(_unch.any(0), 11 - np.argmax(_unch[::-1], 0), -1)
first_det = {}  # month index of the first BULC-D detection in 2026; -1 = none
for _k in "ABC":
    _fd = F[_k + "26"]["first_dec"]
    _doy = np.where(_fd // 1000 == 2026, _fd % 1000, 0)
    first_det[_k] = np.where(_doy > 0, np.searchsorted(MONTH_END, _doy, side="left") + 2, -1)


def doy_month(doy):
    return np.searchsorted(MONTH_END, doy, side="left") + 1


def km2(m):
    return float((m & land).sum() * PX_KM2)


def pct(m, within):
    return float(100 * (m & within & land).sum() / max(1, (within & land).sum()))


# ---------------------------------------------------------------- numbers
def bench(k):
    b = BENCH[f"bench-fullyear-{k}_r0056c0034"]
    if b["state"] != "SUCCEEDED":
        return None
    t0, t1 = (np.datetime64(b[x].rstrip("Z")) for x in ("start", "end"))
    return {"eecu_s": b["eecu_s"], "minutes": float((t1 - t0) / np.timedelta64(1, "s") / 60)}


month_diff = {}
for k in "ABC":
    m = CLS["s26"] & (det_doy[k] > 0) & (s2_month > 0)
    d = doy_month(det_doy[k][m]) - s2_month[m]
    month_diff[k] = {"n_km2": km2(m), "earlier2": 100 * np.mean(d <= -2), "earlier1": 100 * np.mean(d == -1),
                     "same": 100 * np.mean(d == 0), "later1": 100 * np.mean(d == 1), "later2": 100 * np.mean(d >= 2)}
def timing_cats(k, within):
    """Where the first BULC-D detection falls relative to the independent change window, % of `within`."""
    b, f, u = first_det[k][within], S2_FIRST[within], S2_LAST_UNCH[within]
    det = b >= 0
    return {"before_change": 100 * np.mean(det & (b <= u)), "in_window": 100 * np.mean(det & (b > u) & (b <= f)),
            "next_month": 100 * np.mean(det & (b == f + 1)), "later": 100 * np.mean(det & (b >= f + 2)),
            "not_flagged": 100 * np.mean(~det), "n_km2": km2(within)}


S26_2026 = CLS["s26"] & (S2_FIRST >= 2)            # change first seen in Jan-Oct 2026
SEASONS = {"Jan–Feb": (2, 3), "Mar–May": (4, 6), "Jun–Aug": (7, 9), "Sep–Oct": (10, 11)}
o24, o25 = (land & (F[k]["outcome"] == 0) for k in ("A24", "A25"))
first_year_A = np.where(o24, 2024, np.where(o25, 2025, np.where(flag["A"], 2026, 0)))
N_ = {
    "bench_fullyear_tile": {k: bench(k) for k in "ABC"},
    "class_km2": {c: km2(m) for c, m in CLS.items()},
    "flagged_km2": {k: km2(flag[k]) for k in "ABC"},
    "flagged_by_class_km2": {k: {c: km2(flag[k] & m) for c, m in CLS.items()} for k in "ABC"},
    "share_flagged_by_loss_year": {k: {2000 + y: pct(flag[k], loss == y) for y in range(18, 26)} for k in "ABC"},
    "loss_year_km2": {2000 + y: km2(loss == y) for y in range(18, 26)},
    "hist_flagged": {k: {"pct": pct(flag[k], CLS["hist"]), "km2": km2(flag[k] & CLS["hist"])} for k in "ABC"},
    "y2025_flagged": {k: {"pct": pct(flag[k], CLS["y2025"]), "km2": km2(flag[k] & CLS["y2025"])} for k in "ABC"},
    "s26_flagged": {k: {"pct": pct(flag[k], CLS["s26"]), "km2": km2(flag[k] & CLS["s26"])} for k in "ABC"},
    "s26_all_three": pct(flag["A"] & flag["B"] & flag["C"], CLS["s26"]),
    "s26_none": pct(~(flag["A"] | flag["B"] | flag["C"]), CLS["s26"]),
    "s26_detected_by_month_end_pct": {k: [pct(CLS["s26"] & (det_doy[k] > 0) & (det_doy[k] <= e), CLS["s26"])
                                          for e in MONTH_END] for k in "ABC"},
    "s26_s2_month_by_month_end_pct": [pct((s2_month > 0) & (s2_month <= m), CLS["s26"]) for m in range(1, 11)],
    "month_diff": month_diff,
    "year_check_A": {"hansen2024_first_flag_2024": pct(first_year_A == 2024, loss == 24),
                     "hansen2025_first_flag_2025": pct(first_year_A == 2025, loss == 25)},
    "repeat_candidates_km2": {k: km2(flag[k] & hansen & (dl < -0.2)) for k in "ABC"},
    "s26_first_seen_pct": {"late_2025": pct((S2_FIRST >= 0) & (S2_FIRST <= 1), CLS["s26"]),
                           "jan_2026": pct(S2_FIRST == 2, CLS["s26"]), "feb_oct_2026": pct(S2_FIRST >= 3, CLS["s26"]),
                           "not_found": pct(S2_FIRST < 0, CLS["s26"])},
    "timing_vs_window": {k: timing_cats(k, S26_2026) for k in "ABC"},
    "timing_by_season": {k: {s_: timing_cats(k, S26_2026 & (S2_FIRST >= a) & (S2_FIRST <= b))
                             for s_, (a, b) in SEASONS.items()} for k in "ABC"},
    "before_change_months_early_median": {k: float(np.median((S2_FIRST - first_det[k])[S26_2026 & (first_det[k] >= 0)
                                                                                     & (first_det[k] <= S2_LAST_UNCH)]))
                                          for k in "ABC"},
    "late2025_first_bulcd_month": {k: {MLAB[i]: pct(first_det[k] == i, CLS["s26"] & (S2_FIRST >= 0) & (S2_FIRST <= 1))
                                       for i in range(2, 12)} for k in "ABC"},
}
(DATA / "figures_v5_numbers.json").write_text(json.dumps(N_, indent=1, default=float))
NB = N_["flagged_by_class_km2"]

FOOT_RUN = ("Oregon Coast Range pilot, 400 km², 30 m. BULC-D on Landsat 8/9; whole year used to learn \"normal\" "
            "and to monitor; 2026 = Jan 1–Oct 27.")
FOOT_EVID = ("Historical and 2025 forest loss: Hansen Global Forest Change v1.13. 2026 spectral decline: "
             "Sentinel-2 burn ratio fell ≥ 0.2 (late 2025 → late 2026), no earlier Hansen loss.\nIndependent "
             "satellite estimates BULC-D never used; they indicate change, not verified disturbance dates.")


# ---------------------------------------------------------------- layout helpers
def save(fig, name):
    fig.savefig(OUT / name, dpi=200)
    plt.close(fig)
    print("wrote", OUT / name)


def header(fig, q, question, answer, title, subtitle=None):
    """Question line with an answer chip, the answer as the title, optional one-line subtitle."""
    chip = fig.text(0.04, 0.955, f" {answer.upper()} ", fontsize=13, fontweight="bold", color="white", va="top",
                    bbox=dict(boxstyle="round,pad=0.35", fc=INK, ec="none"))
    fig.canvas.draw()
    x = fig.transFigure.inverted().transform(chip.get_window_extent())[1, 0] + 0.012
    fig.text(x, 0.955, f"Q{q}  ·  {question}", fontsize=13, color=INK2, va="top", fontweight="bold")
    fig.text(0.04, 0.895, title, fontsize=20, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(0.04, 0.835, subtitle, fontsize=13.5, color=INK2, va="top")


def footer(fig, text, y=0.07):
    fig.text(0.04, y, text, fontsize=10, color=MUTED, va="top", linespacing=1.4)


def unknown(fig, x, y, w, h, text):
    """'Can't tell yet' callout."""
    fig.patches.append(mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.006", transform=fig.transFigure,
                                               fc=SOFT, ec=GRID, ls=(0, (4, 3))))
    fig.text(x + 0.012, y + h - 0.015, "CAN'T TELL YET", fontsize=11, fontweight="bold", color=MUTED, va="top")
    fig.text(x + 0.012, y + h - 0.05, text, fontsize=12, color=INK2, va="top", linespacing=1.35)


def hbar(ax, v, col, vmax=100):
    ax.barh(0, vmax, color=GRID, height=1)
    ax.barh(0, v, color=col, height=1)
    ax.set_xlim(0, vmax)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")


def rgb_image(prefix, src):
    rgb = np.dstack([src[f"{prefix}_B4"], src[f"{prefix}_B3"], src[f"{prefix}_B2"]]).astype(float)
    ok = (rgb > 0).all(-1) & land
    lo, hi = np.percentile(rgb[ok], [2, 98])
    img = np.clip((rgb - lo) / (hi - lo), 0, 1) ** 0.8
    img[~land] = 1
    return img


IMG26 = rgb_image("summer2026", R)
IMG23 = rgb_image("summer2023", RGB)


def window():
    r, c, s = WIN
    x0, x1 = c * 0.03, (c + s) * 0.03
    y1 = EXT_KM - r * 0.03
    return x0, x1, y1 - s * 0.03, y1


def outline(ax, mask, color, lw=1.8):
    ax.contour(mask.astype(float), levels=[0.5], colors=[color], linewidths=lw,
               extent=(0, EXT_KM, 0, EXT_KM), origin="upper")


def map_panel(ax, k, style):
    """style 'outline': natural-color 2026 imagery, flagged areas outlined; 'fill': lightened imagery, filled."""
    x0, x1, y0, y1 = window()
    if style == "outline":
        ax.imshow(IMG26, extent=(0, EXT_KM, 0, EXT_KM), interpolation="nearest")
        for c in ("hist", "y2025", "s26"):
            outline(ax, flag[k] & CLS[c], COL[c])
    else:
        ax.imshow(0.45 + 0.55 * IMG26.mean(-1, keepdims=True).repeat(3, -1) * 0.9, extent=(0, EXT_KM, 0, EXT_KM),
                  interpolation="nearest")
        for c in ("hist", "y2025", "s26", "none"):
            overlay(ax, flag[k] & CLS[c], COL[c], alpha=0.85)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(INK)
        s.set_linewidth(1.2)


# ---------------------------------------------------------------- Q1
def q1():
    fig = figure()
    b = N_["bench_fullyear_tile"]
    mins = [v["minutes"] for v in b.values()]
    header(fig, 1, "Can BULC-D process large regions efficiently?", "Partly",
           f"One 100 km² tile takes {min(mins):.0f}–{max(mins):.0f} minutes; whole-region performance is untested",
           "Measured: one Earth Engine batch export of one tile for each version of \"normal\", full-year 2026 "
           "monitoring. One tile is not a region.")
    for i, k in enumerate("ABC"):
        x = 0.04 + i * 0.31
        fig.patches.append(mpatches.FancyBboxPatch((x, 0.36), 0.29, 0.4, boxstyle="round,pad=0.006",
                                                   transform=fig.transFigure, fc=SOFT, ec=GRID))
        fig.text(x + 0.018, 0.735, SHORT[k], fontsize=15, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.018, 0.69, "one 100 km² tile", fontsize=12, color=MUTED, va="top")
        fig.text(x + 0.018, 0.655, f"{b[k]['minutes']:.1f} min", fontsize=34, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.018, 0.565, f"{b[k]['eecu_s']:.0f} compute-seconds", fontsize=13.5, color=INK2, va="top")
        fig.lines.append(plt.Line2D([x + 0.018, x + 0.272], [0.515, 0.515], transform=fig.transFigure, color=GRID))
        fig.text(x + 0.018, 0.495, "10,000 km²: 100 × this tile (not measured)", fontsize=12, color=MUTED, va="top")
        fig.text(x + 0.018, 0.455, f"≈ {b[k]['eecu_s'] * 100 / 3600:.0f} compute-hours", fontsize=20,
                 fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.32, "Compute-seconds: Earth Engine's measure of work done (EECU-seconds). Tiles are independent, "
             "so they can run side by side;\nminutes depend on Earth Engine's shared queue.", fontsize=12, color=INK2,
             va="top")
    unknown(fig, 0.04, 0.11, 0.92, 0.135,
            "• Performance across a whole region: only one 100 km² tile was run with full-year monitoring. Total time, "
            "Earth Engine task limits and\n   tile-to-tile variation (forest type, cloudiness, terrain) are not measured; "
            "the 10,000 km² figures simply multiply one tile by 100.")
    footer(fig, "Tile r0056c0034 (Oregon Coast Range), Landsat 8/9, exported 2026-10-28 to a separate benchmark "
                "folder (regional_bench/fullyear-2026); validated regional products untouched.\n" + FOOT_RUN, y=0.075)
    save(fig, "Q1_regional_processing.png")


# ---------------------------------------------------------------- Q2
EXAMPLES = [  # (row, col, label): densest 9 x 9 patch in the Q2 window for each case
    (424, 168, "Cut in 2024 (Hansen)"), (286, 209, "Cut in 2025 (Hansen)"),
    (404, 234, "2026 spectral decline")]


def q2(style="fill", name="Q2_new_vs_older.png"):
    fig = figure()
    header(fig, 2, "Can BULC-D distinguish new disturbances from older ones?", "Partly",
           "BULC-D doesn't label age; a recent \"normal\" just stops flagging older loss",
           "Same 6 × 6 km, three versions of \"normal\". Colored: flagged as a 2026 decrease; the colors come from "
           "independent records.")
    w, gap, top = 0.245, 0.025, 0.765
    h = w * 13.333 / 7.5
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * (w + gap), top - h, w, h])
        map_panel(ax, k, style)
        ax.set_title(NAMES[k], loc="left", fontsize=14, fontweight="bold", color=INK, pad=6)
        for n, (r, c, _) in enumerate(EXAMPLES, 1):
            ax.text((c + 0.5) * 0.03, EXT_KM - (r + 0.5) * 0.03, str(n), ha="center", va="center",
                    fontsize=12, fontweight="bold", color=INK, zorder=8,
                    bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec=INK, lw=1.2))
        if i == 0:
            x0, _, y0, _ = window()
            ax.add_patch(mpatches.Rectangle((x0 + 0.25, y0 + 0.3), 1, 0.08, color="white", ec=INK, lw=0.8, zorder=6))
            ax.text(x0 + 0.75, y0 + 0.45, "1 km", ha="center", va="bottom", fontsize=11, color="white",
                    fontweight="bold", zorder=6)
    bx = 0.04 + 3 * (w + gap) - 0.012
    ax = fig.add_axes([bx, top - 0.21, 0.105, 0.105 * 13.333 / 7.5])
    ax.imshow(IMG23, extent=(0, EXT_KM, 0, EXT_KM), interpolation="nearest")
    x0, x1, y0, y1 = window()
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.text(bx, top - 0.22, "Same area, 2023\n(before the 2024–\n2026 changes)", fontsize=10.5, color=INK2, va="top")
    ly = top - h - 0.04
    shown = ("hist", "y2025", "s26", "none") if style == "fill" else ("hist", "y2025", "s26")
    for j, c in enumerate(shown):
        swatch(fig, [0.04, 0.32, 0.48, 0.67][j], ly, COL[c], LAB[c], fontsize=12)
    # real examples: what each version does at the numbered stands
    ey = ly - 0.07
    fig.text(0.04, ey, "Real stands", fontsize=13, fontweight="bold", color=INK, va="center")
    for n, (r, c, lab) in enumerate(EXAMPLES, 1):
        x = 0.16 + (n - 1) * 0.28
        verdict = "   ".join(f"{k}: {'flagged' if flag[k][r - 3:r + 4, c - 3:c + 4].mean() > 0.5 else 'not flagged'}"
                             for k in "ABC")
        fig.text(x, ey, f"{n}", fontsize=12, fontweight="bold", color=INK, va="center", ha="center",
                 bbox=dict(boxstyle="circle,pad=0.2", fc="white", ec=INK, lw=1.2))
        fig.text(x + 0.018, ey + 0.012, lab, fontsize=12.5, fontweight="bold", color=INK, va="center")
        fig.text(x + 0.018, ey - 0.022, verdict, fontsize=11.5, color=INK2, va="center")
    fig.text(0.04, ey - 0.075, "BULC-D only asks \"is this unlike normal?\". Stand 1 is bare in 2026 under every version; "
             "it is flagged unless \"normal\" already includes the bare years (B).", fontsize=12, color=INK2, va="top")
    note = ("Background: Sentinel-2, Jul–Sep 2026, lightened; bright, uncolored patches are bare ground BULC-D does not "
            "flag. " if style == "fill" else "Flagged area with no independent record is not outlined. ")
    footer(fig, note + "Whole-pilot maps: appendix A2.\n" + FOOT_EVID + "\n" + FOOT_RUN, y=0.105)
    save(fig, name)


# ---------------------------------------------------------------- Q3
def q3():
    fig = figure()
    s = N_["share_flagged_by_loss_year"]
    header(fig, 3, "How does the expectation period affect disturbance detection?", "Strong effect",
           "Past loss stays flagged until \"normal\" includes enough years after it",
           "Circle: share of that year's forest loss (Hansen) still flagged as a 2026 decrease; red: share of 2026 "
           "spectral declines flagged.")
    years = list(range(2018, 2027))
    ax = fig.add_axes([0.13, 0.25, 0.83, 0.52])
    ax.set_xlim(2017.5, 2026.5)
    ax.set_ylim(-0.6, 2.6)
    ax.axis("off")
    for row, k in enumerate("ABC"):
        y = 2 - row
        a, b = NORMAL[k]
        ax.add_patch(mpatches.FancyBboxPatch((a - 0.45, y - 0.42), b - a + 0.9, 0.84, boxstyle="round,pad=0.02",
                                             fc="#e9e7e1", ec="none"))
        ax.text(a - 0.4, y + 0.34, "normal", fontsize=10, color=MUTED, va="center")
        fig.text(0.04, ax.transData.transform((0, y))[1] / fig.bbox.height, SHORT[k], fontsize=14,
                 fontweight="bold", color=INK, va="center")
        for yr in years:
            if yr == 2026:
                v, col = N_["s26_flagged"][k]["pct"], S26
            else:
                v, col = s[k][yr], (Y25 if yr == 2025 else HIST)
            r = 0.27 * np.sqrt(v / 100)
            ax.add_patch(mpatches.Circle((yr, y + 0.08), 0.27, fc="white", ec=GRID, lw=1))
            ax.add_patch(mpatches.Circle((yr, y + 0.08), max(r, 0.02), fc=col, ec="none"))
            ax.text(yr, y - 0.24, f"{v:.0f}%", fontsize=12.5, color=INK, fontweight="bold", ha="center",
                    va="center")
    for yr in years:
        ax.text(yr, 2.55, str(yr), ha="center", fontsize=13, color=INK, fontweight="bold" if yr == 2026 else None)
    ax.text(2017.6, -0.62, "Shaded: the years each version learns \"normal\" from. Circle area ∝ share.", fontsize=11,
            color=MUTED, va="top")
    ax.axvline(2025.5, color=INK2, lw=1, ls=(0, (3, 3)), ymin=0.05, ymax=0.93)
    fig.text(0.04, 0.175, "Under A, loss after its \"normal\" (2024–2025) is almost all flagged, and so is loss from "
             "its last years (2022–2023). Under B, 2024 loss is absorbed but 2025\nloss is not: \"normal\" holds only "
             "about one year of the stand after a 2025 harvest. Loss from 2018–2021 has regrown enough that no "
             "version flags much.",
             fontsize=12, color=INK2, va="top", linespacing=1.35)
    footer(fig, FOOT_EVID + "\n" + FOOT_RUN, y=0.085)
    save(fig, "Q3_expectation_period_effect.png")


# ---------------------------------------------------------------- Q4 / Q5 shared grid
def grid_rows(fig, rows, top, colx, cw=0.14, gap=0.1):
    for k, x in zip("ABC", colx):
        fig.text(x, top + 0.05, SHORT[k], fontsize=15, fontweight="bold", color=INK, va="bottom")
    for i, (lab, sub, vals, col) in enumerate(rows):
        y = top - i * gap
        fig.text(0.04, y, lab, fontsize=14, color=INK, va="center", fontweight="bold")
        fig.text(0.04, y - 0.03, sub, fontsize=10.5, color=INK2, va="top")
        for k, x in zip("ABC", colx):
            v, km = vals[k]
            ax = fig.add_axes([x, y - 0.02, cw, 0.04])
            hbar(ax, v, col)
            fig.text(x + cw + 0.008, y, f"{v:.0f}%", fontsize=17, fontweight="bold", color=INK, va="center")
            fig.text(x, y - 0.03, f"{km:.1f} km²", fontsize=10.5, color=INK2, va="top")


def q4():
    fig = figure()
    h, y = N_["hist_flagged"], N_["y2025_flagged"]
    header(fig, 4, "Does a shorter, more recent expectation period reduce detections of older disturbances?",
           "Mostly yes",
           f"Historical loss flagged falls from {h['A']['pct']:.0f}% (A) to {h['B']['pct']:.0f}% (B); 2025 loss: "
           f"still {y['B']['pct']:.0f}%",
           "Share of each kind of past forest loss that BULC-D flags as a 2026 decrease. For early detection, "
           "lower is better here.")
    colx = [0.33, 0.54, 0.75]
    grid_rows(fig, [
        (LAB["hist"], f"{N_['class_km2']['hist']:.1f} km² in the pilot",
         {k: (h[k]["pct"], h[k]["km2"]) for k in "ABC"}, HIST),
        (LAB["y2025"], f"{N_['class_km2']['y2025']:.1f} km² in the pilot",
         {k: (y[k]["pct"], y[k]["km2"]) for k in "ABC"}, Y25)], top=0.66, colx=colx, gap=0.15)
    fig.patches.append(mpatches.FancyBboxPatch((colx[1] - 0.008, 0.51 - 0.045), 0.205, 0.09,
                                               boxstyle="round,pad=0.004", transform=fig.transFigure, fill=False,
                                               ec=INK, lw=1.6))
    fig.text(colx[1], 0.445, "B's \"normal\" ends in 2025, so 2025 loss still stands out", fontsize=11,
             color=INK, va="top", ha="left", fontweight="bold")
    fig.text(0.04, 0.37, "Why 2025 loss stays flagged under B: its \"normal\" (2024–2025) holds only about one year "
             "of a 2025-harvested stand, so in 2026 the bare stand\nstill looks unusual. A recent \"normal\" helps "
             "only for loss at least a year older than its end. Per-year detail: appendix A1.",
             fontsize=12.5, color=INK2, va="top", linespacing=1.35)
    unknown(fig, 0.04, 0.12, 0.92, 0.1,
            "Whether some of this flagged past-loss area is genuine repeat disturbance in 2026 (about 1 km² also "
            "shows a 2026 spectral decline).")
    footer(fig, FOOT_EVID + "\n" + FOOT_RUN, y=0.08)
    save(fig, "Q4_older_disturbances.png")


def q5():
    fig = figure()
    s = N_["s26_flagged"]
    lo, hi = min(v["pct"] for v in s.values()), max(v["pct"] for v in s.values())
    header(fig, 5, "Does changing the expectation period cause us to miss genuine 2026 disturbances?",
           "No evidence of that",
           f"All versions flag {lo:.0f}–{hi:.0f}% of strong 2026 spectral declines, largely the same",
           "Strong, independently supported spectral declines only: not all genuine 2026 disturbances. Higher is "
           "better here.")
    colx = [0.33, 0.54, 0.75]
    grid_rows(fig, [(LAB["s26"], f"{N_['class_km2']['s26']:.1f} km² in the pilot",
                     {k: (s[k]["pct"], s[k]["km2"]) for k in "ABC"}, S26)], top=0.66, colx=colx)
    # overlap bar
    a3, n0 = N_["s26_all_three"], N_["s26_none"]
    some = 100 - a3 - n0
    fig.text(0.04, 0.5, "Same places in\nall three versions?", fontsize=14, color=INK, va="center",
             fontweight="bold")
    ax = fig.add_axes([0.33, 0.48, 0.59, 0.04])
    left = 0
    for v, col, lab, tc in ((a3, S26, f"flagged by all three  {a3:.0f}%", "white"),
                            (some, "#f2a4a0", f"{some:.0f}%", INK), (n0, GRID, f"by none  {n0:.0f}%", INK)):
        ax.barh(0, v, left=left, color=col, height=1, edgecolor="white", lw=1.5)
        left += v
    ax.text(a3 / 2, 0, f"flagged by all three: {a3:.0f}%", ha="center", va="center", fontsize=12.5, color="white",
            fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")
    fig.text(0.33, 0.45, f"by only one or two: {some:.0f}%     by none: {n0:.0f}%", fontsize=12, color=INK2,
             va="top")
    unknown(fig, 0.04, 0.12, 0.92, 0.2,
            "• Subtle 2026 change (thinning, insects, drought stress): only strong declines (burn ratio drop ≥ 0.2) "
            "are tested here.\n"
            f"• The flagged area with no independent record (A {NB['A']['none']:.1f}, B {NB['B']['none']:.1f}, "
            f"C {NB['C']['none']:.1f} km²): could be subtle real change or false alarms.\n"
            f"• Not all are 2026 disturbances: {N_['s26_first_seen_pct']['late_2025']:.0f}% were already visible in "
            "Nov–Dec 2025 (Q7). 2026 is year to date; late-2026 change may not be confirmed yet.")
    footer(fig, FOOT_EVID + "\n" + FOOT_RUN, y=0.08)
    save(fig, "Q5_missing_2026.png")


# ---------------------------------------------------------------- Q6 / Q7 shared
TCATS = [("before_change", "flagged while Sentinel-2 still showed no change", "#b8322f", "white"),
         ("in_window", "by the month Sentinel-2 first shows the change", INK2, "white"),
         ("next_month", "1 month later", "#8db8e8", INK),
         ("later", "2+ months later", "#1f5fa8", "white"),
         ("not_flagged", "not flagged in 2026", GRID, INK)]


def tbar(fig, x, y, w, h, vals, keys, minlab=6, fs=12):
    ax = fig.add_axes([x, y, w, h])
    left = 0
    for key, _, col, tc in TCATS:
        if key not in keys:
            continue
        v = vals[key]
        ax.barh(0, v, left=left, color=col, height=1, edgecolor="white", lw=1.5)
        if v >= minlab:
            ax.text(left + v / 2, 0, f"{v:.0f}%", ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)
        left += v
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")


# ---------------------------------------------------------------- Q6
def q6():
    fig = figure()
    ts = N_["timing_by_season"]
    quick = [ts[k][s_]["in_window"] + ts[k][s_]["next_month"]
             for k in "ABC" for s_ in ("Mar–May", "Jun–Aug")]
    header(fig, 6, "Can BULC-D detect disturbances earlier using full-year monitoring?", "Partly",
           f"{min(quick):.0f}–{max(quick):.0f}% of spring–summer changes flagged within a month; winter ones "
           "wait",
           "When BULC-D first flags each 2026 spectral decline, grouped by the month Sentinel-2 first shows it. "
           "Full-year monitoring.")
    keys = ("before_change", "in_window", "next_month", "later", "not_flagged")
    rows = list(SEASONS)
    y0 = 0.68
    for j, (col, lab) in enumerate([(TCATS[0][2], "before any change is seen (Q7)"),
                                    (TCATS[1][2], "by the month change first appears"), (TCATS[2][2], "1 month later"),
                                    (TCATS[3][2], "2+ months later"), (TCATS[4][2], "not flagged")]):
        swatch(fig, [0.04, 0.255, 0.49, 0.6, 0.725][j], 0.775, col, lab, fontsize=11)
    for i, s_ in enumerate(rows):
        yy = y0 - i * 0.125
        fig.text(0.04, yy - 0.01, f"First seen {s_}", fontsize=14, fontweight="bold", color=INK, va="center")
        fig.text(0.04, yy - 0.045, f"{ts['A'][s_]['n_km2']:.1f} km²", fontsize=10.5, color=INK2, va="center")
        for r, k in enumerate("ABC"):
            fig.text(0.222, yy + 0.03 - r * 0.033, k, fontsize=11.5, color=INK2, va="center", fontweight="bold")
            tbar(fig, 0.235, yy + 0.016 - r * 0.033, 0.455, 0.027, ts[k][s_], keys, minlab=7, fs=10.5)
    # first flags vs clear Landsat views (A)
    ax = fig.add_axes([0.73, 0.36, 0.24, 0.36])
    fd = F["A26"]["first_dec"]
    doy = fd[S26_2026 & (fd // 1000 == 2026)] % 1000
    ax.hist(doy, bins=np.arange(1, 125, 4), color=INK2, edgecolor="white", lw=0.5)
    for d in CLEAR_LANDSAT:
        dd = (np.datetime64(d) - np.datetime64("2026-01-01")).astype(int) + 1
        ax.axvline(dd, color=HIST, lw=1.6, ymax=0.12)
    ax.set_xlim(1, 121)
    ax.set_xticks([1, 32, 60, 91, 121], ["Jan", "Feb", "Mar", "Apr", "May"], fontsize=11)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_title("A's first flags, Jan–Apr", loc="left", fontsize=13, fontweight="bold", color=INK, pad=6)
    ax.text(3, ax.get_ylim()[1] * 0.92, "blue ticks: clear Landsat\nviews (Jan 19, Feb 5, ...)",
            fontsize=10.5, color=HIST, va="top")
    fig.text(0.73, 0.32, "Nothing is flagged before Mar 16,\nthough clear views exist on\nJan 19 and Feb 5.",
             fontsize=11.5, color=INK2, va="top", linespacing=1.3)
    unknown(fig, 0.04, 0.125, 0.92, 0.1,
            "Why winter changes wait for March: not yet explained (few clear views, or a winter \"normal\" that allows "
            "more variation).\nSnowy winters are untested (2026 was nearly snow-free). Sep–Oct: some changes may be too "
            "recent to confirm by Oct 27.")
    footer(fig, "Sentinel-2: first month the monthly burn ratio is clearly below the same month a year earlier "
                "(an estimate;\nthe actual disturbance date is unknown). BULC-D: first 4-day window with "
                "P(decrease) > 0.65. Only declines first seen in 2026 (the "
                f"{N_['s26_first_seen_pct']['late_2025']:.0f}% seen in Nov–Dec 2025: Q7).\n"
                + FOOT_RUN, y=0.085)
    save(fig, "Q6_how_early.png")


# ---------------------------------------------------------------- Q7
def q7():
    fig = figure()
    tv = N_["timing_vs_window"]
    close = {k: tv[k]["in_window"] + tv[k]["next_month"] for k in "ABC"}
    early = {k: tv[k]["before_change"] for k in "ABC"}
    header(fig, 7, "How accurately can BULC-D identify when disturbances occurred?", "Can't tell yet",
           f"~{np.mean(list(close.values())):.0f}% of first flags are within a month of the observed change; "
           f"{min(early.values()):.0f}–{max(early.values()):.0f}% precede it",
           "First BULC-D detection compared with the independent change window from monthly Sentinel-2 imagery "
           "(2026 spectral declines).")
    # schematic of the three dates
    ax = fig.add_axes([0.04, 0.58, 0.92, 0.2])
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.plot([0.3, 11.7], [0.45, 0.45], color=GRID, lw=3, solid_capstyle="round")
    ax.add_patch(mpatches.Rectangle((4.2, 0.3), 2.6, 0.3, fc="#e9e7e1", ec="none"))
    ax.text(5.5, 0.45, "actual disturbance:\nunknown, in here", ha="center", va="center", fontsize=11, color=INK2)
    for xx, lab in ((4.2, "last month Sentinel-2\nlooks unchanged"), (6.8, "first month Sentinel-2\nshows change")):
        ax.plot([xx, xx], [0.25, 0.65], color=INK, lw=2)
        ax.text(xx, 0.72, lab, ha="center", va="bottom", fontsize=11, color=INK)
    for xx, key in ((2.2, "before_change"), (5.5, "in_window"), (7.9, "next_month"), (10.0, "later")):
        col = dict((t[0], t[2]) for t in TCATS)[key]
        ax.plot(xx, 0.12, marker="v", ms=13, color=col, mec="white")
    ax.text(2.2, -0.02, "BULC-D flags here:\npossible false early detection", ha="center", va="top", fontsize=10.5,
            color="#b8322f", fontweight="bold")
    ax.text(10.0, -0.02, "BULC-D flags here:\n2+ months late", ha="center", va="top", fontsize=10.5,
            color="#1f5fa8", fontweight="bold")
    ax.text(5.5, -0.02, "BULC-D flags here:\nconsistent", ha="center", va="top", fontsize=10.5, color=INK2,
            fontweight="bold")
    ax.text(7.9, -0.02, "1 month\nlater", ha="center", va="top", fontsize=10.5, color=INK2, fontweight="bold")
    keys = [t[0] for t in TCATS]
    for j, (key, lab, col, _) in enumerate(TCATS):
        swatch(fig, [0.04, 0.25, 0.48, 0.6, 0.735][j], 0.445,
               col, {"before_change": "before any change is seen", "in_window": "by the month change is first seen",
                     "next_month": "1 month later", "later": "2+ months later", "not_flagged": "not flagged"}[key],
               fontsize=11.5)
    for i, k in enumerate("ABC"):
        yy = 0.375 - i * 0.065
        fig.text(0.04, yy, SHORT[k], fontsize=13.5, fontweight="bold", color=INK, va="center")
        tbar(fig, 0.17, yy - 0.022, 0.79, 0.044, tv[k], keys, minlab=2.5)
    sf = N_["s26_first_seen_pct"]
    lm = N_["late2025_first_bulcd_month"]["A"]
    fig.text(0.04, 0.17, f"Not counted above: {sf['late_2025']:.0f}% of the 2026 spectral declines were already visible "
             f"in Nov–Dec 2025, so they are not 2026 disturbances. BULC-D's 2026 run\nflags them in March–April "
             f"(A: {lm['Mar'] + lm['Apr']:.0f}%), just like early-2026 changes: a 2026 flag alone cannot separate "
             f"late-2025 from early-2026 change.\nYear check (A only): "
             f"{N_['year_check_A']['hansen2024_first_flag_2024']:.0f}% of Hansen 2024 loss is first flagged in 2024, "
             f"{N_['year_check_A']['hansen2025_first_flag_2025']:.0f}% of Hansen 2025 loss in 2025.", fontsize=11.5, color=INK2, va="top", linespacing=1.3)
    footer(fig, "Can't tell yet: true timing accuracy. Neither Sentinel-2 (monthly, cloud-limited) nor Hansen (yearly) "
                "gives a verified date; a test needs dated events (e.g., harvest records).\n"
                "Sentinel-2 change window: monthly medians, each compared with the same month a year earlier. "
                "BULC-D: first 4-day window with P(decrease) > 0.65.\n" + FOOT_RUN, y=0.075)
    save(fig, "Q7_timing.png")


# ---------------------------------------------------------------- appendix
def a1_table():
    fig = figure()
    s = N_["share_flagged_by_loss_year"]
    fig.text(0.04, 0.94, "Appendix A1 · Share of each year's forest loss flagged as a 2026 decrease", fontsize=20,
             fontweight="bold", color=INK, va="top")
    cols = ["Hansen loss year", "km²", "A (2018–2023)", "B (2024–2025)", "C (2018–2025)"]
    xs = [0.06, 0.25, 0.38, 0.56, 0.74]
    for x, c in zip(xs, cols):
        fig.text(x, 0.82, c, fontsize=13.5, fontweight="bold", color=INK, va="center")
    rows = [(str(y), N_["loss_year_km2"][y], [s[k][y] for k in "ABC"]) for y in range(2018, 2026)]
    rows.append(("2026 spectral decline", N_["class_km2"]["s26"], [N_["s26_flagged"][k]["pct"] for k in "ABC"]))
    rows.append(("No independent record*", N_["class_km2"]["none"], [100 * NB[k]["none"] / N_["class_km2"]["none"]
                                                                       for k in "ABC"]))
    for i, (lab, km, vals) in enumerate(rows):
        y = 0.76 - i * 0.055
        if i % 2 == 0:
            fig.patches.append(mpatches.Rectangle((0.05, y - 0.024), 0.85, 0.048, transform=fig.transFigure, fc=SOFT,
                                                  ec="none"))
        fig.text(xs[0], y, lab, fontsize=13, color=INK, va="center")
        fig.text(xs[1], y, f"{km:.1f}", fontsize=13, color=INK, va="center")
        for x, v in zip(xs[2:], vals):
            fig.text(x, y, f"{v:.1f}%", fontsize=13, color=INK, va="center")
    footer(fig, "* All other land; its share flagged is the false-alarm-or-subtle-change rate, not testable here. "
                "\nRepeat-disturbance candidates (flagged, Hansen loss 2018–2025 and a 2026 spectral decline): "
                f"A {N_['repeat_candidates_km2']['A']:.1f}, B {N_['repeat_candidates_km2']['B']:.1f}, "
                f"C {N_['repeat_candidates_km2']['C']:.1f} km².\n" + FOOT_EVID + "\n" + FOOT_RUN, y=0.1)
    save(fig, "A1_table_by_loss_year.png")


def a2_maps():
    fig = figure()
    fig.text(0.04, 0.94, "Appendix A2 · Whole pilot: what each version flags as a 2026 decrease", fontsize=20,
             fontweight="bold", color=INK, va="top")
    w = 0.28
    h = w * 13.333 / 7.5
    x0, x1, y0, y1 = window()
    for i, k in enumerate("ABC"):
        ax = fig.add_axes([0.04 + i * 0.31, 0.83 - h, w, h])
        base_map(ax)
        for c in ("hist", "y2025", "s26", "none"):
            overlay(ax, flag[k] & CLS[c], COL[c])
        ax.add_patch(mpatches.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, ec=INK, lw=1.2, ls=(0, (3, 2))))
        ax.set_title(NAMES[k], loc="left", fontsize=14, fontweight="bold", color=INK, pad=6)
    for j, c in enumerate(("hist", "y2025", "s26", "none")):
        swatch(fig, [0.04, 0.3, 0.46, 0.65][j], 0.27, COL[c], LAB[c], fontsize=12)
    footer(fig, "Dashed box: the window in Q2. Flat gray: land not flagged; white: water. No forest mask.\n"
                + FOOT_EVID + "\n" + FOOT_RUN, y=0.11)
    save(fig, "A2_whole_area_maps.png")


if __name__ == "__main__":
    q1()
    q2()
    q2(style="outline", name="A3_map_treatment_alternative.png")
    q3()
    q4()
    q5()
    q6()
    q7()
    a1_table()
    a2_maps()
    print(json.dumps(N_, indent=1, default=float))

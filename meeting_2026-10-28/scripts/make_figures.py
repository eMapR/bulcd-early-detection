"""Figures for the 2026-10-28 BULC-D meeting (read-only; uses data/ fetched by the other scripts).

    python meeting_2026-10-28/scripts/make_figures.py

Inputs:  data/pilot.npz (fetch_pilot.py), data/pixels.json (fetch_pixels.py),
         data/vectors.json, data/spot_check_*.json (spot_check.py),
         experiments/output/pine_mountain_fit_order/*_order1.csv (the 2026-10-13 experiment).
Outputs: figures/slide{1..5}_*.png, 2667 x 1500 px (16:9 at 200 dpi).
"""
import csv
import datetime as dt
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

HERE = Path(__file__).resolve().parents[1]
DATA, FIGS = HERE / "data", HERE / "figures"
REPO = HERE.parent
FIGS.mkdir(exist_ok=True)

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a887f", "#e4e3df"
DEC, UNC, INC = "#e34948", "#8a887f", "#2a78d6"            # the apps' outcome colors
YEAR_COLORS = {2024: "#2a78d6", 2025: "#eda100", 2026: "#e34948"}  # validated all-pairs (dataviz)
YEAR_LABELS = {2024: "2024 or earlier", 2025: "2025", 2026: "2026"}
SENSOR_COLORS = {"L8": "#2a78d6", "L8+S2": "#eb6834", "L8+L9+S2": "#1baf7a"}
SNOW = "#eda100"  # Slide 3 false (snowmelt) episode; validated all-pairs with DEC and INC (dataviz)
THRESHOLD = 0.65
PX_KM2 = 0.0009

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 15, "axes.titlesize": 18, "axes.labelsize": 15,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": "white",
    "savefig.facecolor": "white", "legend.frameon": False,
})


def figure():
    return plt.figure(figsize=(13.333, 7.5), dpi=200)


def save(fig, name):
    fig.savefig(FIGS / name, dpi=200)
    plt.close(fig)
    print("wrote", FIGS / name)


# ---------------------------------------------------------------- map helpers
pilot = np.load(DATA / "pilot.npz")
cond = {y: pilot[f"condition_{y}"] for y in ("2024", "2025", "2026")}
dyear = pilot["detection_year"]
land = cond["2026"] != 255  # water is masked in the pilot (mask_water: true); no forest mask
dec26 = cond["2026"] == 0
N = pilot["condition_2026"].shape[0]
EXT_KM = N * 0.03
EXTENT = (0, EXT_KM, 0, EXT_KM)  # km from the pilot box's lower-left corner
X0, Y1 = -2153385.0, 2750565.0
Y0 = Y1 - N * 30


def to_km(x, y):
    return (np.asarray(x) - X0) / 1000.0, (np.asarray(y) - Y0) / 1000.0


def background():
    """Sentinel-2 Jul-Sep 2026 true color as a light grayscale base (display only; Slide 4)."""
    rgb = np.dstack([pilot["rgb_B4"], pilot["rgb_B3"], pilot["rgb_B2"]])
    g = 0.3 * rgb[..., 0] + 0.59 * rgb[..., 1] + 0.11 * rgb[..., 2]
    lo, hi = np.percentile(g[g > 0], [2, 98])
    g = np.clip((g - lo) / (hi - lo), 0, 1)
    return 0.58 + 0.38 * g  # lightened so the classes read on top


BG = background()
LAND, WATER = "#e4e3df", "#ffffff"  # flat base: land not otherwise colored / masked water


def base_map(ax, title=None, image=False):
    if image:
        ax.imshow(BG, cmap="gray", vmin=0, vmax=1, extent=EXTENT, interpolation="nearest")
    else:
        flat = np.where(land[..., None], matplotlib.colors.to_rgb(LAND), matplotlib.colors.to_rgb(WATER))
        ax.imshow(flat, extent=EXTENT, interpolation="nearest")
    ax.set_xlim(0, EXT_KM)
    ax.set_ylim(0, EXT_KM)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(True)
        s.set_color(INK)
        s.set_linewidth(1.5)
    if title:
        ax.set_title(title, loc="left", fontsize=18, color=INK, pad=10)


def overlay(ax, mask, color, alpha=1.0):
    rgba = np.zeros(mask.shape + (4,))
    rgba[mask] = matplotlib.colors.to_rgba(color, alpha)
    ax.imshow(rgba, extent=EXTENT, interpolation="nearest")


def scale_bar(ax, km=5, x=0.8, y=0.9):
    ax.add_patch(mpatches.Rectangle((x, y), km, 0.25, color="white", ec=INK, lw=1.2, zorder=5))
    ax.add_patch(mpatches.Rectangle((x, y), km / 2, 0.25, color=INK, zorder=6))
    ax.text(x, y + 0.45, "0", ha="center", va="bottom", fontsize=12, color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    ax.text(x + km, y + 0.45, f"{km} km", ha="center", va="bottom", fontsize=12, color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))


def north_arrow(ax, x=18.6, y=17.2, length=1.8):
    """True north (EPSG:5070 Albers grid north is ~17 degrees off here)."""
    vx, vy = pilot["north_vec"] / np.hypot(*pilot["north_vec"])
    ax.annotate("", xy=(x + vx * length, y + vy * length), xytext=(x, y),
                arrowprops=dict(arrowstyle="-|>,head_width=0.5,head_length=0.8", color=INK, lw=2.2), zorder=6)
    ax.text(x + vx * (length + 0.5), y + vy * (length + 0.5), "N", ha="center", va="center", fontsize=14,
            fontweight="bold", color=INK, zorder=6)


def tile_lines(ax, labels=False):
    tiles = json.loads(str(pilot["tiles_json"]))
    for tid, (tx, ty) in tiles.items():
        x, y = to_km(tx, ty)
        ax.add_patch(mpatches.Rectangle((x, y - 9.99), 9.99, 9.99, fill=False, ec=INK, lw=1.4, ls=(0, (6, 4)),
                                        zorder=4))
        if labels:
            ax.text(x + 0.35, y - 0.35, f"tile {tid}", ha="left", va="top", fontsize=12, color=INK, zorder=6,
                    bbox=dict(fc="white", ec="none", alpha=0.8, pad=2))


def swatch(fig, x, y, color, text, alpha=1.0, fontsize=12):
    """Legend entry in figure coordinates; edged so white/light swatches stay visible."""
    fig.patches.append(mpatches.Rectangle((x, y - 0.011), 0.012, 0.022, transform=fig.transFigure, fc=color,
                                          alpha=alpha, ec=MUTED, lw=0.8))
    fig.text(x + 0.017, y, text, fontsize=fontsize, color=INK, va="center")


# ---------------------------------------------------------------- slide 2
def slide2():
    fig = figure()
    fig.text(0.04, 0.945, "Only 28% of the 2026 decrease area was first confirmed in 2026", fontsize=24,
             fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.885, "Regional pilot, Oregon Coast Range (400 km²). Same pixels, same extent; the right map "
             "colors each 2026\ndecrease pixel by the earliest season BULC-D confirmed it as decrease.",
             fontsize=14, color=INK2, va="top")
    ax1 = fig.add_axes([0.04, 0.19, 0.30, 0.58])
    ax2 = fig.add_axes([0.37, 0.19, 0.30, 0.58])
    base_map(ax1)
    ax1.set_title("2026 condition: decrease", loc="left", fontsize=15, color=INK, pad=10)
    overlay(ax1, dec26, DEC)
    base_map(ax2)
    ax2.set_title("2026 decreases by first detection year", loc="left", fontsize=15, color=INK, pad=10)
    counts = {}
    for y in (2024, 2025, 2026):
        m = dec26 & (dyear == y)
        counts[y] = int(m.sum())
        overlay(ax2, m, YEAR_COLORS[y])
    assert sum(counts.values()) == int(dec26.sum()), "every 2026 decrease pixel has a detection year"
    for ax in (ax1, ax2):
        scale_bar(ax)
        north_arrow(ax)
    total = sum(counts.values())

    # Legend + numbers panel.
    lx = 0.70
    fig.text(lx, 0.79, "2026 decrease area", fontsize=16, color=INK2, va="top")
    fig.text(lx, 0.755, f"{total * PX_KM2:.1f} km²", fontsize=30, fontweight="bold", color=INK, va="top")
    fig.text(lx, 0.675, "First confirmed as decrease in:", fontsize=16, color=INK2, va="top")
    y = 0.615
    for yr in (2024, 2025, 2026):
        pct = 100 * counts[yr] / total
        fig.patches.append(mpatches.Rectangle((lx, y - 0.045), 0.022, 0.04, transform=fig.transFigure,
                                              color=YEAR_COLORS[yr]))
        fig.text(lx + 0.032, y - 0.005, f"{pct:.0f}%", fontsize=28, fontweight="bold", color=INK, va="top")
        fig.text(lx + 0.11, y - 0.002, YEAR_LABELS[yr], fontsize=16, color=INK, va="top")
        fig.text(lx + 0.11, y - 0.035, f"{counts[yr] * PX_KM2:.1f} km²", fontsize=13, color=INK2, va="top")
        y -= 0.105
    # Map legend (one row under both maps).
    for x, (c, t) in zip((0.04, 0.165, 0.43),
                         ((DEC, "2026 decrease"), (LAND, "other land: unchanged or increase"),
                          (WATER, "water (masked)"))):
        swatch(fig, x, 0.145, c, t, fontsize=12)
    fig.text(lx, 0.31, "Detection year = the first season BULC-D\n"
             "confirmed the decrease (season ended as\n"
             "decrease). It is not the disturbance year.\n"
             "2024 is the first season analyzed, so\n"
             "\"2024 or earlier\" includes older change.",
             fontsize=12.5, color=INK2, va="top", linespacing=1.4)
    fig.text(0.04, 0.105, "Each season is an independent BULC-D run (Jun 1–Sep 30) against the same fixed 2018–2023 "
             "Landsat 8 expectation; L8+L9 monitoring; decrease threshold 0.65.\n"
             "30 m, EPSG:5070. Water masked; no forest mask (all land-cover types). Percentages are rounded.\n"
             "Source: projects/bulcd-python-rebuild/assets/regional/r6-pilot-coast-range-2026-stack "
             "(condition, detection_year).",
             fontsize=10.5, color=MUTED, va="top", linespacing=1.5)
    save(fig, "slide2_original_vs_detection_year.png")
    return counts, total


# ---------------------------------------------------------------- slide 1
def date(s):
    return dt.date.fromisoformat(s)


def season_axes_fmt(ax, year):
    ax.set_xlim(dt.date(year, 5, 28), dt.date(year, 10, 4))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[6, 7, 8, 9, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.grid(axis="y", color=GRID, lw=0.8)


def slide1():
    p = json.loads((DATA / "pixels.json").read_text())["slide1"]
    fig = figure()
    fig.text(0.04, 0.955, "A change confirmed in 2025 is still mapped as \"decrease\" in 2026", fontsize=24,
             fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.895, "NBR dropped sometime between the 2024 and 2025 observation seasons, not necessarily "
             "during 2025.\nEvery season is compared with the same 2018–2023 expectation, so an existing change "
             "keeps looking like a decrease.", fontsize=14, color=INK2,
             va="top", linespacing=1.35)
    gs = fig.add_gridspec(2, 3, left=0.07, right=0.70, top=0.78, bottom=0.12, hspace=0.18, wspace=0.08)
    status = {"2024": ("not decrease", UNC), "2025": ("DECREASE (first)", DEC),
              "2026": ("still DECREASE", DEC)}
    top_axes = []
    for i, yr in enumerate(("2024", "2025", "2026")):
        rows = p["seasons"][yr]
        d = [date(r["date"]) for r in rows]
        a = fig.add_subplot(gs[0, i])
        b = fig.add_subplot(gs[1, i], sharex=a)
        top_axes.append(a)
        a.plot(d, [r["expected"] for r in rows], color=MUTED, lw=2.5, label="expected NBR (2018–2023 fit)")
        for cls, col in (("decrease", DEC), ("unchanged", UNC), ("increase", INC)):
            pts = [(dd, r["observed"]) for dd, r in zip(d, rows) if r["observed"] is not None and r["supports"] == cls]
            if pts:
                a.scatter(*zip(*pts), s=55, color=col, edgecolor="white", lw=1, zorder=3,
                          label=f"observed NBR, favors {cls}")
        a.set_ylim(-0.3, 1.0)
        b.step(d, [r["decrease"] for r in rows], where="post", color=DEC, lw=2.5, label="P(decrease)")
        b.axhline(THRESHOLD, color=INK2, lw=1.3, ls=(0, (4, 3)), label=f"decision threshold ({THRESHOLD})")
        b.set_ylim(0, 1)
        for ax in (a, b):
            season_axes_fmt(ax, int(yr))
        plt.setp(a.get_xticklabels(), visible=False)
        if i:
            plt.setp(a.get_yticklabels(), visible=False)
            plt.setp(b.get_yticklabels(), visible=False)
        else:
            a.set_ylabel("NBR")
            b.set_ylabel("P(decrease)")
        label, col = status[yr]
        a.set_title(f"{yr} season", loc="left", fontsize=17, color=INK)
        fc = next((r["date"] for r in rows if r["decrease"] > THRESHOLD), None)
        b.text(0.97, 0.16 if fc else 0.45, f"Season end:\n{label}", transform=b.transAxes, ha="right",
               va="center",
               fontsize=12.5, color="white" if col == DEC else INK, fontweight="bold",
               bbox=dict(fc=col, ec="none", pad=4, alpha=0.95 if col == DEC else 0.35))
        if fc:
            b.annotate(f"crosses {fc[5:].replace('-', '/')}", xy=(date(fc), THRESHOLD), xytext=(date(fc) +
                       dt.timedelta(days=22), 0.45), fontsize=12, color=INK,
                       arrowprops=dict(arrowstyle="->", color=INK2, lw=1.2))
    # Between-season note.
    top_axes[0].text(0.5, 0.3, "NBR drops sometime between\nthe 2024 and 2025 seasons\n(Oct–May: outside the season) →",
                     transform=top_axes[0].transAxes, fontsize=12, color=INK, ha="center", va="center",
                     bbox=dict(fc="white", ec=MUTED, pad=5))
    h, lab = [], []
    for ax in fig.axes:
        hh, ll = ax.get_legend_handles_labels()
        for x, y in zip(hh, ll):
            if y not in lab:
                h.append(x)
                lab.append(y)
    lab = [x.replace("observed NBR, favors", "observed, favors").replace(" (2018–2023 fit)", "\n(2018–2023 fit)")
           for x in lab]
    fig.legend(h, lab, loc="upper left", bbox_to_anchor=(0.725, 0.80), fontsize=12.5, handletextpad=0.6,
               labelspacing=0.8)
    fig.text(0.735, 0.43, "What the products say", fontsize=15, fontweight="bold", color=INK, va="top")
    fig.text(0.735, 0.385, "2026 condition: decrease\n"
             "Detection year: 2025\n\n"
             "The 2026 map alone would\n"
             "report this as 2026 change.\n"
             "Detection year shows it was\n"
             "already confirmed in 2025;\n"
             "the change itself happened\n"
             "between the 2024 and 2025\n"
             "seasons.", fontsize=12.5, color=INK2, va="top", linespacing=1.35)
    fig.text(0.04, 0.05, f"Regional-pilot pixel {p['lon']:.5f}, {p['lat']:.5f} (center of a uniform patch that is "
             "decrease in 2025 and 2026, not 2024). Independent single-season runs rerun live with the pilot's "
             "stored configs; end-of-season P(decrease) matches the exported tiles (0.0435 / 0.9145 / 0.9145).",
             fontsize=10.5, color=MUTED, va="top", wrap=True)
    save(fig, "slide1_detection_year_problem.png")
    return p


# ---------------------------------------------------------------- slide 3
def read_csv(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["date"] = date(r["date"])
        for k in ("observed", "expected", "fitted", "zscore", "decrease"):
            if k in r:
                r[k] = float(r[k]) if r[k] not in ("", None) else None
    return rows


def episodes(rows, threshold):
    out, above = [], False
    for r in rows:
        now = r["decrease"] is not None and r["decrease"] > threshold
        if now and not above:
            out.append([r["date"], None])
        elif above and not now:
            out[-1][1] = r["date"]
        above = now
    return out


def slide3():
    src = REPO / "experiments" / "output" / "pine_mountain_fit_order"
    exp = read_csv(src / "expectation_order1.csv")
    mon = read_csv(src / "monitoring_order1.csv")
    eps = episodes(mon, THRESHOLD)
    fig = figure()
    fig.text(0.04, 0.955, "First detection is not the disturbance date", fontsize=24, fontweight="bold",
             color=INK, va="top")
    fig.text(0.04, 0.895, "Pine Mountain pixel, central Oregon (fall 2024 fire): BULC-D first flags the spring "
             "snowmelt, months before the fire.", fontsize=14, color=INK2, va="top")
    gs = fig.add_gridspec(2, 2, width_ratios=[1, 2.4], left=0.07, right=0.97, top=0.80, bottom=0.235,
                          hspace=0.15, wspace=0.12)
    ae = fig.add_subplot(gs[0, 0])
    am = fig.add_subplot(gs[0, 1], sharey=ae)
    ap = fig.add_subplot(gs[1, 1], sharex=am)
    note = fig.add_subplot(gs[1, 0])
    note.axis("off")

    ae.plot([r["date"] for r in exp], [r["fitted"] for r in exp], color=MUTED, lw=2.5)
    pts = [(r["date"], r["observed"]) for r in exp if r["observed"] is not None]
    ae.scatter(*zip(*pts), s=50, color=INK, edgecolor="white", lw=1, zorder=3, label="2023 observations (fit)")
    ae.set_title("Expectation: 2023", loc="left", fontsize=17)
    ae.set_ylabel("NBR")
    ae.set_ylim(-0.3, 1.0)

    d = [r["date"] for r in mon]
    am.plot(d, [r["expected"] for r in mon], color=MUTED, lw=2.5, label="expected NBR (2023 fit)")
    for cls, col in (("decrease", DEC), ("unchanged", UNC), ("increase", INC)):
        pts = [(r["date"], r["observed"]) for r in mon if r["observed"] is not None and r["supports"] == cls]
        if pts:
            am.scatter(*zip(*pts), s=55, color=col, edgecolor="white", lw=1, zorder=3,
                       label=f"observed NBR, favors {cls}")
    am.set_title("Monitoring: 2024", loc="left", fontsize=17)
    plt.setp(am.get_yticklabels(), visible=False)
    plt.setp(am.get_xticklabels(), visible=False)

    ap.step(d, [r["decrease"] for r in mon], where="post", color=DEC, lw=2.5, label="P(decrease)")
    ap.axhline(THRESHOLD, color=INK2, lw=1.3, ls=(0, (4, 3)), label=f"decision threshold ({THRESHOLD})")
    end = mon[-1]["date"]
    assert len(eps) == 2, "expected two episodes: spring snowmelt, fall fire"
    kinds = [(SNOW, "\\\\", "Spring snowmelt: FALSE detection"), (DEC, None, "Fall fire: the real disturbance")]
    for (s, e), (col, hatch, label) in zip(eps, kinds):
        for ax in (am, ap):
            ax.axvspan(s, e or end, fc=col, alpha=0.16, lw=0)
            if hatch:
                ax.axvspan(s, e or end, fc="none", ec=col, alpha=0.5, hatch=hatch, lw=0)
        mid = s + ((e or end) - s) / 2 if e else end
        am.text(mid, 0.97, label.replace(": ", ":\n"), ha="center" if e else "right", va="top", fontsize=12, fontweight="bold",
                color=INK if col == SNOW else "white", bbox=dict(fc=col, ec="none", pad=4))
    ap.set_ylim(0, 1)
    ap.set_ylabel("P(decrease)")
    for ax in (ae, am, ap):
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[2, 4, 6, 8, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ae.set_xlim(dt.date(2023, 1, 25), dt.date(2023, 11, 25))
    am.set_xlim(dt.date(2024, 1, 25), dt.date(2024, 11, 25))
    first, last = eps[0][0], eps[-1][0]
    ap.annotate(f"First detection\n{first:%b %d} = snowmelt,\nnot the fire", xy=(first, THRESHOLD),
                xytext=(dt.date(2024, 1, 30), 0.66), fontsize=12, color=INK, va="top",
                arrowprops=dict(arrowstyle="->", color=SNOW, lw=1.6))
    ap.annotate(f"Last detection {last:%b %d}\n= the fire", xy=(last, THRESHOLD), xytext=(dt.date(2024, 7, 10), 0.88),
                fontsize=12.5, color=INK, va="top", arrowprops=dict(arrowstyle="->", color=DEC, lw=1.6))
    ap.text(0.99, 0.04, "Season ends as DECREASE (confirmed)", transform=ap.transAxes, ha="right", va="bottom",
            fontsize=12.5, color="white", fontweight="bold", bbox=dict(fc=DEC, ec="none", pad=4))
    ep_text = "; ".join(f"{s:%b %d}–{e:%b %d}" if e else f"{s:%b %d}–season end" for s, e in eps)

    h1, l1 = am.get_legend_handles_labels()
    h2, l2 = ap.get_legend_handles_labels()
    note.legend(h1 + h2 + [mpatches.Patch(fc=SNOW, alpha=0.3, hatch="\\\\", ec=SNOW),
                           mpatches.Patch(fc=DEC, alpha=0.3)],
                l1 + l2 + ["episode: snowmelt (false)", "episode: fire (real)"], loc="upper left", fontsize=11.5,
                labelspacing=0.6,
                bbox_to_anchor=(-0.12, 1.0))
    fig.text(0.04, 0.165, f"Why: in 2024 the pixel was snow-free from April while the single 2023 fit still "
             f"expected high spring NBR,\nso spring observations favor decrease. {len(eps)} detection episodes "
             f"({ep_text}). The season ends as decrease,\nso it counts: its first detection is the false "
             "spring one, its last detection is the fire.", fontsize=12.5, color=INK2, va="top", linespacing=1.35)
    fig.text(0.04, 0.06, "SEPARATE EXPERIMENT, not the regional pilot settings: expectation 2023 only, "
             "monitoring 2024, season Feb 1–Nov 15, L8+L9+S2, fit order 1, interactive-app defaults\n"
             "(docs/findings.md 2026-10-13; experiments/output/pine_mountain_fit_order/). Pixel −120.95938, "
             "43.69499.", fontsize=10.5, color=MUTED, va="top", linespacing=1.4)
    save(fig, "slide3_detection_timing_pine_mountain.png")
    return eps


# ---------------------------------------------------------------- slide 4
def ring_km(coords):
    xs, ys = zip(*coords)
    return to_km(xs, ys)


def slide4(spot):
    vec = json.loads((DATA / "vectors.json").read_text())
    fig = figure()
    fig.text(0.04, 0.955, "Regional processing: the Oregon Coast Range pilot", fontsize=24, fontweight="bold",
             color=INK, va="top")
    fig.text(0.04, 0.895, "Batch exports to Earth Engine assets, tile by tile; the products are read back without "
             "rerunning BULC-D.", fontsize=14, color=INK2, va="top")
    ax = fig.add_axes([0.04, 0.08, 0.44, 0.78])
    base_map(ax, image=True)
    overlay(ax, dec26, DEC)
    tile_lines(ax, labels=True)
    tx, ty = ring_km(vec["testsite"][0])
    ax.plot(tx, ty, color="#1baf7a", lw=2.2, zorder=5)
    scale_bar(ax)
    north_arrow(ax)
    ax.add_patch(mpatches.Rectangle((0.8, 18.0), 0.9, 0.9, color=DEC, zorder=6))
    ax.text(2.0, 18.45, "2026 decrease", fontsize=12, va="center", color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=2))
    ax.plot([0.8, 1.7], [16.95, 16.95], color=INK, lw=1.4, ls=(0, (6, 4)), zorder=6)
    ax.text(2.0, 16.95, "10 km tile boundary", fontsize=12, va="center", color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=2))
    ax.plot([0.8, 1.7], [15.9, 15.9], color="#1baf7a", lw=2.2, zorder=6)
    ax.text(2.0, 15.9, "original testsite", fontsize=12, va="center", color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", alpha=0.8, pad=2))

    # Locator.
    loc = fig.add_axes([0.50, 0.55, 0.14, 0.26])
    polys = vec["oregon"] if vec["oregon_type"] == "MultiPolygon" else [vec["oregon"]]
    for poly in polys:
        xs, ys = zip(*poly[0])
        loc.fill(np.array(xs) / 1000, np.array(ys) / 1000, color="#f0efec", ec=INK2, lw=1)
    cx, cy = (X0 + N * 15) / 1000, (Y0 + N * 15) / 1000
    loc.add_patch(mpatches.Rectangle((cx - 10, cy - 10), 20, 20, color=DEC, zorder=3))
    loc.annotate("pilot", xy=(cx + 12, cy), xytext=(cx + 120, cy + 60), fontsize=12, color=INK,
                 arrowprops=dict(arrowstyle="-", color=INK2, lw=1))
    loc.set_aspect("equal")
    loc.axis("off")
    loc.set_title("Oregon", fontsize=13, color=INK2, loc="left")

    dec_km2 = dec26.sum() * PX_KM2
    s26 = next(s for s in spot if s["year"] == "2026")
    lines = [
        ("Area", "400 km² (20 × 20 km), 4 tiles, 30 m"),
        ("Runs", "2024, 2025, 2026 seasons, each vs the\nsame 2018–2023 expectation"),
        ("Exports", "16 batch exports; all succeeded"),
        ("Time", "1–4 min per tile per season"),
        ("Result", f"2026 decrease: {dec_km2:.1f} km² ({100 * dec26.sum() / land.sum():.0f}% of land)"),
    ]
    y = 0.4
    for k, v in lines:
        fig.text(0.50, y, k, fontsize=14, fontweight="bold", color=INK, va="top")
        fig.text(0.585, y, v, fontsize=14, color=INK2, va="top", linespacing=1.3)
        y -= 0.038 * (v.count("\n") + 1) + 0.024
    # Two separate boxes so the spot check is never read as the full validation.
    fig.patches.append(mpatches.FancyBboxPatch((0.665, 0.575), 0.31, 0.265, boxstyle="round,pad=0.008",
                                               transform=fig.transFigure, fc="#f6f5f2", ec=GRID))
    fig.text(0.675, 0.83, "Spot check: 1,600 pixels", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.675, 0.785, "40 × 40 px where all 4 tiles meet,\nrerun live and compared with the exports:\n"
             f"• class: {s26['condition_match']:,} / {s26['land_px']:,} match\n  in 2024, 2025 and 2026\n"
             "• probabilities match to 0.00005\n"
             "• no seams", fontsize=12.5, color=INK2, va="top", linespacing=1.35)
    fig.patches.append(mpatches.FancyBboxPatch((0.665, 0.435), 0.31, 0.105, boxstyle="round,pad=0.008",
                                               transform=fig.transFigure, fc="white", ec=MUTED, ls=(0, (4, 3))))
    fig.text(0.675, 0.53, "Full validation: run on islay", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.675, 0.492, "Results not retrieved for this presentation;\nthe spot check does not replace it.",
             fontsize=12.5, color=INK2, va="top", linespacing=1.3)
    save(fig, "slide4_regional_pilot.png")


# ---------------------------------------------------------------- slide 5
BENCH = [  # (label, sensors, EECU-seconds, minutes) - Earth Engine task history, 2026-10-26, one 10 km tile each
    ("L8, 6 yr (pilot)", "L8", 152.0, 3.0), ("L8, 8 yr", "L8", 471.1, 5.8), ("L8, 10 yr", "L8", 623.6, 4.7),
    ("L8+S2, 2 yr", "L8+S2", 393.2, 5.9), ("L8+S2, 4 yr", "L8+S2", 458.2, 8.0), ("L8+S2, 6 yr", "L8+S2", 640.8, 9.5),
    ("L8+L9+S2, 6 yr", "L8+L9+S2", 652.8, 8.3),
]
BLOCKS = [  # (label, tiles per export, km² per export, EECU-seconds per export (mean), minutes (range))
    ("1 tile", 1, 100, None, "1.0–3.2"), ("2 × 2 tiles", 4, 400, None, "2.4–3.6"), ("4 × 4 tiles", 16, 1600, 3141.4,
                                                                                       "12.8"),
]
SINGLE = [131.8, 136.9, 147.7, 135.1, 142.1, 148.2, 146.8, 141.3, 159.1, 144.1, 234.1, 265.8, 226.5, 178.2, 147.3, 150.2]
BLOCK2 = [435.4, 435.7, 450.7, 490.0]


def slide5():
    fig = figure()
    fig.text(0.04, 0.955, "Processing cost is driven by the expectation period and sensors", fontsize=24,
             fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.895, "Earth Engine batch exports, 2026 season, one 10 × 10 km tile each (benchmark runs, "
             "2026-10-26).", fontsize=14, color=INK2, va="top")
    fig.text(0.04, 0.85, "EECU-seconds (Earth Engine Compute Unit-seconds) = Earth Engine's measure of a task's "
             "computational cost, independent of queue time.", fontsize=13, color=INK, va="top")
    ax = fig.add_axes([0.20, 0.17, 0.36, 0.53])
    labels = [b[0] for b in BENCH][::-1]
    vals = [b[2] for b in BENCH][::-1]
    cols = [SENSOR_COLORS[b[1]] for b in BENCH][::-1]
    mins = [b[3] for b in BENCH][::-1]
    yy = np.arange(len(BENCH))
    ax.barh(yy, vals, color=cols, height=0.62, edgecolor="white", linewidth=2)
    for y, v, m in zip(yy, vals, mins):
        ax.text(v + 12, y, f"{v:.0f}  ({m:.1f} min)", va="center", fontsize=12.5, color=INK)
    ax.set_yticks(yy, labels, fontsize=13.5)
    ax.set_xlim(0, 880)
    ax.set_xlabel("EECU-seconds per tile (wall-clock minutes)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Expectation sensors × length", loc="left", fontsize=17, pad=44)
    handles = [mpatches.Patch(color=c, label=k) for k, c in SENSOR_COLORS.items()]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=12.5,
              handlelength=1.2, columnspacing=1.5, borderaxespad=0.2)

    bx = fig.add_axes([0.66, 0.17, 0.30, 0.53])
    per100 = [np.mean(SINGLE), np.mean(BLOCK2) / 4, 3141.4 / 16]
    names = ["1 tile\n(100 km²)", "2 × 2 tiles\n(400 km²)", "4 × 4 tiles\n(1,600 km²)"]
    wall = ["1.0–3.2 min", "2.4–3.6 min", "12.8 min"]
    bx.bar(range(3), per100, color=SENSOR_COLORS["L8"], width=0.6, edgecolor="white", linewidth=2)
    for i, (v, w) in enumerate(zip(per100, wall)):
        bx.text(i, v + 6, f"{v:.0f}\n{w}", ha="center", va="bottom", fontsize=12.5, color=INK)
    bx.set_xticks(range(3), names, fontsize=12.5)
    bx.set_ylim(0, 290)
    bx.set_ylabel("EECU-seconds per 100 km²")
    bx.grid(axis="y", color=GRID, lw=0.8)
    bx.set_axisbelow(True)
    bx.set_title("Export block size (pilot config)", loc="left", fontsize=17, pad=44)
    fig.text(0.04, 0.085, "Left: expectation 2018–2023 unless noted (8 yr = 2016–2023, 10 yr = 2014–2023; "
             "L8+S2 2/4 yr end 2023), L8+L9 monitoring, otherwise the pilot config. All exports succeeded, "
             "including S2 expectations that fail interactively. shardSize 64/128 did not lower cost "
             "(242–962 EECU-s; not shown).", fontsize=10.5, color=MUTED, va="top", wrap=True)
    fig.text(0.04, 0.035, "Right: 16-tile benchmark area (40 × 40 km) with the pilot config; per-export means. "
             "Wall-clock depends on the Earth Engine queue; tasks ran concurrently.", fontsize=10.5,
             color=MUTED, va="top")
    save(fig, "slide5_processing_performance.png")
    return per100


# ---------------------------------------------------------------- slide 6
EXP = {"A": ("2018–2023", "pilot"), "B": ("2024–2025", "recent only"), "C": ("2018–2025", "extended")}
DIFF = {"dec_a_only": "#eb6834", "dec_b_only": "#1baf7a", "inc_diff": "#6250d6"}  # validated all-pairs (dataviz)


def slide6():
    E = {k: np.load(DATA / f"expectation_{k}.npz") for k in "ABC"}
    o = {k: np.where(land, E[k]["outcome"], -1).astype(int) for k in "ABC"}
    # Config A is the pilot product recomputed live; it must reproduce the asset exactly.
    assert (o["A"][land] == cond["2026"][land]).all(), "live config A does not reproduce the pilot asset"

    rows = {}
    for k in "ABC":
        rows[k] = {"median_obs": float(np.median(E[k]["n_exp"][land])),
                   "decrease_km2": float((o[k] == 0).sum() * PX_KM2),
                   "increase_km2": float((o[k] == 2).sum() * PX_KM2),
                   "agree_with_A_pct": float(100 * (o[k][land] == o["A"][land]).mean())}
    a_dec, b_dec = o["A"] == 0, o["B"] == 0
    keep = {k: [100 * ((o[k] == 0) & a_dec & (dyear == yr)).sum() / (a_dec & (dyear == yr)).sum()
                for yr in (2024, 2025, 2026)] for k in "BC"}
    recov = ((o["B"] == 2) & (o["A"] != 2) & (dyear == 2024)).sum() * PX_KM2
    drop = 100 * (1 - rows["B"]["decrease_km2"] / rows["A"]["decrease_km2"])

    fig = figure()
    fig.text(0.04, 0.955, "How does the expectation period affect detection?", fontsize=24, fontweight="bold",
             color=INK, va="top")
    fig.text(0.04, 0.9, "Experiment on Al's suggestion: the same 2026 monitoring season, three expectation "
             "windows, everything else identical.", fontsize=14, color=INK2, va="top")

    # Maps: A, B, C, then the A-vs-B difference.
    w = 0.165
    h = w * 13.333 / 7.5
    y0 = 0.465
    for x, k in zip((0.04, 0.235, 0.43), "ABC"):
        ax = fig.add_axes([x, y0, w, h])
        base_map(ax)
        overlay(ax, o[k] == 0, DEC)
        overlay(ax, o[k] == 2, INC)
        ax.set_title(f"{k}: {EXP[k][0]} ({EXP[k][1].split()[0]})", loc="left", fontsize=13, color=INK, pad=24,
                     fontweight="bold")
        ax.text(0, 1.015, f"{rows[k]['decrease_km2']:.1f} km² decrease · {rows[k]['median_obs']:.0f} obs",
                transform=ax.transAxes, fontsize=11.5, color=INK2, va="bottom")
        if k == "A":
            scale_bar(ax, km=5, x=0.8, y=0.9)
    ax = fig.add_axes([0.645, y0, w, h])
    base_map(ax)
    overlay(ax, (o["A"] == 2) != (o["B"] == 2), DIFF["inc_diff"], alpha=0.35)
    overlay(ax, a_dec & ~b_dec, DIFF["dec_a_only"])
    overlay(ax, b_dec & ~a_dec, DIFF["dec_b_only"])
    north_arrow(ax, y=15.8)
    ax.set_title("A vs B: where they differ", loc="left", fontsize=13, color=INK, pad=24, fontweight="bold")
    ax.text(0, 1.015, f"same class on {rows['B']['agree_with_A_pct']:.0f}% of land", transform=ax.transAxes,
            fontsize=11.5, color=INK2, va="bottom")

    # Legends: classes under maps A-C; difference classes beside the difference map.
    for x, (c, t) in zip((0.04, 0.15, 0.26, 0.42),
                         ((DEC, "decrease"), (INC, "increase"), (LAND, "unchanged land"), (WATER, "water (masked)"))):
        swatch(fig, x, 0.43, c, t)
    for i, (c, t, al) in enumerate(((DIFF["dec_a_only"], "decrease under\nA only", 1),
                                    (DIFF["dec_b_only"], "decrease under\nB only", 1),
                                    (DIFF["inc_diff"], "increase differs\n(muted)", 0.35),
                                    (LAND, "same class\nunder A and B", 1))):
        swatch(fig, 0.825, 0.745 - i * 0.075, c, t, alpha=al)

    # Key findings: three numbers, readable without the maps.
    fig.text(0.04, 0.375, "Key findings, A vs B: the recent window mainly removes older, persistent detections",
             fontsize=15, fontweight="bold",
             color=INK, va="top")
    tiles = [(f"−{drop:.0f}%", f"decrease area\n{rows['A']['decrease_km2']:.1f} → {rows['B']['decrease_km2']:.1f} km²"),
             (f"{keep['B'][2]:.0f}%", "of decreases first\nconfirmed in 2026 are\nstill decrease under B"),
             (f"{keep['B'][0]:.0f}%", "of 2024-or-earlier\ndetections are still\ndecrease under B")]
    for i, (big, txt) in enumerate(tiles):
        x = 0.04 + i * 0.183
        fig.patches.append(mpatches.FancyBboxPatch((x, 0.085), 0.172, 0.235, boxstyle="round,pad=0.006",
                                                   transform=fig.transFigure, fc="#f6f5f2", ec=GRID))
        fig.text(x + 0.012, 0.31, big, fontsize=34, fontweight="bold", color=INK, va="top")
        fig.text(x + 0.012, 0.222, txt, fontsize=12.5, color=INK2, va="top", linespacing=1.3)

    # Scientific qualifications.
    fig.patches.append(mpatches.FancyBboxPatch((0.6, 0.085), 0.37, 0.235, boxstyle="round,pad=0.006",
                                               transform=fig.transFigure, fc="white", ec=MUTED))
    fig.text(0.61, 0.312, "Read with care", fontsize=13.5, fontweight="bold", color=INK, va="top")
    fig.text(0.61, 0.278, "• No forest mask: all land-cover types included.\n"
             "• Fewer detections ≠ better accuracy; no reference\n  data were compared.\n"
             f"• B has fewer observations ({rows['B']['median_obs']:.0f} vs {rows['A']['median_obs']:.0f} per pixel) "
             "and\n  may treat 2024–2025 disturbances as normal\n"
             f"  ({recov:.1f} km² of 2024 detections become 2026 increase).\n"
             "• Shows how long detections persist, not accuracy.",
             fontsize=11, color=INK2, va="top", linespacing=1.25)

    fig.text(0.04, 0.06, "Regional pilot (400 km²), 2026 Jun 1–Sep 30, L8 expectation, L8+L9 monitoring, "
             "thresholds 0.65 / 0.75, 30 m. obs = median clear expectation observations per pixel.\n"
             "A = the exported pilot product, recomputed live and matching it on all 443,427 land pixels; B and C "
             "computed live with only the expectation years changed. No assets written.", fontsize=10, color=MUTED, va="top", linespacing=1.35)
    save(fig, "slide6_expectation_period.png")
    return {"configs": rows, "still_decrease_pct_by_detection_year": keep,
            "B_increase_on_2024_detections_km2": float(recov), "B_decrease_reduction_pct": float(drop)}

if __name__ == "__main__":
    spot = []
    for f in sorted(DATA.glob("spot_check_*.json")):
        spot.extend(json.loads(f.read_text()))
    spot = list({s["year"]: s for s in spot}.values())
    p1 = slide1()
    counts, total = slide2()
    eps = slide3()
    slide4(spot)
    per100 = slide5()
    s6 = slide6()
    summary = {"slide2_counts_px": counts, "slide2_total_px": total,
               "slide2_pct": {k: 100 * v / total for k, v in counts.items()},
               "slide1_pixel": [p1["lon"], p1["lat"]], "slide3_episodes": [[str(s), str(e)] for s, e in eps],
               "slide5_eecu_per_100km2": per100, "slide6": s6, "spot_check": spot}
    (DATA / "figure_numbers.json").write_text(json.dumps(summary, indent=1, default=float))
    print(json.dumps(summary, indent=1, default=float))

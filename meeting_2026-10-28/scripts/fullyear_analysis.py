"""Full-year (year-to-date) expectation comparison vs the original Jun-Sep results; seasonal / snow check.

    python meeting_2026-10-28/scripts/fullyear_analysis.py

Inputs:  data/fullyear/{A26,B26,C26,A25,A24}.npz (expectation_compare_fullyear.py), data/expectation_{A,B,C}.npz
         and data/pilot.npz (Jun-Sep), data/reference.npz (S2, fetch_reference.py), data/snow.npz (fetch_snow.py).
Outputs: figures/supplement_fullyear_comparison.png, figures/supplement_fullyear_snow.png,
         data/fullyear_numbers.json. The Jun-Sep figures are not touched.

Detection year is BULC-D's (algorithmic) in both versions: Jun-Sep uses the pilot's detection_year band;
full-year uses the earliest of the full-year A runs for 2024, 2025, 2026 (YTD) that ended as decrease.
"Spring transient" = a decrease episode whose first crossing is Jan-May but the run does not end as
decrease. S2 support = an independent Sentinel-2 NBR drop >= 0.10, 2025 -> 2026 (not verification).
"""
import json

import numpy as np

from make_figures import (DATA, DEC, GRID, INK, INK2, MUTED, PX_KM2, base_map, figure, land, north_arrow, overlay,
                          pilot, save, scale_bar, swatch)

KEPT, LOST, ADDED = "#2a78d6", "#eb6834", "#1baf7a"   # validated all-pairs (dataviz), as in the target-year supplement
JS_C, FY_C = "#b9b7ae", "#52514e"                      # Jun-Sep (light) vs full-year (dark), always direct-labeled

R = np.load(DATA / "reference.npz")
S = np.load(DATA / "snow.npz")
FY = {k: np.load(DATA / "fullyear" / f"{k}.npz") for k in ("A26", "B26", "C26", "A25", "A24")}
JS = {k: np.load(DATA / f"expectation_{k}.npz") for k in "ABC"}
s2 = np.minimum(R["summer2026_nbr"] - R["summer2025_nbr"], R["late2026_nbr"] - R["late2025_nbr"]) < -0.10


def cls(d):
    return np.where(land, d["outcome"], -1).astype(int)


def km2(m):
    return float(m.sum() * PX_KM2)


def share(m, within):
    return float(100 * (m & within).sum() / max(1, within.sum()))


o_fy = {k: cls(v) for k, v in FY.items()}
o_js = {k: cls(v) for k, v in JS.items()}
dy_fy = np.where(o_fy["A24"] == 0, 2024, np.where(o_fy["A25"] == 0, 2025, np.where(o_fy["A26"] == 0, 2026, 0)))
VERSIONS = {"jun_sep": ({"A": o_js["A"], "B": o_js["B"], "C": o_js["C"]}, pilot["detection_year"],
                        {k: JS[k]["n_exp"] for k in "ABC"}),
            "full_year_ytd": ({"A": o_fy["A26"], "B": o_fy["B26"], "C": o_fy["C26"]}, dy_fy,
                              {k: FY[k + "26"]["n_exp"] for k in "ABC"})}


def summarize(o, dy, n_exp):
    a = o["A"] == 0
    new = a & (dy == 2026)
    kept, lost, added = new & (o["B"] == 0), new & (o["B"] != 0), (o["B"] == 0) & ~a
    return {
        "decrease_km2": {k: km2(o[k] == 0) for k in "ABC"},
        "increase_km2": {k: km2(o[k] == 2) for k in "ABC"},
        "median_exp_obs": {k: float(np.median(n_exp[k][land])) for k in "ABC"},
        "A_decrease_by_detection_year_km2": {y: km2(a & (dy == y)) for y in (2024, 2025, 2026)},
        "still_decrease_under_B_pct": {y: share(o["B"] == 0, a & (dy == y)) for y in (2024, 2025, 2026)},
        "still_decrease_under_C_pct": {y: share(o["C"] == 0, a & (dy == y)) for y in (2024, 2025, 2026)},
        "target_year_km2": {"retained": km2(kept), "lost": km2(lost), "added": km2(added)},
        "target_year_s2_pct": {"retained": share(s2, kept), "lost": share(s2, lost), "added": share(s2, added)},
        "same_class_as_A_pct": {k: float(100 * np.mean(o[k][land] == o["A"][land])) for k in "BC"},
        "_masks": (kept, lost, added),
    }


res = {v: summarize(*args) for v, args in VERSIONS.items()}


def spring_snow_share(years):
    clear = sum(S[f"clear_spring{y}"] for y in years).astype(float)
    snow = sum(S[f"snow_spring{y}"] for y in years)
    return np.where(clear > 0, snow / np.maximum(clear, 1), 0)


def spring_transient(k):
    d = FY[k]
    doy = d["first_dec"] % 1000
    return (d["episodes"] > 0) & (o_fy[k] != 0) & (d["first_dec"] > 0) & (doy < 152)


SNOW_BINS = [(0, 0.001, "none"), (0.001, 0.05, "< 5%"), (0.05, 0.15, "5–15%"), (0.15, 1.01, "> 15%")]
exp_snow = {"A": spring_snow_share(range(2018, 2024)), "B": spring_snow_share([2024, 2025])}
transient = {k: spring_transient(k + "26") for k in "AB"}
year_snow = {y: float(100 * S[f"snow_spring{y}"][land].sum() / S[f"clear_spring{y}"][land].sum())
             for y in range(2018, 2027)}
doy_a = FY["A26"]["first_dec"] % 1000
new_fy = (o_fy["A26"] == 0) & (dy_fy == 2026)
months = np.minimum((doy_a - 1) // 30.5, 11).astype(int)
snow_numbers = {
    "spring_snow_share_of_clear_obs_pct": year_snow,
    "spring_transient_pct_by_expectation_snow": {
        k: {lab: share(transient[k], land & (exp_snow[k] >= lo) & (exp_snow[k] < hi)) for lo, hi, lab in SNOW_BINS}
        for k in "AB"},
    "spring_transient_km2": {k: km2(spring_transient(k + "26")) for k in "ABC"} | {
        "A25": km2(spring_transient("A25")), "A24": km2(spring_transient("A24"))},
    "spring_transient_s2_pct": {k: share(s2, transient[k]) for k in "AB"},
    "A_2026_first_by_first_crossing_month_km2": [km2(new_fy & (months == m)) for m in range(10)],
    "A_2026_first_by_first_crossing_month_s2_pct": [share(s2, new_fy & (months == m)) for m in range(10)],
    "A_2026_first_jan_may_km2": km2(new_fy & (doy_a < 152)), "A_2026_first_jan_may_s2_pct": share(s2, new_fy & (doy_a < 152)),
    "detection_year_moves": {"js_2026_to_fy_2025_km2": km2((pilot["detection_year"] == 2026) & (dy_fy == 2025)),
                             "js_2024_2025_to_fy_2026_km2": km2(np.isin(pilot["detection_year"], [2024, 2025]) & (dy_fy == 2026))},
}
out = {v: {k: x for k, x in r.items() if not k.startswith("_")} for v, r in res.items()}
out["seasonal"] = snow_numbers
(DATA / "fullyear_numbers.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))


# ---------------------------------------------------------------- figure 1: Jun-Sep vs full-year
def comparison_figure():
    fig = figure()
    fig.text(0.04, 0.955, "Full-year monitoring (2026 year-to-date) vs Jun–Sep", fontsize=22, fontweight="bold",
             color=INK, va="top")
    fig.text(0.04, 0.9, "Same pilot and settings; expectation and monitoring both widened to the full year. 2026 "
             "observations through Oct 27, 2026 (year-to-date).\nDetection year is BULC-D's (algorithmic) in both; "
             "no disturbance year is verified. No forest mask.", fontsize=12.5, color=INK2, va="top",
             linespacing=1.35)
    w = 0.22
    h = w * 13.333 / 7.5
    for i, (v, title) in enumerate((("jun_sep", "Jun–Sep (original)"), ("full_year_ytd", "Full year, 2026 YTD"))):
        ax = fig.add_axes([0.04 + i * 0.235, 0.2, w, h])
        base_map(ax)
        kept, lost, added = res[v]["_masks"]
        for m, c in ((kept, KEPT), (lost, LOST), (added, ADDED)):
            overlay(ax, m, c)
        ax.set_title(title, loc="left", fontsize=14, fontweight="bold", color=INK, pad=6)
        if i == 0:
            scale_bar(ax)
        else:
            north_arrow(ax)
    for i, (c, t) in enumerate(((KEPT, "2026-first, retained by B"), (LOST, "2026-first, lost by B"),
                                (ADDED, "added by B (decrease under B only)"))):
        swatch(fig, 0.04 + (i % 2) * 0.235, 0.155 - (i // 2) * 0.035, c, t, fontsize=11.5)

    js, fy = res["jun_sep"], res["full_year_ytd"]
    rows = [
        ("B removes A's \"2024 or earlier\"", f"{100 - js['still_decrease_under_B_pct'][2024]:.0f}%",
         f"{100 - fy['still_decrease_under_B_pct'][2024]:.0f}%"),
        ("B removes A's \"2025\"", f"{100 - js['still_decrease_under_B_pct'][2025]:.0f}%",
         f"{100 - fy['still_decrease_under_B_pct'][2025]:.0f}%"),
        ("B retains A's 2026-first", f"{js['still_decrease_under_B_pct'][2026]:.0f}%",
         f"{fy['still_decrease_under_B_pct'][2026]:.0f}%"),
        ("Lost by B, km² (S2 support)", f"{js['target_year_km2']['lost']:.1f} ({js['target_year_s2_pct']['lost']:.0f}%)",
         f"{fy['target_year_km2']['lost']:.1f} ({fy['target_year_s2_pct']['lost']:.0f}%)"),
        ("Added by B, km² (S2 support)", f"{js['target_year_km2']['added']:.1f} ({js['target_year_s2_pct']['added']:.0f}%)",
         f"{fy['target_year_km2']['added']:.1f} ({fy['target_year_s2_pct']['added']:.0f}%)"),
        ("Decrease km², A/B/C", " / ".join(f"{js['decrease_km2'][k]:.1f}" for k in "ABC"),
         " / ".join(f"{fy['decrease_km2'][k]:.1f}" for k in "ABC")),
        ("Increase km², A/B/C", " / ".join(f"{js['increase_km2'][k]:.1f}" for k in "ABC"),
         " / ".join(f"{fy['increase_km2'][k]:.1f}" for k in "ABC")),
        ("Expectation obs, A/B/C", " / ".join(f"{js['median_exp_obs'][k]:.0f}" for k in "ABC"),
         " / ".join(f"{fy['median_exp_obs'][k]:.0f}" for k in "ABC")),
    ]
    x0, xa, xb, y = 0.53, 0.845, 0.915, 0.79
    fig.text(xa, y, "Jun–Sep", fontsize=12.5, fontweight="bold", color=INK2, va="top", ha="right")
    fig.text(xb + 0.06, y, "Full year\n(YTD)", fontsize=12.5, fontweight="bold", color=INK, va="top", ha="right")
    y -= 0.075
    for i, (label, a, b) in enumerate(rows):
        if i == 5:
            y -= 0.015
            fig.lines.append(__import__("matplotlib").lines.Line2D([x0, 0.975], [y + 0.012] * 2, color=GRID, lw=1,
                                                                   transform=fig.transFigure))
        fig.text(x0, y, label, fontsize=11.5, color=INK, va="top")
        fig.text(xa, y, a, fontsize=12.5, color=INK2, va="top", ha="right")
        fig.text(xb + 0.06, y, b, fontsize=12.5, color=INK, va="top", ha="right", fontweight="bold")
        y -= 0.05
    fig.text(x0, 0.27, "The target-year conclusion holds with the full year: B removes most\npersistent older "
             "decrease and keeps most 2026-first decrease. Not an\naccuracy result: the S2 drop is independent "
             "spectral evidence, not\nverified disturbance.", fontsize=12, color=INK2, va="top",
             linespacing=1.35)
    fig.text(0.04, 0.075, "Full year: expectation and monitoring DOY 1–362 (4-day bins; the last bin stays inside the "
             "year); detection year from full-year A runs for 2024, 2025 and 2026 YTD.\nJun–Sep: the Slide 6 runs and "
             "the pilot detection_year. 2026 YTD \"ends as decrease\" = as of the latest observation.\n"
             "Live computation; no assets written. Regional pilot, 400 km², 30 m.", fontsize=10, color=MUTED, va="top", linespacing=1.35)
    save(fig, "supplement_fullyear_comparison.png")


# ---------------------------------------------------------------- figure 2: seasonal / snow
def snow_figure():
    fig = figure()
    fig.text(0.04, 0.955, "Winter and spring observations: snow in the expectation, not in 2026", fontsize=22,
             fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.9, "bulcd masks Landsat cloud and shadow but not the snow flag (QA bit 5), so snow enters the "
             "evidence. 2026 had an almost snow-free spring;\nsnowy expectation springs raise expected NBR, so a "
             "normal snow-free spring can look like a decrease (the Pine Mountain mechanism).", fontsize=12.5,
             color=INK2, va="top", linespacing=1.35)
    # (a) snow share by year
    ax = fig.add_axes([0.06, 0.4, 0.26, 0.36])
    years = list(range(2018, 2027))
    cols = [MUTED if y < 2024 else (FY_C if y < 2026 else DEC) for y in years]
    ax.bar(range(len(years)), [year_snow[y] for y in years], color=cols, width=0.65, edgecolor="white", lw=1.5)
    for i, y in enumerate(years):
        ax.text(i, year_snow[y] + 0.3, f"{year_snow[y]:.1f}" if year_snow[y] >= 0.1 else "<0.1", ha="center",
                fontsize=10.5, color=INK)
    ax.set_xticks(range(len(years)), [str(y)[2:] for y in years], fontsize=11)
    ax.set_ylabel("% of clear spring obs flagged snow", fontsize=12)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Spring (Jan–May) snow, by year", loc="left", fontsize=14, pad=26)
    ax.text(0, 1.03, "A's years 2018–23 · B's years 2024–25 · target 2026", transform=ax.transAxes, fontsize=10.5,
            color=INK2)

    # (b) spring transient rate by expectation snow
    bx = fig.add_axes([0.41, 0.4, 0.26, 0.36])
    xs = np.arange(len(SNOW_BINS))
    t = snow_numbers["spring_transient_pct_by_expectation_snow"]
    for j, (k, c) in enumerate((("A", FY_C), ("B", JS_C))):
        vals = [t[k][lab] for _, _, lab in SNOW_BINS]
        bx.bar(xs + (j - 0.5) * 0.38, vals, width=0.36, color=c, edgecolor="white", lw=1.5)
        for x, v in zip(xs + (j - 0.5) * 0.38, vals):
            bx.text(x, v + 0.08, f"{k}\n{v:.1f}", ha="center", fontsize=9.5, color=INK, linespacing=1.0)
    bx.set_xticks(xs, [lab for _, _, lab in SNOW_BINS], fontsize=11)
    bx.set_xlabel("snow share of the expectation's spring obs", fontsize=11.5)
    bx.set_ylabel("% of land with a spring false episode", fontsize=12)
    bx.set_ylim(0, 5.4)
    bx.grid(axis="y", color=GRID, lw=0.8)
    bx.set_axisbelow(True)
    bx.set_title("Spring transient episodes, 2026", loc="left", fontsize=14, pad=26)
    bx.text(0, 1.03, "A (dark) vs B (light); episodes that do not end as decrease", transform=bx.transAxes,
            fontsize=10.5, color=INK2)

    # (c) 2026-first decrease under A by first-crossing month
    cx = fig.add_axes([0.75, 0.4, 0.22, 0.36])
    km = snow_numbers["A_2026_first_by_first_crossing_month_km2"]
    cx.bar(range(10), km, color=KEPT, width=0.65, edgecolor="white", lw=1.5)
    cx.set_xticks(range(10), list("JFMAMJJASO"), fontsize=11)
    cx.set_ylabel("km²", fontsize=12)
    cx.grid(axis="y", color=GRID, lw=0.8)
    cx.set_axisbelow(True)
    cx.set_title("A's 2026-first decrease", loc="left", fontsize=14, pad=26)
    cx.text(0, 1.03, "by month of first crossing", transform=cx.transAxes, fontsize=10.5, color=INK2)

    sn = snow_numbers
    fig.text(0.04, 0.295, "Findings", fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.255,
             f"• 2026 itself adds no snow-driven false decrease: only {year_snow[2026]:.2f}% of clear 2026 spring obs were "
             "snow-flagged, so this year cannot test snow in the target year.\n"
             f"• Snow in the expectation drives spring false episodes: under A from {t['A']['none']:.1f}% (no "
             f"expectation snow) to {t['A']['> 15%']:.1f}% (> 15%); {sn['spring_transient_km2']['A']:.1f} km², "
             f"S2-supported\n  on only {sn['spring_transient_s2_pct']['A']:.0f}%. B's flatter pattern matches its less snowy years.\n"
             "• With the confirmed rule they mostly do not end as decrease, so the 2026 map barely changes; they "
             "do affect first-detection dates and episode counts.\n"
             f"• Real winter–spring change is caught earlier: {sn['A_2026_first_jan_may_km2']:.1f} km² of A's 2026-first "
             f"decrease first crossed in Jan–May, {sn['A_2026_first_jan_may_s2_pct']:.0f}% S2-supported. Whether each\n"
             "  crossing date is the disturbance or an earlier seasonal crossing (as at Pine Mountain) is not resolved: "
             "the S2 check compares summers, not dates.",
             fontsize=11.5, color=INK2, va="top", linespacing=1.3)
    fig.text(0.04, 0.05, "Snow: Landsat 8/9 C2 L2 QA_PIXEL bit 5 among clear obs (bits 0–4 = 0), Jan 1–May 31, "
             "pilot land pixels. Spring false episode: first P(decrease) crossing\nJan–May and the run does not end as "
             "decrease. Full-year runs, 2026 year-to-date (through Oct 27).", fontsize=10, color=MUTED, va="top", linespacing=1.35)
    save(fig, "supplement_fullyear_snow.png")


comparison_figure()
snow_figure()

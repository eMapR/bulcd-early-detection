"""Target-year question: does the recent expectation (B, 2024-2025) keep new 2026 disturbances while
dropping persistent older ones? Read-only analysis of existing results plus independent evidence.

    python meeting_2026-10-28/scripts/target_year_analysis.py

Inputs:  data/pilot.npz, data/expectation_{A,B}.npz (expectation_compare.py),
         data/reference.npz (fetch_reference.py: Sentinel-2 NBR/RGB 2025-2026, Hansen GFC v1.13, LCMS 2025-11).
Outputs: figures/supplement_target_year_map.png, figures/supplement_target_year_chips.png,
         data/target_year_numbers.json.

Two kinds of "year" are kept apart throughout:
  - algorithmic detection year: the first season BULC-D confirmed a decrease (pilot detection_year band);
  - independent evidence: Sentinel-2 NBR change (a sensor the pilot runs did not use), Hansen loss year and
    LCMS loss. These are other models / spectral evidence, NOT verified disturbance years; nothing here has
    been checked in the field or against a reference sample.
"""
import json

import matplotlib.patches as mpatches
import numpy as np

from make_figures import (DATA, EXTENT, INK, INK2, LAND, MUTED, PX_KM2, GRID, base_map, figure, land, north_arrow,
                          overlay, pilot, save, scale_bar, swatch)

R = np.load(DATA / "reference.npz")
E = {k: np.load(DATA / f"expectation_{k}.npz") for k in "AB"}
dyear = pilot["detection_year"]
o = {k: np.where(land, E[k]["outcome"], -1).astype(int) for k in "AB"}
a_dec, b_dec = o["A"] == 0, o["B"] == 0
new = a_dec & (dyear == 2026)                     # A: first confirmed in 2026 (the target year)
kept, lost, bonly = new & b_dec, new & ~b_dec, b_dec & ~a_dec
persist = {2024: a_dec & (dyear == 2024), 2025: a_dec & (dyear == 2025)}
stable = land & (dyear == 0) & (o["A"] == 1) & (o["B"] == 1)

# Independent spectral evidence: the larger NBR drop of the two same-season S2 comparisons (2025 -> 2026).
drop = np.minimum(R["summer2026_nbr"] - R["summer2025_nbr"], R["late2026_nbr"] - R["late2025_nbr"])
S2_DROP = -0.10
s2 = drop < S2_DROP
hansen = R["hansen_lossyear"]
lcms_loss = {y: (R[f"lcms_change_{y}"] >= 1) & (R[f"lcms_change_{y}"] <= 13) for y in (2023, 2024, 2025)}

LOST, BONLY, KEPT = "#eb6834", "#1baf7a", "#2a78d6"  # validated all-pairs (dataviz)


def km2(m):
    return float(m.sum() * PX_KM2)


def pct(m, within):
    return float(100 * (m & within).sum() / within.sum())


def near(m, px=2):
    """Pixels within px (8-connected) of m, without scipy."""
    out = m.copy()
    for _ in range(px):
        g = out.copy()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                g |= np.roll(np.roll(out, dr, 0), dc, 1)
        out = g
    return out


def hotspot(m, w=40, avoid=()):
    """Center of the w x w window with the most pixels of m, away from earlier picks and the box edge."""
    c = np.pad(m.astype(np.int32), ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    s = c[w:, w:] - c[:-w, w:] - c[w:, :-w] + c[:-w, :-w]
    for r0, c0 in avoid:
        s[max(0, r0 - w):r0 + w, max(0, c0 - w):c0 + w] = -1
    r, cc = np.unravel_index(np.argmax(s), s.shape)
    return int(r + w // 2), int(cc + w // 2)


numbers = {
    "km2": {"A_2026_first": km2(new), "kept": km2(kept), "lost": km2(lost), "B_only": km2(bonly)},
    "lost_B_class_km2": {"unchanged": km2(lost & (o["B"] == 1)), "increase": km2(lost & (o["B"] == 2))},
    "s2_drop_pct": {"kept": pct(s2, kept), "lost": pct(s2, lost), "B_only": pct(s2, bonly),
                    "persist_2024": pct(s2, persist[2024]), "persist_2025": pct(s2, persist[2025]),
                    "stable": pct(s2, stable)},
    "s2_drop_km2": {"lost": km2(lost & s2), "B_only": km2(bonly & s2)},
    "edge_pct": {"lost": pct(near((a_dec | b_dec) & ~lost), lost), "B_only": pct(near((a_dec | b_dec) & ~bonly), bonly)},
    "median_p_decrease": {"kept_A": float(np.median(E["A"]["decrease"][kept])),
                          "lost_A": float(np.median(E["A"]["decrease"][lost])),
                          "lost_B": float(np.median(E["B"]["decrease"][lost])),
                          "B_only_B": float(np.median(E["B"]["decrease"][bonly]))},
    "lost_first_detection_doy_pctl_10_50_90": np.percentile(pilot["first_detection_doy_2026"][lost], [10, 50, 90]).tolist(),
    "lost_first_detection_doy_276_pct": pct(pilot["first_detection_doy_2026"] == 276, lost),
    "kept_first_detection_doy_pctl_10_50_90": np.percentile(pilot["first_detection_doy_2026"][kept], [10, 50, 90]).tolist(),
    "hansen_pct": {"persist_2024_loss_2022_2024": pct(np.isin(hansen, [22, 23, 24]), persist[2024]),
                   "persist_2025_loss_2025": pct(hansen == 25, persist[2025]),
                   "kept_loss_2025": pct(hansen == 25, kept), "kept_loss_2018_2025": pct((hansen >= 18), kept),
                   "lost_loss_2018_2025": pct(hansen >= 18, lost), "B_only_loss_2001_2017": pct((hansen > 0) & (hansen < 18), bonly)},
    "lcms_loss_pct": {"persist_2024_2023_or_2024": pct(lcms_loss[2023] | lcms_loss[2024], persist[2024]),
                      "persist_2025_2025": pct(lcms_loss[2025], persist[2025]),
                      "kept_2025": pct(lcms_loss[2025], kept)},
    "s2_drop_threshold": S2_DROP,
}
(DATA / "target_year_numbers.json").write_text(json.dumps(numbers, indent=1))
print(json.dumps(numbers, indent=1))
N_ = numbers


# ---------------------------------------------------------------- figure 1: map + evidence
def map_figure():
    fig = figure()
    fig.text(0.04, 0.955, "Target year 2026: what the recent expectation keeps, loses and adds", fontsize=22,
             fontweight="bold", color=INK, va="top")
    fig.text(0.04, 0.9, "Supplement to Slide 6: 2026 first detections under A (2018–2023) vs B (2024–2025).\n"
             "Detection year here is BULC-D's (algorithmic); no disturbance year has been independently verified.", fontsize=13, color=INK2,
             va="top", linespacing=1.35)
    ax = fig.add_axes([0.04, 0.09, 0.42, 0.42 * 13.333 / 7.5])
    base_map(ax)
    for m, col in ((kept, KEPT), (lost, LOST), (bonly, BONLY)):
        overlay(ax, m & ~s2, col, alpha=0.35)
        overlay(ax, m & s2, col)
    scale_bar(ax)
    north_arrow(ax)
    items = [(KEPT, f"Retained: 2026 first detection under A and B ({N_['km2']['kept']:.1f} km²)"),
             (LOST, f"Lost: A's 2026 first detection, not B ({N_['km2']['lost']:.1f} km²)"),
             (BONLY, f"Added: decrease under B only ({N_['km2']['B_only']:.1f} km²)")]
    for i, (c, t) in enumerate(items):
        swatch(fig, 0.5, 0.80 - i * 0.04, c, t, fontsize=12.5)
    fig.text(0.5, 0.67, "solid: S2 NBR dropped ≥ 0.10 · faded: no S2 drop", fontsize=11.5, color=INK2, va="center")

    # Evidence bars: share with an independent S2 NBR drop.
    bx = fig.add_axes([0.66, 0.36, 0.30, 0.25])
    groups = [("Retained", N_["s2_drop_pct"]["kept"], KEPT), ("Lost", N_["s2_drop_pct"]["lost"], LOST),
              ("Added (B only)", N_["s2_drop_pct"]["B_only"], BONLY),
              ("Stable land (control)", N_["s2_drop_pct"]["stable"], MUTED)]
    yy = np.arange(len(groups))
    bx.barh(yy, [g[1] for g in groups], color=[g[2] for g in groups], height=0.6, edgecolor="white", lw=2)
    for y, (_, v, _) in zip(yy, groups):
        bx.text(v + 2, y, f"{v:.0f}%", va="center", fontsize=12.5, color=INK)
    bx.set_yticks(yy, [g[0] for g in groups], fontsize=12.5)
    bx.invert_yaxis()
    bx.set_xlim(0, 112)
    bx.set_xticks([0, 50, 100], ["0", "50%", "100%"], fontsize=11)
    bx.tick_params(axis="y", length=0)
    bx.spines["left"].set_visible(False)
    bx.grid(axis="x", color=GRID, lw=0.8)
    bx.set_axisbelow(True)
    fig.text(0.5, 0.635, "Share with an independent S2 NBR drop (2025 → 2026)", fontsize=13.5, fontweight="bold",
             color=INK, va="top")

    h = N_["hansen_pct"]
    l = N_["lcms_loss_pct"]
    fig.text(0.5, 0.29, "What B removes is mostly real earlier loss", fontsize=13.5, fontweight="bold", color=INK,
             va="top")
    fig.text(0.5, 0.25, f"• A's persistent \"2024 or earlier\" decrease: Hansen loss 2022–2024 on "
             f"{h['persist_2024_loss_2022_2024']:.0f}%,\n  LCMS loss 2023–2024 on {l['persist_2024_2023_or_2024']:.0f}%.\n"
             f"• A's persistent \"2025\" decrease: Hansen 2025 loss {h['persist_2025_loss_2025']:.0f}%, LCMS 2025 "
             f"loss {l['persist_2025_2025']:.0f}%.\n"
             f"• Retained 2026 detections: Hansen 2018–2025 loss on only {h['kept_loss_2018_2025']:.0f}%, "
             "consistent with\n  new change (neither product covers 2026 yet).",
             fontsize=11.5, color=INK2, va="top", linespacing=1.3)
    fig.text(0.04, 0.045, "S2: Cloud Score+ masked medians, Jul 1–Sep 15 and Sep 15–Oct 27, 2025 vs 2026 (the pilot runs "
             "used Landsat 8/9 only). Hansen GFC v1.13 (loss through 2025);\nLCMS 2025-11 (loss classes 1–13). "
             "Independent spectral evidence and other models, not verified reference data. No forest mask. "
             "Regional pilot, 400 km², 30 m.", fontsize=10, color=MUTED, va="top", linespacing=1.35)
    save(fig, "supplement_target_year_map.png")


# ---------------------------------------------------------------- figure 2: image chips
def rgb(prefix, r, c, w):
    sl = (slice(r - w, r + w), slice(c - w, c + w))
    x = np.dstack([R[f"{prefix}_B4"][sl], R[f"{prefix}_B3"][sl], R[f"{prefix}_B2"][sl]]).astype(float)
    return np.clip(x / 1400.0, 0, 1) ** 0.8  # one fixed stretch for every chip so dates compare


def outline(ax, m, color, w):
    ax.contour(m.astype(float), levels=[0.5], colors=[color], linewidths=1.6, origin="upper",
               extent=(0, 2 * w, 2 * w, 0))


def chips_figure():
    W = 25  # half-width in px: 50 x 50 px = 1.5 km
    picks = []
    for name, m in (("Lost, no S2 drop", lost & ~s2), ("Lost, S2 drop", lost & s2), ("Added (B only), S2 drop", bonly & s2),
                    ("Retained (reference)", kept & s2)):
        r, c = hotspot(m[W:-W, W:-W], w=30, avoid=[(p[1] - W, p[2] - W) for p in picks])
        picks.append((name, r + W, c + W))
    fig = figure()
    fig.text(0.04, 0.955, "What the differences look like in Sentinel-2", fontsize=22, fontweight="bold", color=INK,
             va="top")
    fig.text(0.04, 0.9, "One 1.5 km chip per group (its densest cluster), not a sample. S2 Sep 15–Oct 27 composites; "
             "outlines = BULC-D 2026 classes.", fontsize=13,
             color=INK2, va="top")
    cols = ["Late 2025 (S2)", "Late 2026 (S2)", "Late 2026 + BULC-D"]
    for i, (name, r, c) in enumerate(picks):
        for j, col in enumerate(cols):
            ax = fig.add_axes([0.2 + j * 0.155, 0.66 - i * 0.19, 0.15, 0.17])
            ax.imshow(rgb("late2025" if j == 0 else "late2026", r, c, W), interpolation="nearest")
            ax.set_xticks([])
            ax.set_yticks([])
            if j == 2:
                sl = (slice(r - W, r + W), slice(c - W, c + W))
                for m, colr in ((kept, KEPT), (lost, LOST), (bonly, BONLY)):
                    if m[sl].any():
                        outline(ax, m[sl], colr, W)
            if i == 0:
                ax.set_title(col, fontsize=12.5, color=INK, pad=6)
        lon_r, lon_c = r, c
        fig.text(0.04, 0.745 - i * 0.19, name, fontsize=13, fontweight="bold", color=INK, va="center")
        fig.text(0.04, 0.715 - i * 0.19, f"row {lon_r}, col {lon_c}", fontsize=10.5, color=MUTED, va="center")
    for i, (c, t) in enumerate(((KEPT, "retained"), (LOST, "lost (A only)"), (BONLY, "added (B only)"))):
        fig.patches.append(mpatches.Rectangle((0.69, 0.80 - i * 0.04 - 0.002), 0.02, 0.004,
                                              transform=fig.transFigure, color=c))
        fig.text(0.715, 0.80 - i * 0.04, t + " outline", fontsize=12, color=INK, va="center")
    fig.text(0.69, 0.66, "How to read", fontsize=13.5, fontweight="bold", color=INK, va="top")
    fig.text(0.69, 0.625, "A real 2026 disturbance should look\nintact in late 2025 and cleared or\nbrowned in "
             "late 2026. These are\nvisual impressions from 10–20 m\nimagery, not verification: no field\nor "
             "high-resolution check was done.", fontsize=12, color=INK2, va="top", linespacing=1.35)
    fig.text(0.04, 0.035, "Grid rows/cols are pilot-box pixels (EPSG:5070, 30 m; row 0 = north edge). S2 median "
             "composites, Cloud Score+ ≥ 0.6. Read-only; no BULC-D runs.", fontsize=10, color=MUTED, va="top")
    save(fig, "supplement_target_year_chips.png")
    return picks


map_figure()
print(chips_figure())

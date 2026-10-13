"""Expectation fit order 1 vs 2 vs 3 at Robert's Pine Mountain pixel.

Case (from Robert's GEE-app session, 2026-10): pixel (-120.959384, 43.694992),
near Pine Mountain Observatory, central Oregon, burned in fall 2024. Expectation
2023, monitoring 2024, season Feb 1 - Nov 15 (289 days: no short-season warning
at any order), the interactive apps' defaults otherwise (the original BULC-D
GUI's sensitivity 1, thresholds 0.65 decrease / 0.75 increase, dampening 0.7,
posterior leveler 0.9, starting odds 0.1/0.8/0.1; sensors L8+L9+S2; water
masked, no forest mask). At order 1 the 2023 fit is one cosine with its
minimum in July; in 2024 the pixel was snow-free (NBR ~0.05) from April while
the fit still expected ~0.5, so spring observations count as decrease months
before the October fire.

Same configs as the apps: EarlyDetectionApp.build(controls()) with only the
fit order changed. Expectation fit values come from bulcd's own (private)
fit helpers, read-only, as in gee/tests/run_app_parity.py.

Outputs (experiments/output/pine_mountain_fit_order/):
    expectation_order{n}.csv   2023 bins: observed, fitted
    monitoring_order{n}.csv    2024 bins: pixel_history() rows
    summary.txt                per order: fit, spring vs fall evidence, crossings, final class
    pine_mountain_fit_order.png

    python experiments/pine_mountain_fit_order.py
"""

from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path
from unittest import mock

import ee
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

LON, LAT = -120.95938356858395, 43.69499215695442
SEASON = ((2, 1), (11, 15))
EXPECTATION, MONITORING = (2023, 2023), 2024
ORDERS = (1, 2, 3)
# A small drawn area around the pixel; results at the pixel don't depend on it.
HALF = 0.01
RING = [[LON - HALF, LAT - HALF], [LON + HALF, LAT - HALF], [LON + HALF, LAT + HALF], [LON - HALF, LAT + HALF],
        [LON - HALF, LAT - HALF]]
# Before this date = spring/summer (pre-fire); from it on = the fall fire period.
FIRE_PERIOD = dt.date(2024, 9, 1)
OUT = Path(__file__).parent / "output" / "pine_mountain_fit_order"
COLORS = {1: "#8a887f", 2: "#2a78d6", 3: "#b45f06"}


def expectation_fit(config):
    from bulcd.inputs import _add_fitted_band, _add_harmonic_terms, _fit_expectation_model, organize_inputs
    from bulcd_early_detection.pixel import utm_crs_for
    band = config.reduction.band
    collection = organize_inputs(config).expectation_collection
    fit = _fit_expectation_model(collection, config.modality, band)
    with_fit = collection.map(_add_harmonic_terms).map(
        lambda img: _add_fitted_band(img, fit.coefficients, fit.regressor_names))
    point, crs = ee.Geometry.Point([LON, LAT]), utm_crs_for(LON, LAT)
    reg = with_fit.select([band, "fitted"]).getRegion(point, 30, crs).getInfo()
    h = reg[0]
    rows = sorted(({"date": dt.datetime.fromtimestamp(r[h.index("time")] / 1000, dt.timezone.utc).date(),
                    "observed": r[h.index(band)], "fitted": r[h.index("fitted")]} for r in reg[1:]),
                  key=lambda r: r["date"])
    stats = fit.coefficients.addBands(fit.residual_stddev).addBands(fit.r2).reduceRegion(
        ee.Reducer.first(), point, 30, crs).getInfo()
    return rows, stats, fit.regressor_names


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ee.Initialize(project="bulcd-python-rebuild")
    from bulcd_early_detection import pixel
    from bulcd_early_detection.app import EarlyDetectionApp

    with mock.patch("ee.data.setDeadline"):
        app = EarlyDetectionApp()
    app.expectation.value, app.monitoring_year.value = EXPECTATION, MONITORING
    (app.window.start_month.value, app.window.start_day.value), (app.window.end_month.value,
                                                                 app.window.end_day.value) = SEASON
    OUT.mkdir(parents=True, exist_ok=True)
    results, lines = {}, []
    for order in ORDERS:
        app.fit_order.value = order
        c = app.controls()
        config = app.build(c, aoi_coordinates=RING)
        exp_rows, stats, regressors = expectation_fit(config)
        rows = pixel.pixel_history(config, LON, LAT)
        results[order] = (exp_rows, rows)
        write_csv(OUT / f"expectation_order{order}.csv", exp_rows)
        write_csv(OUT / f"monitoring_order{order}.csv", rows)

        th = c.thresholds
        obs = [r for r in rows if r["zscore"] is not None]
        spring = [r for r in obs if r["date"] < FIRE_PERIOD]
        fall = [r for r in obs if r["date"] >= FIRE_PERIOD]
        pre = [r for r in rows if r["date"] < FIRE_PERIOD]
        clear = [r for r in exp_rows if r["observed"] is not None]
        fitted = [r["fitted"] for r in exp_rows]
        term = lambda name, k: name if k == 1 else f"{name}{k}"   # cos/sin, cos2/sin2, cos3/sin3
        amps = ", ".join(f"{math.hypot(stats[term('cos', k)], stats[term('sin', k)]):.3f} ({k}/yr)"
                         for k in range(1, order + 1))
        dec_cross = pixel.first_crossing(rows, th["decrease"], "decrease")
        pre_cross = pixel.first_crossing(pre, th["decrease"], "decrease")
        final = rows[-1]
        final_class = ("decrease" if final["decrease"] > th["decrease"] else
                       "increase" if final["increase"] > th["increase"] else "unchanged")
        max_pre = max((r["decrease"] for r in pre), default=float("nan"))
        lines += [
            f"Order {order}: {' + '.join(regressors)}",
            f"  expectation 2023: {len(clear)} clear of {len(exp_rows)} bins; constant {stats['constant']:.3f}, "
            f"harmonic amplitudes {amps}; fitted curve {min(fitted):.3f} to {max(fitted):.3f}; "
            f"residual SD {stats['residual_stddev']:.3f}; R2 {stats['r2']:.2f}",
            f"  monitoring 2024: {len(obs)} observations; before {FIRE_PERIOD}: {len(spring)} "
            f"({sum(r['supports'] == 'decrease' for r in spring)} favor decrease, "
            f"{sum(r['supports'] == 'increase' for r in spring)} increase); from {FIRE_PERIOD}: {len(fall)} "
            f"({sum(r['supports'] == 'decrease' for r in fall)} favor decrease)",
            f"  max P(decrease) before {FIRE_PERIOD}: {max_pre:.3f}; first decrease crossing (> {th['decrease']}) "
            f"before {FIRE_PERIOD}: {pre_cross or 'none'}; first crossing overall: {dec_cross or 'none'}",
            f"  final {final['date']}: P = {final['decrease']:.3f} / {final['unchanged']:.3f} / "
            f"{final['increase']:.3f} -> {final_class}",
            "",
        ]
    (OUT / "summary.txt").write_text("\n".join(lines))
    print("\n".join(lines))

    fig, (top, bot) = plt.subplots(2, 1, figsize=(10, 7.5), dpi=110, sharex=True,
                                   gridspec_kw={"height_ratios": [1.3, 1]})
    exp_rows, rows = results[1]
    top.scatter([r["date"] for r in exp_rows if r["observed"] is not None],
                [r["observed"] for r in exp_rows if r["observed"] is not None], s=18, c="#222", zorder=3,
                label="2023 expectation observations")
    top.scatter([r["date"] for r in rows if r["zscore"] is not None],
                [r["observed"] for r in rows if r["zscore"] is not None], s=18, c="#e34948", zorder=3,
                label="2024 monitoring observations")
    for order, (exp_rows, rows) in results.items():
        top.plot([r["date"] for r in exp_rows], [r["fitted"] for r in exp_rows], color=COLORS[order], lw=1.8,
                 label=f"fit, order {order}")
        top.plot([r["date"] for r in rows], [r["expected"] for r in rows], color=COLORS[order], lw=1.8)
        bot.step([r["date"] for r in rows], [r["decrease"] for r in rows], where="post", color=COLORS[order], lw=2,
                 label=f"P(decrease), order {order}")
    bot.axhline(0.65, color="#e34948", ls=":", lw=1, label="decrease threshold (0.65)")
    bot.axvline(FIRE_PERIOD, color="#999", lw=0.8)
    top.set_ylabel("NBR")
    bot.set_ylabel("P(decrease)")
    bot.set_ylim(0, 1.02)
    top.set_title(f"Pine Mountain pixel ({LON:.5f}, {LAT:.5f}): expectation 2023, monitoring 2024, Feb 1 - Nov 15",
                  loc="left", fontsize=11)
    for ax in (top, bot):
        ax.legend(fontsize=8, frameon=False, ncol=2)
        ax.grid(axis="y", color="#e6e5e0", lw=0.8)
    bot.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.tight_layout()
    fig.savefig(OUT / "pine_mountain_fit_order.png", bbox_inches="tight")


if __name__ == "__main__":
    main()

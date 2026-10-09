"""OG GUI chart CSVs vs. Python rebuild: stage-by-stage equivalence test.

Ground truth: chart CSVs exported from the legacy GEE GUI (V53e) for the
reference case in legacy_gui_equivalence.py (testsite, 2024 -> 2025,
L8+L9+S2, NBR, day step 3), for three pixels (PIXELS below), stored under
experiments/reference_data/legacy_gui_charts/<pixel>/ with the GUI's export
filenames kept as-is (see the README there): pixel1 = harvest-like drop,
pixel2 = stable/green (files suffixed _g), pixel3 = increase (suffixed _b).
Values are rounded to 3 decimals there, so "exact" = |diff| <= 0.0005.
`legacy_*` checks refit the Python observations with legacy's fracDOY time
variable (numpy, diagnostic only) to isolate the harmonic-time difference.

Python side: the same bulcd config, sampled at the point at 1 m scale, so
each scene is read at its own native pixel containing the point. A probe
of grids found that this is what reproduces the GUI's NBR (30 m grids do not);
see docs/findings.md 2026-10-04 (second entry).

Variants:
    default         bulcd's normal implementation, configured like the GUI run. Since
                    BULC-D_rebuild decision 0011 that means no S2 scene filter and the
                    legacy fracDOY time axis - the acceptance case.
    s2_scene_filter bulcd's opt-in S2 scene filter (s2_scene_cloud_threshold = 70,
                    CLOUDY_PIXEL_PERCENTAGE <= 70; not legacy), to show what it changes.
(Before decision 0011 the variants were as_is = S2 filter at 70 + years-since-1970 axis,
and s2_nofilter = S2 threshold 100; see docs/findings.md 2026-10-04 to 2026-10-08.)

Investigation only. Writes experiments/output/legacy_gui_csv_compare/<pixel>/:
    <variant>_steps.csv   per time step: GUI and Python values side by side
    summary.txt           agreement statistics per stage

    python experiments/legacy_gui_csv_compare.py [pixel1] [pixel2] [pixel3]
"""

from __future__ import annotations

import csv
import copy
import datetime as dt
import math
from pathlib import Path

import ee
import numpy as np

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.engine import _bin_zscore, run_bulcd
from bulcd.inputs import _add_fitted_band, _add_harmonic_terms, _fit_expectation_model, organize_inputs

from legacy_gui_equivalence import build_config

PIXELS = {
    "pixel1": {"lonlat": (-123.56922, 44.84283), "dir": "pixel1", "files": {
        "exp": "ExpectationYearVsFitofExpectation.csv", "tgt": "TargetYearVsFitofExpectation.csv",
        "res": "TargetPeriodResiduals.csv", "bin": "BinValuesThroughTIme.csv", "prob": "ProbabilityThroughTime.csv",
        "exp_res": None}},
    "pixel2": {"lonlat": (-123.55299, 44.83292), "dir": "pixel2", "files": {
        "exp": "ExpectationYearVsFitOfExpectation_g.csv", "tgt": "TargerYearVsFitOfExpectation_g.csv",
        "res": "TargetPeriodResiduals_g.csv", "bin": "BinValuesThroughTime_g.csv", "prob": "ProbabillityThroughTime_g.csv",
        "exp_res": "ExpectationPeriodResiduals_g.csv"}},
    # Coordinate captured at full precision. An earlier copied coordinate (-123.54755, 44.83627) was a different
    # click, not the chart's point: the GUI's NBR matched nowhere within 150 m of it.
    "pixel3": {"lonlat": (-123.54330474162032, 44.847525314894625), "dir": "pixel3", "files": {
        "exp": "EcpectationYearVsFitofExpectation_b.csv", "tgt": "TargetYearVsFitoFExpectation_b.csv",
        "res": "TargetPeriodResiduals_b.csv", "bin": "BinValuesThroughTime_b.csv", "prob": "ProbabilityThroughTime_b.csv",
        "exp_res": "ExpectationPeriodResiduals_b.csv"}},
}
# Pixel 2 at the location the GUI actually sampled: its S2 values match only inside the 10 m S2 pixel
# ~0.7-10.5 m east / 1.2-11.5 m north of the stated coordinate (offset scan, docs/findings.md); centre of it.
PIXELS["pixel2_gui_location"] = {**PIXELS["pixel2"], "lonlat": (-123.552919, 44.832977)}

REF = Path(__file__).parent / "reference_data" / "legacy_gui_charts"
OUT = Path(__file__).parent / "output" / "legacy_gui_csv_compare"
CRS, SCALE = "EPSG:4326", 1
TOL = 0.0005 + 1e-9
CLASSES = (("drop", "decrease"), ("same", "unchanged"), ("up", "increase"))


def gui(path: Path) -> dict[dt.date, dict]:
    out = {}
    for r in csv.DictReader(open(path)):
        d = dt.datetime.strptime(r.pop("system:time_start"), "%b %d, %Y").date()
        out[d] = {k: (float(v) if v != "" else None) for k, v in r.items()}
    return out


def region(collection: ee.ImageCollection, point: ee.Geometry) -> dict[dt.date, dict]:
    rows = collection.getRegion(point, SCALE, CRS).getInfo()
    h = rows[0]
    return {dt.datetime.fromtimestamp(r[h.index("time")] / 1000, dt.timezone.utc).date(): dict(zip(h, r))
            for r in rows[1:]}


def python_values(config, point) -> tuple[dict, dict, float]:
    cuts = config.bin_cuts
    org = organize_inputs(config)
    fit = _fit_expectation_model(org.expectation_collection, config.modality, "nbr")
    exp = org.expectation_collection.map(_add_harmonic_terms).map(
        lambda im: _add_fitted_band(im, fit.coefficients, fit.regressor_names))
    zs = org.lof_zscore
    bins = zs.map(lambda im: _bin_zscore(im.select("zscore"), cuts).updateMask(im.select("zscore").mask())
                  .copyProperties(im, ["system:time_start"]))
    target = org.expectation_fitted_collection.select(["nbr", "fitted"]).combine(zs).combine(bins)
    probs = run_bulcd(config).probability_stack
    e = region(exp.select(["nbr", "fitted"]), point)
    t = region(target, point)
    p = region(probs, point)
    for d in t:
        t[d].update({c: p[d][c] for _, c in CLASSES})
    sd = ee.ImageCollection([fit.residual_stddev.set("system:time_start", 0)])
    sd = next(iter(region(sd, point).values()))["residual_stddev"]
    return e, t, sd


def stats(pairs: list[tuple[float, float]]) -> str:
    if not pairs:
        return "n=0"
    d = [abs(a - b) for a, b in pairs]
    return (f"n={len(d)} exact={sum(x <= TOL for x in d)}/{len(d)} "
            f"max={max(d):.4f} mean={sum(d) / len(d):.4f}")


def presence(g: dict, p: dict, gk: str, pk: str) -> str:
    gd = {d for d, r in g.items() if r[gk] is not None}
    pd = {d for d, r in p.items() if r.get(pk) is not None}
    return (f"GUI {len(gd)}, Python {len(pd)}, both {len(gd & pd)}; "
            f"GUI-only {sorted(x.isoformat() for x in gd - pd)}; Python-only {sorted(x.isoformat() for x in pd - gd)}")


def legacy_fit(e: dict, t: dict):
    """Refit Python's expectation observations with legacy fracDOY = (0-based DOY of bin end) / 365."""
    def X(ds):
        f = np.array([(d.timetuple().tm_yday - 1) / 365 for d in ds])
        return np.column_stack([np.ones_like(f), np.cos(2 * math.pi * f), np.sin(2 * math.pi * f)])
    ed = sorted(e)
    y = np.array([np.nan if e[d]["nbr"] is None else e[d]["nbr"] for d in ed])
    ok = ~np.isnan(y)
    beta, *_ = np.linalg.lstsq(X(ed)[ok], y[ok], rcond=None)
    return dict(zip(ed, X(ed) @ beta)), dict(zip(sorted(t), X(sorted(t)) @ beta))


def compare(label: str, config, pixel: dict, out: Path) -> list[str]:
    fl = pixel["files"]
    point = ee.Geometry.Point(list(pixel["lonlat"]))
    ref = REF / pixel["dir"]
    ge, gt, gr, gb, gp = (gui(ref / fl[k]) for k in ("exp", "tgt", "res", "bin", "prob"))
    e, t, sd = python_values(config, point)
    le, lt = legacy_fit(e, t)
    s = [f"=== {label} ===", f"python residual SD {sd:.5f} -> denominator {max(sd, 0.05):.5f}"]
    s.append(f"time steps: expectation GUI {len(ge)} / Python {len(e)}, same dates: {sorted(ge) == sorted(e)}; "
             f"target GUI {len(gt)} / Python {len(t)}, same dates: {sorted(gt) == sorted(t)}")

    def pairs(g, gk, p, pk, dates=None):
        return [(g[d][gk], p[d][pk]) for d in (dates or g) if d in p and g[d][gk] is not None and p[d].get(pk) is not None]

    s.append("1 expectation NBR presence: " + presence(ge, e, "nbr", "nbr"))
    s.append("  expectation NBR     " + stats(pairs(ge, "nbr", e, "nbr")))
    s.append("2 expectation fitted  " + stats(pairs(ge, "fitted", e, "fitted")))
    s.append("  legacy-fracDOY refit " + stats([(ge[d]["fitted"], le[d]) for d in ge if d in le]))
    if fl["exp_res"]:
        gx = gui(ref / fl["exp_res"])
        py_xres = {d: {"res": None if r["nbr"] is None else r["nbr"] - r["fitted"]} for d, r in e.items()}
        s.append("  expectation residual " + stats(pairs(gx, "expectationDifferenceOptical", py_xres, "res"))
                 + "; legacy-fracDOY refit " + stats([(gx[d]["expectationDifferenceOptical"], e[d]["nbr"] - le[d])
                                                       for d in gx if gx[d]["expectationDifferenceOptical"] is not None
                                                       and e.get(d, {}).get("nbr") is not None]))
        s.append("  expectation residual presence: " + presence(gx, py_xres, "expectationDifferenceOptical", "res"))
    s.append("3 target NBR presence: " + presence(gt, t, "nbr", "nbr"))
    s.append("  target NBR          " + stats(pairs(gt, "nbr", t, "nbr")))
    s.append("  target fitted       " + stats(pairs(gt, "fitted", t, "fitted")))
    s.append("  legacy-fracDOY refit " + stats([(gt[d]["fitted"], lt[d]) for d in gt if d in lt]))
    py_res = {d: {"res": None if r["nbr"] is None else r["nbr"] - r["fitted"]} for d, r in t.items()}
    s.append("4 target residual     " + stats(pairs(gr, "targetDifference", py_res, "res")))
    s.append("  legacy-fracDOY refit " + stats([(gr[d]["targetDifference"], t[d]["nbr"] - lt[d]) for d in gr
                                                if gr[d]["targetDifference"] is not None and t.get(d, {}).get("nbr") is not None]))
    zs = [r["zscore"] for r in t.values() if r.get("zscore") is not None]
    if zs:
        s.append(f"  python z range {min(zs):.2f}..{max(zs):.2f}; nearest z to a bin cut: "
                 f"{min(abs(z - c) for z in zs for c in config.bin_cuts):.3f}")
    s.append("  residual presence: " + presence(gr, py_res, "targetDifference", "res"))
    bp = [(g, p) for g, p in pairs(gb, "band", t, "bin")]
    s.append(f"5 bins: agree {sum(a == b for a, b in bp)}/{len(bp)}; presence: " + presence(gb, t, "band", "bin"))
    mism = [(d.isoformat(), gb[d]["band"], t[d]["bin"], round(t[d]["zscore"], 3)) for d in sorted(gb)
            if d in t and gb[d]["band"] is not None and t[d].get("bin") is not None and gb[d]["band"] != t[d]["bin"]]
    if mism:
        s.append(f"  bin mismatches (date, GUI, Python, Python z): {mism}")

    dates = sorted(gp)
    for lag in (0, 1):
        # lag 1: GUI row i compared with Python step i-1 (GUI row 0 = starting prior)
        diffs = []
        for i, d in enumerate(dates):
            if i - lag < 0:
                continue
            pd_ = dates[i - lag]
            if pd_ in t:
                diffs += [abs(gp[d][g] - t[pd_][c]) for g, c in CLASSES]
        exact = sum(x <= TOL for x in diffs)
        s.append(f"6 probabilities lag {lag}: values exact {exact}/{len(diffs)} max={max(diffs):.4f} mean={sum(diffs) / len(diffs):.4f}")
    s.append(f"  GUI first row {dates[0]}: " + "/".join(f"{gp[dates[0]][g]}" for g, _ in CLASSES)
             + "  (legacy starting prior = 0.1/0.8/0.1)")
    g_cross = next((d for d in dates if gp[d]["drop"] > 0.5), None)
    p_cross = next((d for d in sorted(t) if t[d]["decrease"] > 0.5), None)
    s.append(f"7 first P(drop)>0.5: GUI row {g_cross}, Python step {p_cross}")
    same = [gp[d]["same"] for d in dates]
    s.append(f"  GUI P(same): min {min(same)} max {max(same)} final {same[-1]}; "
             f"GUI P(drop) max {max(gp[d]['drop'] for d in dates)}, P(up) max {max(gp[d]['up'] for d in dates)}")
    s.append("  final: GUI " + "/".join(f"{gp[dates[-1]][g]}" for g, _ in CLASSES)
             + f" ({dates[-1]}, = posterior after step {dates[-2]}); Python after {dates[-2]}: "
             + "/".join(f"{t[dates[-2]][c]:.3f}" for _, c in CLASSES)
             + f"; Python after last step {max(t)} (never plotted by the GUI): "
             + "/".join(f"{t[max(t)][c]:.3f}" for _, c in CLASSES))

    rows = []
    for i, d in enumerate(sorted(gt)):
        pr, prev = t.get(d, {}), t.get(dates[i - 1], {}) if i else {}
        rows.append({
            "date": d.isoformat(),
            "exp_date": sorted(ge)[i].isoformat() if i < len(ge) else "",
            "gui_exp_nbr": ge[sorted(ge)[i]]["nbr"], "py_exp_nbr": e.get(sorted(ge)[i], {}).get("nbr"),
            "gui_exp_fitted": ge[sorted(ge)[i]]["fitted"], "py_exp_fitted": e.get(sorted(ge)[i], {}).get("fitted"),
            "gui_nbr": gt[d]["nbr"], "py_nbr": pr.get("nbr"), "gui_fitted": gt[d]["fitted"], "py_fitted": pr.get("fitted"),
            "gui_residual": gr[d]["targetDifference"], "py_residual": py_res.get(d, {}).get("res"),
            "py_z": pr.get("zscore"), "gui_bin": gb[d]["band"], "py_bin": pr.get("bin"),
            **{f"gui_P_{g}": gp[d][g] for g, _ in CLASSES},
            **{f"py_P_{g}_prev_step": prev.get(c) for g, c in CLASSES},
            **{f"py_P_{g}_same_step": pr.get(c) for g, c in CLASSES},
        })
    with open(out / f"{label}_steps.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return s


def main() -> None:
    import sys
    default = build_config()
    s2_filter = copy.deepcopy(default)
    for p in (s2_filter.evidence.expectation, s2_filter.evidence.target):
        p.sensors["S2"].s2_scene_cloud_threshold = 70
    for name in sys.argv[1:] or PIXELS:
        out = OUT / name
        out.mkdir(parents=True, exist_ok=True)
        lines = [f"##### {name} {PIXELS[name]['lonlat']}"]
        for label, cfg in (("default", default), ("s2_scene_filter", s2_filter)):
            lines += compare(label, cfg, PIXELS[name], out) + [""]
        (out / "summary.txt").write_text("\n".join(lines))
        print("\n".join(lines))


if __name__ == "__main__":
    main()

"""GEE app <-> Python app parity.

Runs gee/app.js under Node (tests/app_extract.js, stub `ui`), drives it
through its own buttons and map-click handler, and compares with the Python
app's own code (src/bulcd_early_detection) on the same settings:

1. Legacy reference case (tests/reference_case.js, a test fixture; not in the
   GUI), through the app's modules: its config == BULC-D_rebuild's
   legacy_reference() (the case held to JS <-> Python engine parity in
   gee/tests/run_parity.py); inspector rows and chart values ==
   pixel.pixel_history() at pixels 1-3; condition ==
   outputs._outcome_from_result() over a 30 m box.
2. The GUI (asset area = the testsite, default widgets, "Run Early
   Detection"): no validation shortcuts exposed; the widgets' defaults and the
   config they build == EarlyDetectionApp's defaults and build() (both the
   original BULC-D GUI's settings where it had one: checked against the legacy
   source in controls_check.js and tests/test_app_defaults.py); the condition
   layer follows the original GUI's rule at its thresholds (decrease where
   final P(decrease) > 0.65, increase where P(increase) > 0.75);
   first-detected-season configs == build(controls(y)); condition and
   first-detected-season layers == outputs.outcome_image() and
   combine_season_timing() over the box; inspector == pixel_history() at pixel 1
   (map click) and pixel 3 (typed lon/lat + Submit Pixel); the inspector's
   expectation period (bins, observations, fitted curve, coefficients, residual
   SD, R2) == Python bulcd's expectation fit at those pixels, and its timeline
   chart holds those rows; layer list in the notebook's order.
   Detection timing: the last-detection and detection-episode layers ==
   combine_episode_metrics() over the box; the first-detected-season bands are
   identical with and without the episode bands (existing behavior
   preserved); within each pixel first <= last detection and one episode
   means last == first. 2b: the same with detection timing set to raw in the
   GUI == the confirmed=False combinations.
3. A non-default settings combination (including expectation fit order 2):
   configs == EarlyDetectionApp.build() with the same widget values (no
   computation).
4. Expectation fit orders 2 and 3, each chosen in the GUI's Advanced settings
   and run (order 1 = the default run in 2): config and first-detected-season
   configs == build() with the same fit order (and the modality flags/regressors
   that order means); condition and first-detected-season layers ==
   outcome_image() / combine_season_timing() over the box; inspector rows and
   expectation fit == Python at pixel 1; the run label and expectation summary
   name the order.
5. Robert's Pine Mountain pixel (docs/findings.md, 2026-10-13): the JS and
   Python detection timing images, both inspectors' episodes and the
   documented values agree - first detection Apr 17 (doy 108), last detection
   Sep 24 (doy 268), 2 episodes.

Run from the bulcd env: cd gee/tests && python run_app_parity.py   (~45 min)
Node and bulcd.js come from ../../BULC-D_rebuild/gee (BULCD_GEE overrides).
"""

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ee

HERE = Path(__file__).parent
BULCD_GEE = Path(os.environ.get("BULCD_GEE", HERE.parents[2] / "BULC-D_rebuild" / "gee"))
NODE = os.environ.get("BULCD_NODE", "/Users/clarype/miniconda3/envs/bulcd-gee/bin/node")
TOL = 1e-6
BOX = [-123.5725, 44.8300, -123.5400, 44.8500]
TESTSITE = "projects/bulcd-python-rebuild/assets/testsite"
CLASSES = ("decrease", "unchanged", "increase")
NUMERIC = ("observed", "expected", "zscore", *CLASSES)
# Must match app_extract.js VARIANT.
VARIANT = dict(expectation=(2019, 2023), monitoring_year=2025, start=(5, 15), end=(10, 15), sensitivity=1.5,
               decrease_threshold=0.6, increase_threshold=0.8, timing=True, dampening=0.5, posterior=1.0,
               fit_order=2, sensors={"L8": True, "L9": True, "S2": False}, mask_forest=True, mask_water=True)
# Must match app_extract.js FIT_ORDERS_RUN; order 1 is the default run.
FIT_ORDERS_RUN = (2, 3)
# Must match app_extract.js PM / PM_CONTROLS.
PINE_MOUNTAIN = dict(lon=-120.95938356858395, lat=43.69499215695442, half=0.01, expectation=(2023, 2023),
                     monitoring_year=2024, start=(2, 1), end=(11, 15))
TIMING_BOX_BANDS = ["first_decrease_year", "first_decrease_doy"]
REGRESSORS = {1: ["constant", "cos", "sin"], 2: ["constant", "cos", "sin", "cos2", "sin2"],
              3: ["constant", "cos", "sin", "cos2", "sin2", "cos3", "sin3"]}
# The original BULC-D GUI's thresholds (gee/tests/legacy_gui.js), the default in both apps.
LEGACY_THRESHOLDS = {"decrease": 0.65, "increase": 0.75}

sys.path.insert(0, str(BULCD_GEE / "tests"))
from cases import legacy_reference  # noqa: E402


def region(image):
    return ee.ImageCollection([image.set("system:time_start", 0)]).getRegion(
        ee.Geometry.Rectangle(BOX), 30, "EPSG:32610").getInfo()


def expectation_history(config, lon, lat):
    """The expectation period at one pixel from Python bulcd: the binned
    observations the fit uses, the fitted curve at their dates and the fit's
    per-pixel values (bulcd.inputs internals; diagnostic comparison only)."""
    from bulcd.inputs import _add_fitted_band, _add_harmonic_terms, _fit_expectation_model, organize_inputs
    from bulcd_early_detection.pixel import utm_crs_for
    band = config.reduction.band
    collection = organize_inputs(config).expectation_collection
    fit = _fit_expectation_model(collection, config.modality, band)
    with_fit = collection.map(_add_harmonic_terms).map(
        lambda img: _add_fitted_band(img, fit.coefficients, fit.regressor_names))
    point, crs = ee.Geometry.Point([lon, lat]), utm_crs_for(lon, lat)
    reg = with_fit.select([band, "fitted"]).getRegion(point, 30, crs).getInfo()
    h = reg[0]
    rows = sorted(({"time": r[h.index("time")], "observed": r[h.index(band)], "expected": r[h.index("fitted")]}
                   for r in reg[1:]), key=lambda r: r["time"])
    stats = fit.coefficients.addBands(fit.residual_stddev).addBands(fit.r2).reduceRegion(
        ee.Reducer.first(), point, 30, crs).getInfo()
    return {"rows": rows, "fit": stats, "regressors": fit.regressor_names}


def set_widgets(app, v):
    """Sets the Python app's widgets to `v` (VARIANT's form)."""
    app.expectation.value = v["expectation"]
    app.monitoring_year.value = v["monitoring_year"]
    app.window.start_month.value, app.window.start_day.value = v["start"]
    app.window.end_month.value, app.window.end_day.value = v["end"]
    app.sensitivity.value, app.timing.value = v["sensitivity"], v["timing"]
    app.decrease_threshold.value, app.increase_threshold.value = v["decrease_threshold"], v["increase_threshold"]
    app.dampening.value, app.posterior.value = v["dampening"], v["posterior"]
    app.fit_order.value = v["fit_order"]
    for k, on in v["sensors"].items():
        app.sensors[k].value = on
    app.mask_forest.value, app.mask_water.value = v["mask_forest"], v["mask_water"]


def python_side(pixels):
    from bulcd.engine import run_bulcd
    from bulcd_early_detection import outputs, pixel
    from bulcd_early_detection.app import EarlyDetectionApp

    def build(app, controls):
        return app.build(controls, aoi_asset=TESTSITE)

    pool = ThreadPoolExecutor(8)
    out = {"reference": {}, "notebook": {}, "variant": {}}

    cfg = legacy_reference()
    out["reference"]["config"] = dataclasses.asdict(cfg)
    out["reference"]["rows"] = {k: pool.submit(pixel.pixel_history, cfg, *pixels[k]) for k in pixels}
    out["reference"]["outcome_box"] = pool.submit(
        region, outputs._outcome_from_result(run_bulcd(cfg), cfg, 0.5).select("outcome"))

    app = EarlyDetectionApp()
    c = app.controls()
    config = build(app, c)
    years = app._timing_years() if app.timing.value else []
    geom = ee.FeatureCollection(TESTSITE).geometry()
    nb = out["notebook"]
    nb["widgets"] = dict(expectation=list(app.expectation.value), monitoring_year=app.monitoring_year.value,
                         window=list(app.window.value), sensitivity=app.sensitivity.value,
                         decrease_threshold=app.decrease_threshold.value,
                         increase_threshold=app.increase_threshold.value, timing=app.timing.value, dampening=app.dampening.value,
                         posterior=app.posterior.value, fit_order=app.fit_order.value,
                         timing_confirmed=app.timing_confirmed.value,
                         sensors={k: b.value for k, b in app.sensors.items()},
                         mask_forest=app.mask_forest.value, mask_water=app.mask_water.value,
                         allow_large=app.allow_large.value)
    nb["config"] = dataclasses.asdict(config)
    nb["timing_years"] = years
    nb["timing_configs"] = [dataclasses.asdict(build(app, app.controls(y))) for y in years]
    nb["outcome_box"] = pool.submit(region, outputs.outcome_image(config, c.decision_threshold, c.increase_threshold)
                                    .clip(geom)
                                    .select("outcome"))
    seasons = {y: outputs.detection_timing_image(build(app, app.controls(y)), c.decision_threshold,
                                                 c.increase_threshold, episodes=True)
               for y in years}
    plain = {y: outputs.detection_timing_image(build(app, app.controls(y)), c.decision_threshold,
                                               c.increase_threshold)
             for y in years}
    nb["timing_box"] = pool.submit(region, outputs.combine_season_timing(seasons).clip(geom).select(TIMING_BOX_BANDS))
    nb["timing_box_plain"] = pool.submit(region, outputs.combine_season_timing(plain).clip(geom).select(TIMING_BOX_BANDS))
    nb["episodes_box"] = pool.submit(region, outputs.combine_episode_metrics(seasons).clip(geom))
    out["raw"] = {
        "timing_box": pool.submit(region, outputs.combine_season_timing(seasons, confirmed=False).clip(geom)
                                  .select(TIMING_BOX_BANDS)),
        "episodes_box": pool.submit(region, outputs.combine_episode_metrics(seasons, confirmed=False).clip(geom)),
    }
    nb["rows"] = {k: pool.submit(pixel.pixel_history, config, *pixels[k]) for k in (list(pixels)[0], list(pixels)[2])}
    nb["expectation"] = {k: pool.submit(expectation_history, config, *pixels[k])
                         for k in (list(pixels)[0], list(pixels)[2])}

    set_widgets(app, VARIANT)
    out["variant"]["config"] = dataclasses.asdict(build(app, app.controls()))
    out["variant"]["timing_years"] = app._timing_years()
    out["variant"]["timing_configs"] = [dataclasses.asdict(build(app, app.controls(y)))
                                        for y in app._timing_years()]

    first = list(pixels)[0]
    for order in FIT_ORDERS_RUN:
        app_o = EarlyDetectionApp()
        app_o.fit_order.value = order
        c = app_o.controls()
        config = build(app_o, c)
        years = app_o._timing_years()
        seasons = {y: outputs.detection_timing_image(build(app_o, app_o.controls(y)), c.decision_threshold,
                                                     c.increase_threshold, episodes=True) for y in years}
        out.setdefault("orders", {})[order] = {
            "config": dataclasses.asdict(config), "timing_years": years,
            "timing_configs": [dataclasses.asdict(build(app_o, app_o.controls(y))) for y in years],
            "outcome_box": pool.submit(region, outputs.outcome_image(config, c.decision_threshold, c.increase_threshold)
                                       .clip(geom).select("outcome")),
            "timing_box": pool.submit(region, outputs.combine_season_timing(seasons).clip(geom).select(TIMING_BOX_BANDS)),
            "episodes_box": pool.submit(region, outputs.combine_episode_metrics(seasons).clip(geom)),
            "rows": {first: pool.submit(pixel.pixel_history, config, *pixels[first])},
            "expectation": {first: pool.submit(expectation_history, config, *pixels[first])},
        }

    pm = PINE_MOUNTAIN
    app_pm = EarlyDetectionApp()
    app_pm.expectation.value, app_pm.monitoring_year.value = pm["expectation"], pm["monitoring_year"]
    app_pm.window.start_month.value, app_pm.window.start_day.value = pm["start"]
    app_pm.window.end_month.value, app_pm.window.end_day.value = pm["end"]
    lon, lat, h = pm["lon"], pm["lat"], pm["half"]
    ring = [[lon - h, lat - h], [lon + h, lat - h], [lon + h, lat + h], [lon - h, lat + h], [lon - h, lat - h]]
    c_pm = app_pm.controls()
    cfg_pm = app_pm.build(c_pm, aoi_coordinates=ring)
    pt, crs = ee.Geometry.Point([lon, lat]), pixel.utm_crs_for(lon, lat)
    img = outputs.detection_timing_image(cfg_pm, c_pm.decision_threshold, c_pm.increase_threshold, episodes=True)
    out["pine_mountain"] = {
        "config": dataclasses.asdict(cfg_pm), "threshold": c_pm.decision_threshold,
        "image": pool.submit(lambda: img.reduceRegion(ee.Reducer.first(), pt, 30, crs).getInfo()),
        "combined": pool.submit(lambda: outputs.combine_episode_metrics({2024: img}).reduceRegion(
            ee.Reducer.first(), pt, 30, crs).getInfo()),
        "rows": pool.submit(pixel.pixel_history, cfg_pm, lon, lat),
    }

    def resolve(x):
        if isinstance(x, dict):
            return {k: resolve(val) for k, val in x.items()}
        return x.result() if hasattr(x, "result") else x
    return resolve(out)


def subset_mismatches(js, py, where="config"):
    """Every key bulcd.js sees must equal the Python config's value."""
    if isinstance(js, dict):
        if not isinstance(py, dict):
            return [f"{where}: {js!r} vs {py!r}"]
        return [m for k, v in js.items()
                for m in (subset_mismatches(v, py[k], f"{where}.{k}") if k in py else [f"{where}.{k}: not in Python"])]
    if isinstance(js, list):
        if not isinstance(py, list) or len(js) != len(py):
            return [f"{where}: {js!r} vs {py!r}"]
        return [m for i, (a, b) in enumerate(zip(js, py)) for m in subset_mismatches(a, b, f"{where}[{i}]")]
    if isinstance(js, (int, float)) and isinstance(py, (int, float)) and not isinstance(js, bool):
        return [] if abs(js - py) <= TOL else [f"{where}: {js} vs {py}"]
    return [] if js == py else [f"{where}: {js!r} vs {py!r}"]


def num_close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= TOL)


def compare_pixels(name, js_pixels, py_rows, thresholds):
    failures = []
    for label, rows in py_rows.items():
        j = js_pixels[label]
        bad = []
        if len(j["rows"]) != len(rows):
            bad.append(f"{len(j['rows'])} JS rows vs {len(rows)} Python rows")
        for jr, pr in zip(j["rows"], rows):
            if jr["date"] != str(pr["date"]) or jr["supports"] != pr["supports"] or \
                    not all(num_close(jr[k], pr[k]) for k in NUMERIC):
                bad.append(f"{jr['date']}: JS {jr} vs Python {pr}")
        expected_chart = [[r[c] for c in CLASSES] + list(thresholds) for r in j["rows"]]
        if j["prob_table"] != expected_chart or j["fit_table_rows"] != len(j["rows"]):
            bad.append("chart tables do not hold the inspector rows")
        if "boxes" in j and j["boxes"] != [repr(j["lon"]), repr(j["lat"])]:
            bad.append(f"coordinate boxes {j['boxes']} after selecting {j['lon']}, {j['lat']}")
        n_obs = sum(r["zscore"] is not None for r in rows)
        final = "/".join(f"{rows[-1][c]:.3f}" for c in CLASSES) if rows else "-"
        how = f" via {j['how']}" if "how" in j else ""
        print(f"  {name} {label}{how}: {len(rows)} rows ({n_obs} observations), final {final} - "
              f"{'match' if not bad else f'{len(bad)} MISMATCHES'}")
        for note in j["notes"]:
            print(f"      {note}")
        failures += [f"{name} {label}: {b}" for b in bad[:5]]
    return failures


def compare_expectation(name, js_pixels, py_exp):
    failures = []
    for label, py in py_exp.items():
        j = js_pixels[label]["expectation"]
        bad = []
        if [r["time"] for r in j["rows"]] != [r["time"] for r in py["rows"]]:
            bad.append(f"{len(j['rows'])} JS expectation bins vs {len(py['rows'])} Python")
        for jr, pr in zip(j["rows"], py["rows"]):
            if not (num_close(jr["observed"], pr["observed"]) and num_close(jr["expected"], pr["expected"])):
                bad.append(f"{jr['date']}: JS {jr} vs Python {pr}")
        if j["regressors"] != py["regressors"]:
            bad.append(f"regressors {j['regressors']} vs {py['regressors']}")
        for k, v in py["fit"].items():
            if not num_close(j["fit"].get(k), v):
                bad.append(f"fit {k}: JS {j['fit'].get(k)} vs Python {v}")
        if not j["timeline_matches"]:
            bad.append("timeline chart does not hold the expectation and monitoring rows")
        n_obs = sum(r["observed"] is not None for r in py["rows"])
        print(f"  {name} {label} expectation: {len(py['rows'])} bins ({n_obs} observations), "
              f"fit {', '.join(f'{k} {v:.3f}' for k, v in py['fit'].items() if v is not None)} - "
              f"{'match' if not bad else f'{len(bad)} MISMATCHES'}")
        for line in j["summary"]:
            print(f"      {line}")
        failures += [f"{name} {label} expectation: {b}" for b in bad[:5]]
    return failures


def keyed(reg):
    h = reg[0]
    bands = [b for b in h if b not in ("id", "longitude", "latitude", "time")]
    x, y = h.index("longitude"), h.index("latitude")
    return {(round(r[x], 7), round(r[y], 7), b): r[h.index(b)] for r in reg[1:] for b in bands}


def check_decision_rule(outcome_region, final_region, thresholds):
    """The condition layer against the original GUI's rule, recomputed here
    from the run's final probabilities: decrease where P(decrease) >
    thresholds["decrease"], increase where P(increase) > thresholds["increase"]
    (strict, as its .gt()), else unchanged."""
    from bulcd_early_detection.outputs import DECREASE, INCREASE, UNCHANGED
    out, fin = keyed(outcome_region), keyed(final_region)
    bad, n, between = [], 0, 0
    for (x, y, _), code in out.items():
        dec, inc = fin.get((x, y, "decrease")), fin.get((x, y, "increase"))
        if code is None or code > INCREASE or dec is None:
            continue
        n += 1
        want = DECREASE if dec > thresholds["decrease"] else INCREASE if inc > thresholds["increase"] else UNCHANGED
        between += thresholds["decrease"] < inc <= thresholds["increase"]
        if code != want:
            bad.append(f"condition at {x}, {y}: {code} but P(dec) {dec}, P(inc) {inc} -> {want}")
    print(f"  condition follows the decrease > {thresholds['decrease']} / increase > {thresholds['increase']} rule: "
          f"{'yes' if not bad else 'NO'} ({n} analyzed pixels; {between} with "
          f"{thresholds['decrease']} < P(increase) <= {thresholds['increase']}, unchanged under this rule)")
    return bad[:5] + ([] if n else ["no analyzed pixels to check the decision rule on"])


def check_episodes(timing_region, episodes_region, name):
    """Within each pixel: episodes >= 1 wherever there is a first detection,
    last detection not before the first, and one episode means last == first."""
    t, e = keyed(timing_region), keyed(episodes_region)
    bad, n, multi = [], 0, 0
    for (x, y, b), year in t.items():
        if b != "first_decrease_year" or year is None:
            continue
        n += 1
        first = year * 1000 + t[(x, y, "first_decrease_doy")]
        last = (e.get((x, y, "last_decrease_year")) or 0) * 1000 + (e.get((x, y, "last_decrease_doy")) or 0)
        count = e.get((x, y, "decrease_episodes")) or 0
        multi += count > 1
        if count < 1 or last < first or (count == 1 and last != first):
            bad.append(f"{name} episodes at {x}, {y}: first {first}, last {last}, count {count}")
    print(f"  {name}: first <= last detection, one episode => last == first: {'yes' if not bad else 'NO'} "
          f"({n} detected pixels, {multi} with more than one episode)")
    return bad[:5]


def compare_box(name, js_region, py_region):
    jb, pb = keyed(js_region), keyed(py_region)
    diff = [k for k in set(jb) | set(pb) if not num_close(jb.get(k), pb.get(k))]
    by_band = {}
    for (_, _, b), v in pb.items():
        if v is not None:
            by_band.setdefault(b, {}).setdefault(v, 0)
            by_band[b][v] += 1
    summary = "; ".join(f"{b}: {dict(sorted(c.items()))}" for b, c in by_band.items())
    print(f"  {name}: {len(pb)} values, {len(diff)} differ ({summary})")
    return [f"{name} at {k}: JS {jb.get(k)} vs Python {pb.get(k)}" for k in diff[:5]]


def main():
    from bulcd_early_detection import pixel
    ee.Initialize(project="bulcd-python-rebuild")
    ref = json.loads(subprocess.check_output(
        [NODE, "-e", "console.log(JSON.stringify(require('./reference_case.js').REFERENCE_PIXELS))"], cwd=HERE))
    pixels = {p["label"]: (p["lon"], p["lat"]) for p in ref}
    with tempfile.TemporaryDirectory() as tmp:
        js_out = Path(tmp) / "js.json"
        proc = subprocess.Popen([NODE, str(HERE / "app_extract.js"), str(js_out)], cwd=HERE,
                                env={**os.environ, "BULCD_GEE": str(BULCD_GEE)})
        py = python_side(pixels)
        if proc.wait() != 0:
            sys.exit("app_extract.js failed")
        js = json.loads(js_out.read_text())

    failures = []
    print(f"Test area (testsite asset via the GUI): {js['area_report']['area_km2']:.1f} km2, verdict {js['area_report']['verdict']}")

    print("1. Legacy reference case (test fixture, through the app's modules)")
    f = subset_mismatches(js["reference"]["config"], py["reference"]["config"])
    print(f"  config == legacy_reference(): {'yes' if not f else 'NO'}")
    failures += f
    failures += compare_pixels("reference", js["reference"]["pixels"], py["reference"]["rows"], [0.5])
    failures += compare_box("reference condition", js["reference"]["outcome_box"], py["reference"]["outcome_box"])

    print("2. GUI: asset area, default settings, Run Early Detection")
    visible = " | ".join(js["gui_labels"] + js["gui_buttons"] + js["gui_area_sources"])
    f = [f"GUI exposes validation/testing text: {m!r}" for m in
         ("legacy", "reference case", "reference pixel", "validation", "testsite", "Pixel 1", "Pixel 2", "Pixel 3",
          "parity", "debug") if m.lower() in visible.lower()]
    if js["gui_buttons"] != ["Use this area", "Run Early Detection", "Submit Pixel"]:
        f.append(f"GUI buttons {js['gui_buttons']}")
    if js["gui_area_sources"] != ["Draw on the map", "Earth Engine asset"]:
        f.append(f"area sources {js['gui_area_sources']}")
    print(f"  buttons {js['gui_buttons']}, area sources {js['gui_area_sources']}; "
          f"no validation shortcuts: {'yes' if not f else 'NO'}")
    failures += f
    w, c = py["notebook"]["widgets"], js["notebook"]["controls"]
    widget_pairs = {
        "expectation": ([c["expectation_first"], c["expectation_last"]], w["expectation"]),
        "monitoring_year": (c["monitoring_year"], w["monitoring_year"]),
        "season": ([c["season_start"], c["season_end"]], w["window"]),
        "sensitivity": (c["sensitivity"], w["sensitivity"]),
        "decrease_threshold": (c["decrease_threshold"], w["decrease_threshold"]),
        "increase_threshold": (c["increase_threshold"], w["increase_threshold"]),
        "timing": (c["timing"], w["timing"]), "dampening": (c["dampening"], w["dampening"]),
        "posterior": (c["posterior_leveler"], w["posterior"]), "fit_order": (c["fit_order"], w["fit_order"]),
        "timing_confirmed": (c["timing_confirmed"], w["timing_confirmed"]),
        "sensors": (c["sensors"], w["sensors"]),
        "mask_forest": (c["mask_forest"], w["mask_forest"]), "mask_water": (c["mask_water"], w["mask_water"]),
        "allow_large": (c["allow_large"], w["allow_large"]),
    }
    f = [f"widget default {k}: JS {a!r} vs Python app {b!r}" for k, (a, b) in widget_pairs.items() if a != b]
    print(f"  widget defaults == Python app's: {'yes' if not f else 'NO'}")
    t = (c["decrease_threshold"], c["increase_threshold"])
    if t != (LEGACY_THRESHOLDS["decrease"], LEGACY_THRESHOLDS["increase"]):
        f.append(f"default thresholds {t} != the original GUI's {LEGACY_THRESHOLDS}")
    failures += f
    f = subset_mismatches(js["notebook"]["config"], py["notebook"]["config"])
    if js["notebook"]["timing_years"] != py["notebook"]["timing_years"]:
        f.append(f"timing years JS {js['notebook']['timing_years']} vs {py['notebook']['timing_years']}")
    for y, a, b in zip(py["notebook"]["timing_years"], js["notebook"]["timing_configs"], py["notebook"]["timing_configs"]):
        f += subset_mismatches(a, b, f"timing config {y}")
    print(f"  config and first-detected-season configs ({py['notebook']['timing_years']}) == build(): "
          f"{'yes' if not f else 'NO'}")
    failures += f
    failures += compare_box("notebook last detection / episodes", js["notebook"]["episodes_box"],
                            py["notebook"]["episodes_box"])
    f = compare_box("first detected season with vs without the episode bands (Python)",
                    py["notebook"]["timing_box"], py["notebook"]["timing_box_plain"])
    f += check_episodes(js["notebook"]["timing_box"], js["notebook"]["episodes_box"], "notebook")
    failures += f
    names = [l["name"] for l in js["notebook"]["layers"] if l["name"] not in ("Study area", "Selected pixel")]
    print(f"  layers (bottom to top): {names}")
    shown = [l["name"] for l in js["notebook"]["layers"] if l.get("shown") is not False]
    years = [2024, 2025, 2026]
    expected = [f"True color {y}" for y in years] + [f"NBR composite R={years[0]} G={years[1]} B={years[2]}",
                                                     "First detected season (decrease)", "Last detection (decrease)",
                                                     "Detection episodes (decrease)", "Condition 2026"]
    if names != expected:
        failures.append(f"layer list {names} != notebook order {expected}")
    if [n for n in shown if n not in ("Study area", "Selected pixel")] != ["Condition 2026"]:
        failures.append(f"layers shown at start: {shown}")
    failures += compare_box("notebook condition", js["notebook"]["outcome_box"], py["notebook"]["outcome_box"])
    failures += check_decision_rule(js["notebook"]["outcome_box"], js["notebook"]["final_box"], LEGACY_THRESHOLDS)
    failures += compare_box("notebook first detected season", js["notebook"]["timing_box"], py["notebook"]["timing_box"])
    failures += compare_pixels("notebook", js["notebook"]["pixels"], py["notebook"]["rows"],
                               [LEGACY_THRESHOLDS["decrease"], LEGACY_THRESHOLDS["increase"]])
    failures += compare_expectation("notebook", js["notebook"]["pixels"], py["notebook"]["expectation"])
    # The default run is expectation fit order 1 (the original GUI's constant + unimodal).
    f = [] if c["fit_order"] == 1 and "expectation fit order 1" in js["notebook"]["label"] else \
        [f"default run is not fit order 1: {c['fit_order']}, {js['notebook']['label']!r}"]
    f += [f"default inspector regressors {p['expectation']['regressors']} != {REGRESSORS[1]}"
          for p in js["notebook"]["pixels"].values() if p["expectation"]["regressors"] != REGRESSORS[1]]
    print(f"  default run is expectation fit order 1 ({' + '.join(REGRESSORS[1])}): {'yes' if not f else 'NO'}")
    failures += f

    print("2b. GUI: detection timing raw (Advanced settings), Run")
    f = [] if js["raw"]["controls"]["timing_confirmed"] is False and "detection timing raw" in js["raw"]["label"] else \
        [f"raw run not raw: {js['raw']['label']!r}"]
    failures += f
    failures += compare_box("raw first detected season", js["raw"]["timing_box"], py["raw"]["timing_box"])
    failures += compare_box("raw last detection / episodes", js["raw"]["episodes_box"], py["raw"]["episodes_box"])
    failures += check_episodes(js["raw"]["timing_box"], js["raw"]["episodes_box"], "raw")
    conf, raw = keyed(js["notebook"]["timing_box"]), keyed(js["raw"]["timing_box"])
    more = sum(1 for k, v in raw.items() if k[2] == "first_decrease_year" and v is not None and conf.get(k) is None)
    print(f"  raw adds {more} pixels with a (later retracted) detection to the confirmed layer's")

    print("3. Non-default settings (configs only)")
    f = subset_mismatches(js["variant"]["config"], py["variant"]["config"])
    if js["variant"]["timing_years"] != py["variant"]["timing_years"]:
        f.append(f"timing years JS {js['variant']['timing_years']} vs {py['variant']['timing_years']}")
    for y, a, b in zip(py["variant"]["timing_years"], js["variant"]["timing_configs"], py["variant"]["timing_configs"]):
        f += subset_mismatches(a, b, f"variant timing config {y}")
    print(f"  config and first-detected-season configs ({py['variant']['timing_years']}) == build(): "
          f"{'yes' if not f else 'NO'}")
    failures += f

    print("4. Expectation fit orders (chosen in Advanced settings, Run; order 1 is the default run in 2)")
    for order in FIT_ORDERS_RUN:
        jo, po = js["orders"][str(order)], py["orders"][order]
        f = [] if jo["controls"]["fit_order"] == order else [f"GUI read fit_order {jo['controls']['fit_order']}"]
        f += subset_mismatches(jo["config"], po["config"], f"order {order} config")
        flags = {k for k, v in po["config"]["modality"].items() if v}
        want = {"constant", "unimodal", "bimodal", "trimodal"} - ({"bimodal", "trimodal"} if order == 1 else
                                                                   {"trimodal"} if order == 2 else set())
        if flags != want:
            f.append(f"order {order} modality flags {sorted(flags)} != {sorted(want)}")
        for y, a, b in zip(po["timing_years"], jo["timing_configs"], po["timing_configs"]):
            f += subset_mismatches(a, b, f"order {order} timing config {y}")
        if f"expectation fit order {order}" not in jo["label"]:
            f.append(f"run label does not name fit order {order}: {jo['label']!r}")
        summary = jo["pixels"][list(po["rows"])[0]]["expectation"]["summary"]
        if not any(line.startswith(f"Expectation fit order {order}.") for line in summary):
            f.append(f"inspector summary does not name fit order {order}")
        if js["orders"][str(order)]["pixels"][list(po["rows"])[0]]["expectation"]["regressors"] != REGRESSORS[order]:
            f.append(f"order {order} inspector regressors != {REGRESSORS[order]}")
        warned = any(line.startswith("Warning: Expectation fit order") for line in jo["description"])
        print(f"  order {order}: config, modality {sorted(flags)} and first-detected-season configs == build(): "
              f"{'yes' if not f else 'NO'}; short-season warning shown: {'yes' if warned else 'no'}")
        if not warned:
            f.append(f"order {order} with the default 122-day season shows no warning")
        failures += f
        failures += compare_box(f"order {order} condition", jo["outcome_box"], po["outcome_box"])
        failures += compare_box(f"order {order} first detected season", jo["timing_box"], po["timing_box"])
        failures += compare_box(f"order {order} last detection / episodes", jo["episodes_box"], po["episodes_box"])
        failures += check_episodes(jo["timing_box"], jo["episodes_box"], f"order {order}")
        failures += compare_pixels(f"order {order}", jo["pixels"], po["rows"],
                                   [LEGACY_THRESHOLDS["decrease"], LEGACY_THRESHOLDS["increase"]])
        failures += compare_expectation(f"order {order}", jo["pixels"], po["expectation"])

    print("5. Pine Mountain pixel (docs/findings.md, 2026-10-13)")
    jp, pp = js["pine_mountain"], py["pine_mountain"]
    f = subset_mismatches(jp["config"], pp["config"], "Pine Mountain config")
    want = {"first_decrease_year": 2024, "first_decrease_doy": 108, "last_decrease_year": 2024,
            "last_decrease_doy": 268, "decrease_episodes": 2, "outcome": 0}
    for name, got in (("JS image", jp["image"]), ("Python image", pp["image"])):
        f += [f"{name} {k}: {got.get(k)} != {v}" for k, v in want.items() if got.get(k) != v]
    for name, got in (("JS combined", jp["combined"]), ("Python combined", pp["combined"])):
        f += [f"{name} {k}: {got.get(k)} != {want[k]}" for k in want if k in got and got[k] != want[k]]
    py_eps = [{"start": str(e["start"]), "end": None if e["end"] is None else str(e["end"])}
              for e in pixel.detection_episodes(pp["rows"], pp["threshold"])]
    doc = [{"start": "2024-04-17", "end": "2024-06-08"}, {"start": "2024-09-24", "end": None}]
    if jp["episodes"] != doc or py_eps != doc:
        f.append(f"inspector episodes JS {jp['episodes']} / Python {py_eps} != {doc}")
    if jp["notes"] != pixel.episode_notes(pp["rows"], pp["threshold"]):
        f.append(f"episode notes differ: JS {jp['notes']} vs Python {pixel.episode_notes(pp['rows'], pp['threshold'])}")
    print(f"  image (JS and Python): first {jp['image'].get('first_decrease_doy')}, last "
          f"{jp['image'].get('last_decrease_doy')}, episodes {jp['image'].get('decrease_episodes')}; inspector: "
          f"{jp['notes'][0] if jp['notes'] else '-'} - {'match' if not f else 'MISMATCH'}")
    failures += f

    if failures:
        print("\nAPP PARITY FAILED")
        for line in failures:
            print("  " + line)
        sys.exit(1)
    print("\nAPP PARITY PASSED")


if __name__ == "__main__":
    main()

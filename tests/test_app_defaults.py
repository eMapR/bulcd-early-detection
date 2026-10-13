"""The interactive app's algorithm defaults equal the original BULC-D GUI's
(the same values gee/tests/legacy_gui.js records from the legacy source,
checked for the GEE app in gee/tests/controls_check.js), and the two-threshold
decision rule (no Earth Engine calls)."""

import dataclasses
import datetime
import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from bulcd_early_detection.compare import classify
from bulcd.config.schema import ModalityConfig

from bulcd_early_detection.config import (MonitoringControls, build_config, class_thresholds, config_summary,
                                          fit_order_warning, modality_for_order)
from bulcd_early_detection.outputs import DECREASE, INCREASE, UNCHANGED
from bulcd_early_detection.pixel import crossing_notes

# The original BULC-D GUI (guiBULCD.rtf, legacy/6003.3c-BULC-AdvancedParameters.txt).
LEGACY = {"sensitivity": 1.0, "decrease_threshold": 0.65, "increase_threshold": 0.75, "dampening": 0.7,
          "posterior_leveler": 0.9, "initializing_leveler": 0.7, "mask_forest": False, "mask_water": True}
# Its modalityDictionary: constant + unimodal = expectation fit order 1.
LEGACY_MODALITY = ModalityConfig(constant=True, unimodal=True)
GEE_TESTS = Path(__file__).parents[1] / "gee" / "tests"


def app_module():
    from bulcd_early_detection import app as module
    return module


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    pytest.importorskip("ipyleaflet")
    from bulcd_early_detection.app import EarlyDetectionApp
    with mock.patch("ee.data.setDeadline"):   # needs an initialized Earth Engine; nothing else here does
        return EarlyDetectionApp(aoi_dir=tmp_path_factory.mktemp("aois"))


def test_widgets_default_to_the_original_gui(app):
    assert app.sensitivity.value == LEGACY["sensitivity"]
    assert app.decrease_threshold.value == LEGACY["decrease_threshold"]
    assert app.increase_threshold.value == LEGACY["increase_threshold"]
    assert app.dampening.value == LEGACY["dampening"]
    assert app.posterior.value == LEGACY["posterior_leveler"]
    assert app.mask_forest.value is LEGACY["mask_forest"]
    assert app.mask_water.value is LEGACY["mask_water"]
    assert app.fit_order.value == 1
    assert app.fit_order.options == ((app_module().FIT_ORDER_LABELS[1], 1), (app_module().FIT_ORDER_LABELS[2], 2),
                                     (app_module().FIT_ORDER_LABELS[3], 3))


def test_default_config_carries_the_original_gui_settings(app):
    c = app.controls()
    assert c.thresholds == {"decrease": 0.65, "increase": 0.75}
    config = app.build(c, aoi_asset="x")
    adv = config.bulc_advanced_params
    assert config.sensitivity.z_score_numerator_factor == LEGACY["sensitivity"]
    assert config.sensitivity.z_score_denominator_factor == 0.05
    assert (adv.dampening_factor, adv.posterior_leveler, adv.initializing_leveler) == (0.7, 0.9, 0.7)
    assert (config.study_area.mask_non_forest, config.study_area.mask_water) == (False, True)
    assert config.modality == LEGACY_MODALITY
    # Starting probabilities: one-hot "unchanged" leveled as x * L + (1 - L) / 3.
    L = adv.initializing_leveler
    assert [round((1 - L) / 3, 12), round(L + (1 - L) / 3, 12)] == [0.1, 0.8]


def test_python_and_gee_apps_share_the_algorithm_defaults(app):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    script = ("const c = require('../config.js'), l = require('./legacy_gui').LEGACY_DEFAULTS; "
              "console.log(JSON.stringify({d: c.APP_DEFAULTS, lev: c.INITIALIZING_LEVELER, legacy: l}))")
    gee = json.loads(subprocess.check_output([node, "-e", script], cwd=GEE_TESTS))
    d = gee["d"]
    assert (d["sensitivity"], d["decrease_threshold"], d["increase_threshold"], d["dampening"], d["posterior_leveler"],
            gee["lev"], d["mask_forest"], d["mask_water"]) == tuple(LEGACY.values())
    assert (gee["legacy"]["decrease_threshold"], gee["legacy"]["increase_threshold"]) == (0.65, 0.75)


def test_controls_thresholds():
    assert MonitoringControls().thresholds == {"decrease": 0.5, "increase": 0.5}   # demonstration notebooks
    assert MonitoringControls(decision_threshold=0.65, increase_threshold=0.75).thresholds == \
        {"decrease": 0.65, "increase": 0.75}
    assert class_thresholds(0.6) == {"decrease": 0.6, "increase": 0.6}
    with pytest.raises(ValueError, match="increase_threshold"):
        MonitoringControls(increase_threshold=0.4)


def _run(dec, inc):
    n = len(dec)
    ones = np.ones((1, n))
    return {"decrease": np.array([dec]), "unchanged": 1 - np.array([dec]) - np.array([inc]),
            "increase": np.array([inc]), "land": ones, "forest": ones, "inside": ones}


def test_legacy_thresholds_apply_per_class_with_strict_gt():
    # P(dec) 0.66 > 0.65; exactly 0.65 is not (legacy .gt()); P(inc) 0.70 is below 0.75, 0.76 above, 0.75 not.
    run = _run([0.66, 0.65, 0.10, 0.10, 0.10], [0.10, 0.10, 0.70, 0.76, 0.75])
    classes = classify(run, 0.65, True, False, increase_threshold=0.75)[0]
    assert list(classes) == [DECREASE, UNCHANGED, UNCHANGED, INCREASE, UNCHANGED]
    # One shared threshold would have mapped P(inc) 0.70 as increase.
    assert classify(run, 0.65, True, False)[0][2] == INCREASE


def test_crossing_notes_use_each_class_threshold():
    d = datetime.date
    rows = [{"date": d(2026, 6, 1), "decrease": 0.66, "increase": 0.05},
            {"date": d(2026, 6, 5), "decrease": 0.10, "increase": 0.70},
            {"date": d(2026, 6, 9), "decrease": 0.10, "increase": 0.80}]
    assert crossing_notes(rows, 0.65, 0.75) == [
        "decrease first crossed its threshold (0.65) on 2026-06-01, finished below its threshold (does not count)",
        "increase first crossed its threshold (0.75) on 2026-06-09, finished the season as increase (counts as detected)",
    ]
    assert crossing_notes(rows[1:2], 0.65, 0.75) == ["never crossed a threshold (decrease 0.65, increase 0.75)"]


def test_fit_order_maps_to_cumulative_modality_flags():
    assert MonitoringControls().fit_order == 1   # demonstration notebooks unchanged
    assert build_config(MonitoringControls(), aoi_asset="x").modality == LEGACY_MODALITY
    assert modality_for_order(2) == ModalityConfig(constant=True, unimodal=True, bimodal=True)
    assert modality_for_order(3) == ModalityConfig(constant=True, unimodal=True, bimodal=True, trimodal=True)
    assert build_config(MonitoringControls(fit_order=3), aoi_asset="x").modality == modality_for_order(3)
    with pytest.raises(ValueError, match="fit_order"):
        MonitoringControls(fit_order=4)
    assert dict(config_summary(build_config(MonitoringControls(fit_order=2), aoi_asset="x")))["Seasonal model"] == \
        "expectation fit order 2: average level + cycles of 1 and 2 per year"


def test_fit_order_follows_into_every_run(app):
    """Condition, first-detected-season (controls(y)) and inspector configs all come from controls()."""
    app.fit_order.value = 3
    try:
        for c in (app.controls(), app.controls(2025)):
            assert c.fit_order == 3
            assert app.build(c, aoi_asset="x").modality == modality_for_order(3)
        assert "Warning:" in app.relationship.value and "order 3 with a 122-day season" in app.relationship.value
    finally:
        app.fit_order.value = 1
    assert "Warning" not in app.relationship.value


def test_fit_order_warning_boundaries():
    assert fit_order_warning(1, 30) is None
    assert MonitoringControls(fit_order=2).window_days == 122
    assert MonitoringControls(fit_order=2, season_end="11-30").fit_order_warning is None            # 183 days
    assert "182-day" in MonitoringControls(fit_order=2, season_end="11-29").fit_order_warning
    assert MonitoringControls(fit_order=3, season_start="03-01", season_end="10-31").fit_order_warning is None  # 245
    assert "244-day" in MonitoringControls(fit_order=3, season_start="03-01", season_end="10-30").fit_order_warning


def test_python_and_gee_fit_order_mapping_and_warning_match():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    cases = [(o, s, e) for o in (1, 2, 3) for s, e in (("06-01", "09-30"), ("06-01", "11-30"), ("06-01", "11-29"),
                                                        ("03-01", "10-31"), ("03-01", "10-30"), ("01-01", "12-31"))]
    script = ("const c = require('../config.js'), cases = %s; console.log(JSON.stringify({labels: c.FIT_ORDER_LABELS, "
              "out: cases.map(([o, s, e]) => { const x = Object.assign({}, c.APP_DEFAULTS, {fit_order: o, "
              "season_start: s, season_end: e}); return [c.buildConfig(x, {aoi_asset: 'x'}).modality, "
              "c.fitOrderWarning(x)]; })}))" % json.dumps(cases))
    gee = json.loads(subprocess.check_output([node, "-e", script], cwd=GEE_TESTS))
    assert {int(k): v for k, v in gee["labels"].items()} == app_module().FIT_ORDER_LABELS
    for (order, start, end), (modality, warning) in zip(cases, gee["out"]):
        c = MonitoringControls(season_start=start, season_end=end, fit_order=order)
        py = dataclasses.asdict(build_config(c, aoi_asset="x").modality)
        assert {k: v for k, v in py.items() if v} == modality, (order, start, end)
        assert c.fit_order_warning == warning, (order, start, end)

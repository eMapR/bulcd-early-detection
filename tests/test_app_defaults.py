"""The interactive app's algorithm defaults equal the original BULC-D GUI's
(the same values gee/tests/legacy_gui.js records from the legacy source,
checked for the GEE app in gee/tests/controls_check.js), and the two-threshold
decision rule (no Earth Engine calls)."""

import datetime
import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from bulcd_early_detection.compare import classify
from bulcd_early_detection.config import MonitoringControls, class_thresholds
from bulcd_early_detection.outputs import DECREASE, INCREASE, UNCHANGED
from bulcd_early_detection.pixel import crossing_notes

# The original BULC-D GUI (guiBULCD.rtf, legacy/6003.3c-BULC-AdvancedParameters.txt).
LEGACY = {"sensitivity": 1.0, "decrease_threshold": 0.65, "increase_threshold": 0.75, "dampening": 0.7,
          "posterior_leveler": 0.9, "initializing_leveler": 0.7, "mask_forest": False, "mask_water": True}
GEE_TESTS = Path(__file__).parents[1] / "gee" / "tests"


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


def test_default_config_carries_the_original_gui_settings(app):
    c = app.controls()
    assert c.thresholds == {"decrease": 0.65, "increase": 0.75}
    config = app.build(c, aoi_asset="x")
    adv = config.bulc_advanced_params
    assert config.sensitivity.z_score_numerator_factor == LEGACY["sensitivity"]
    assert config.sensitivity.z_score_denominator_factor == 0.05
    assert (adv.dampening_factor, adv.posterior_leveler, adv.initializing_leveler) == (0.7, 0.9, 0.7)
    assert (config.study_area.mask_non_forest, config.study_area.mask_water) == (False, True)
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

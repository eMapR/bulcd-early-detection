"""Sensor selection for each period (no Earth Engine calls): the expectation
defaults to Landsat 8 only (the config is unchanged), any sensor combination
reaches the config and every timing run, and the sensor warnings
(docs/findings.md, 2026-10-19 and 2026-11-02), with the same text in the GEE
app. Historical years and Landsat 5/7: tests/test_historical_years.py."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from bulcd_early_detection.config import (BASELINE_SENSORS, MONITORING_SENSORS, S2_EXPECTATION_MAX_YEARS, SENSORS,
                                          MonitoringControls, availability_problem, build_config, sensor_warnings,
                                          with_monitoring_sensors)

GEE_TESTS = Path(__file__).parents[1] / "gee" / "tests"
MONITORING = ("L8", "L9", "S2")


@pytest.fixture()
def app(tmp_path):
    pytest.importorskip("ipyleaflet")
    from bulcd_early_detection.app import EarlyDetectionApp
    with mock.patch("ee.data.setDeadline"):
        return EarlyDetectionApp(aoi_dir=tmp_path)


def test_default_expectation_is_landsat_8_only():
    assert BASELINE_SENSORS == ("L8",)
    assert MonitoringControls().expectation_sensors == ("L8",)
    assert list(build_config(MonitoringControls(), aoi_asset="x").evidence.expectation.sensors) == ["L8"]


def test_any_combination_reaches_the_config_in_sensor_order():
    config = build_config(MonitoringControls(expectation_sensors=("S2", "L8")), aoi_asset="x")
    exp = config.evidence.expectation.sensors
    assert list(exp) == ["L8", "S2"]
    assert exp["S2"] == exp["L8"]
    assert (exp["L8"].first_year, exp["L8"].last_year, exp["L8"].first_doy, exp["L8"].last_doy) == (2018, 2026, 152, 273)


@pytest.mark.parametrize("bad", [(), ("L4",), ("L8", "MO")])
def test_expectation_sensors_must_be_a_nonempty_subset(bad):
    with pytest.raises(ValueError, match="expectation_sensors"):
        MonitoringControls(expectation_sensors=bad)


def test_mismatch_warning():
    w = sensor_warnings(("L8",), MONITORING, 2018, 2023)
    assert len(w) == 1
    assert w[0].startswith("The expectation uses Landsat 8 and monitoring uses Landsat 8, Landsat 9 and Sentinel-2.")
    assert sensor_warnings(MONITORING[:1], ("L8",), 2018, 2023) == []
    # Same sensors in any order: no warning.
    assert [x for x in sensor_warnings(("S2", "L8"), ("L8", "S2"), 2018, 2023) if "expectation uses" in x] == []


def test_availability_warnings():
    w = sensor_warnings(("L8", "L9"), ("L8", "L9"), 2018, 2023)
    assert w == ["Landsat 9 has no observations before 2022 (its first scenes are from Oct 31, 2021), which affects "
                 "expectation years 2018-2021; the sensor mix changes partway through the expectation."]
    assert sensor_warnings(("L9",), ("L9",), 2021, 2023)[0].endswith("which affects expectation year 2021.")
    assert sensor_warnings(("L9",), ("L9",), 2022, 2023) == []
    s2 = sensor_warnings(("S2",), ("S2",), 2016, 2019)
    assert any("Sentinel-2 has fewer observations before 2018" in x and "years 2016-2017." in x for x in s2)
    assert not any("observations before" in x for x in sensor_warnings(("S2",), ("S2",), 2018, 2019))


def test_memory_warning_follows_the_probe_limit():
    n = S2_EXPECTATION_MAX_YEARS
    first = 2023 - n + 1
    ok = sensor_warnings(("L8", "S2"), ("L8", "S2"), first, 2023)
    assert not any("memory limit" in x for x in ok)
    over = sensor_warnings(("L8", "S2"), ("L8", "S2"), first - 1, 2023)
    assert any(x.startswith(f"A {n + 1}-year expectation with Sentinel-2 is likely to exceed") for x in over)
    # Landsat only: no memory warning at any length.
    assert not any("memory limit" in x for x in sensor_warnings(("L8", "L9"), ("L8", "L9"), 2016, 2025))


def test_python_and_gee_sensor_configs_and_warnings_match():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    combos = [("L8",), ("L9",), ("S2",), ("L8", "S2"), ("L8", "L9"), ("L8", "L9", "S2"),
              ("L5",), ("L7",), ("L5", "L7"), ("L7", "L8"), ("L5", "L7", "L8")]
    monitoring = (("L8", "L9", "S2"), ("L8",), ("L8", "S2"), ("L7",), ("L7", "L8"), ("L9",))
    years = ((2018, 2023, 2026), (2016, 2023, 2026), (2022, 2023, 2026), (2021, 2021, 2026), (2016, 2025, 2026),
             (2010, 2014, 2015), (2013, 2014, 2015), (2010, 2011, 2015), (2012, 2014, 2016), (2018, 2019, 2023),
             (2010, 2023, 2024), (2015, 2021, 2022))
    cases = [(e, m, y0, y1, my, t) for e in combos for m in monitoring for y0, y1, my in years for t in (True, False)]
    script = ("const c = require('../config.js'), cases = %s; const box = (xs) => { const b = {}; "
              "c.SENSORS.forEach((s) => { b[s] = xs.includes(s); }); return b; }; "
              "console.log(JSON.stringify(cases.map(([e, m, y0, y1, my, t]) => "
              "{ const x = Object.assign({}, c.APP_DEFAULTS, {expectation_sensors: box(e), sensors: box(m), "
              "expectation_first: y0, expectation_last: y1, monitoring_year: my, timing: t}); "
              "const problem = c.availabilityProblem(x); if (problem) return [null, null, null, c.sensorWarnings(x), "
              "problem, c.timingYears(x)]; const cfg = c.buildConfig(x, {aoi_asset: 'x'}).evidence; "
              "return [Object.keys(cfg.expectation.sensors), Object.keys(cfg.target.sensors).filter((k) => "
              "cfg.target.sensors[k].enabled), Object.keys(cfg.target.sensors), c.sensorWarnings(x), problem, "
              "c.timingYears(x)]; })))"
              % json.dumps(cases))
    gee = json.loads(subprocess.check_output([node, "-e", script], cwd=GEE_TESTS))
    for (e, m, y0, y1, my, t), (keys, target, all_target, warnings, problem, timing) in zip(cases, gee):
        case = (e, m, y0, y1, my, t)
        controls = MonitoringControls(monitoring_year=my, baseline_first_year=y0, baseline_last_year=y1,
                                      expectation_sensors=e)
        config = build_config(controls, aoi_asset="x")
        with_monitoring_sensors(config, m)   # EarlyDetectionApp.build()'s monitoring boxes
        if keys is not None:   # buildConfig() refuses a blocked run
            assert list(config.evidence.expectation.sensors) == keys, case
            assert [k for k, v in config.evidence.target.sensors.items() if v.enabled] == target, case
            assert list(config.evidence.target.sensors) == all_target, case
        assert sensor_warnings(e, m, y0, y1, my, timing if t else None) == warnings, case
        assert availability_problem(e, m, y0, y1, my) == problem, case


def test_app_widgets_default_and_follow_into_every_run(app):
    assert {s: b.value for s, b in app.expectation_sensors.items()} == {"L5": False, "L7": False, "L8": True,
                                                                         "L9": False, "S2": False}
    assert {s: b.value for s, b in app.sensors.items()} == {"L7": False, "L8": True, "L9": True, "S2": True}
    assert list(app.build(app.controls(), aoi_asset="x").evidence.expectation.sensors) == ["L8"]
    assert "The expectation uses Landsat 8 and monitoring uses" in app.relationship.value
    app.expectation_sensors["S2"].value = True
    try:
        for c in (app.controls(), *(app.controls(y) for y in (2024, 2025, 2026))):
            assert list(app.build(c, aoi_asset="x").evidence.expectation.sensors) == ["L8", "S2"]
    finally:
        app.expectation_sensors["S2"].value = False


def test_app_blocks_a_period_without_sensors(app):
    app.area = object()   # an area is chosen, so only the settings decide
    for boxes, message in ((app.expectation_sensors, "Select at least one expectation sensor."),
                           (app.sensors, "Select at least one monitoring sensor.")):
        before = {s: b.value for s, b in boxes.items()}
        try:
            for b in boxes.values():
                b.value = False
            assert message in app.relationship.value
            assert app.run_btn.disabled
        finally:
            for s, b in boxes.items():
                b.value = before[s]
        assert not app.run_btn.disabled
    assert set(MONITORING_SENSORS) == set(SENSORS) - {"L5"}

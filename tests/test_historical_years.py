"""Historical years (docs/findings.md, 2026-11-02), no Earth Engine calls:
expectation years from 2010 and monitoring years from 2015 in the app's
widgets; Landsat 5/7 as sensors, with the data-availability table driving
warnings and blocking problems; Landsat 7 monitoring only when ticked, so the
default config is exactly what it was; Landsat reference imagery before
Sentinel-2. Python <-> GEE equality of all of it:
tests/test_expectation_sensors.py and gee/tests/controls_check.js."""

from unittest import mock

import pytest

from bulcd_early_detection import outputs
from bulcd_early_detection.config import (DEFAULT_MONITORING_SENSORS, EXPECTATION_YEARS, MONITORING_SENSORS,
                                          MONITORING_YEARS, SENSORS, MonitoringControls, availability_problem,
                                          build_config, has_data, sensor_warnings, with_monitoring_sensors)


@pytest.fixture()
def app(tmp_path):
    pytest.importorskip("ipyleaflet")
    from bulcd_early_detection.app import EarlyDetectionApp
    with mock.patch("ee.data.setDeadline"):
        a = EarlyDetectionApp(aoi_dir=tmp_path)
    a.area = object()   # an area is chosen, so only the settings decide
    return a


def test_year_limits():
    assert EXPECTATION_YEARS == (2010, 2025)
    assert MONITORING_YEARS == tuple(range(2015, 2027))


def test_sensors():
    assert SENSORS == ("L5", "L7", "L8", "L9", "S2")
    assert MONITORING_SENSORS == ("L7", "L8", "L9", "S2")   # Landsat 5 ended in 2011
    assert DEFAULT_MONITORING_SENSORS == ("L8", "L9", "S2")


@pytest.mark.parametrize("code, years_with, years_without", [
    ("L5", [2010, 2011], [2012, 2015]),
    ("L7", [2010, 2012, 2022, 2023], [2024, 2026]),
    ("L8", [2013, 2015], [2010, 2012]),
    ("L9", [2022], [2021, 2015]),
    ("S2", [2016, 2017, 2018], [2015]),
])
def test_has_data(code, years_with, years_without):
    assert all(has_data(code, y, y) for y in years_with)
    assert not any(has_data(code, y, y) for y in years_without)


def test_partial_coverage_has_data_and_warns():
    assert has_data("L5", 2010, 2014)
    w = sensor_warnings(("L5",), ("L8",), 2010, 2014, 2015)
    assert any(x.startswith("Landsat 5 has no observations after 2011") and x.endswith("expectation years 2012-2014.")
               for x in w)
    assert any("fewer observations in 2022-2023" in x and "expectation years 2022-2023" in x
               for x in sensor_warnings(("L7",), ("L7",), 2018, 2023, 2023))


def test_blocking_problems():
    assert availability_problem(("L5",), ("L8",), 2012, 2014, 2015).startswith(
        "No selected expectation sensor has observations in 2012-2014: Landsat 5 has no observations after 2011")
    assert availability_problem(("L8",), ("L9",), 2010, 2012, 2015).startswith(
        "No selected expectation sensor has observations in 2010-2012: Landsat 8 has no observations before 2013")
    assert availability_problem(("L8",), ("L7",), 2018, 2023, 2024).startswith(
        "No selected monitoring sensor has observations in 2024: Landsat 7 has no observations after 2023")
    assert availability_problem(("L8",), ("L9", "S2"), 2013, 2014, 2015).startswith(
        "No selected monitoring sensor has observations in 2015: Landsat 9 has no observations before 2022 "
        "(its first scenes are from Oct 31, 2021); Sentinel-2 has no observations before 2016")
    # One sensor with data is enough.
    assert availability_problem(("L5", "L8"), ("L7", "L9"), 2010, 2014, 2015) is None
    assert availability_problem(("L8",), ("L8", "L9", "S2"), 2018, 2023, 2026) is None


def test_mismatch_counts_only_sensors_with_data():
    # Landsat 9 and Sentinel-2 have nothing in 2015: both periods effectively use Landsat 8.
    w = sensor_warnings(("L8",), ("L8", "L9", "S2"), 2013, 2014, 2015)
    assert not any("expectation uses" in x for x in w)
    assert sum("which affects the monitoring year (2015)" in x for x in w) == 2
    # TM/ETM+ vs OLI: the Landsat text, with the measured result.
    w = sensor_warnings(("L7",), ("L8",), 2010, 2014, 2015)
    assert w[0].startswith("The expectation uses Landsat 7 and monitoring uses Landsat 8. Landsat 5 and 7 (TM/ETM+)")
    assert "median 0.013 or less" in w[0]
    # Sentinel-2 involved: the Sentinel-2 text, as before.
    w = sensor_warnings(("L7", "L8"), ("L8", "S2"), 2016, 2020, 2021)
    assert "Sentinel-2 in monitoring but not in the expectation" in w[0]


def test_landsat_7_note_and_empty_timing_seasons():
    assert any(x.startswith("Landsat 7 images since 2003 have striped gaps")
               for x in sensor_warnings(("L8",), ("L7", "L8"), 2013, 2014, 2015))
    assert not any("striped gaps" in x for x in sensor_warnings(("L8",), ("L8",), 2013, 2014, 2015))
    w = sensor_warnings(("L8",), ("L9",), 2016, 2019, 2023, [2021, 2022, 2023])
    assert "No selected monitoring sensor has observations in 2021, so the first-detected-season run for that " \
           "season has nothing to evaluate and shows no detection there." in w
    assert not any("first-detected-season run" in x for x in sensor_warnings(("L8",), ("L9",), 2016, 2019, 2023))


def test_default_config_unchanged_and_landsat_7_opt_in():
    base = build_config(MonitoringControls(), aoi_asset="x")
    assert list(base.evidence.target.sensors) == ["L8", "L9", "S2"]
    assert all(s.enabled for s in base.evidence.target.sensors.values())
    with_monitoring_sensors(base, ("L8", "L9", "S2"))
    assert list(base.evidence.target.sensors) == ["L8", "L9", "S2"]
    config = with_monitoring_sensors(build_config(MonitoringControls(monitoring_year=2015, baseline_first_year=2010,
                                                                     baseline_last_year=2014,
                                                                     expectation_sensors=("L5", "L7", "L8")),
                                                  aoi_asset="x"), ("L7", "L8"))
    target = config.evidence.target.sensors
    assert {k: v.enabled for k, v in target.items()} == {"L7": True, "L8": True, "L9": False, "S2": False}
    assert (target["L7"].first_year, target["L7"].last_year) == (2015, 2016)
    assert target["L7"] == target["L8"]
    exp = config.evidence.expectation.sensors
    assert list(exp) == ["L5", "L7", "L8"] and (exp["L5"].first_year, exp["L5"].last_year) == (2010, 2015)


def test_reference_imagery_source():
    assert outputs.reference_source([2024, 2025, 2026]) == "S2"
    assert outputs.reference_source([2017, 2018, 2019]) == "S2"
    assert outputs.reference_source([2016, 2017, 2018]) == "Landsat"   # one source for all three years
    assert outputs.reference_source([2013, 2014, 2015]) == "Landsat"


def test_app_widgets_reach_the_historical_years(app):
    assert (app.expectation.min, app.expectation.max) == EXPECTATION_YEARS
    assert list(app.monitoring_year.options) == list(MONITORING_YEARS)
    assert list(app.expectation_sensors) == list(SENSORS)
    assert list(app.sensors) == list(MONITORING_SENSORS)
    app.monitoring_year.value = 2015
    app.expectation.value = (2010, 2014)
    app.expectation_sensors["L7"].value = True
    app.sensors["L7"].value = True
    assert app.settings_ok and not app.run_btn.disabled
    config = app.build(app.controls(), aoi_asset="x")
    assert list(config.evidence.expectation.sensors) == ["L7", "L8"]
    assert [k for k, v in config.evidence.target.sensors.items() if v.enabled] == ["L7", "L8", "L9", "S2"]
    assert "striped gaps" in app.relationship.value
    assert "Landsat 8 has no observations before 2013" in app.relationship.value


def test_app_blocks_a_period_without_data(app):
    app.monitoring_year.value = 2015
    app.expectation.value = (2012, 2014)
    app.expectation_sensors["L8"].value = False
    app.expectation_sensors["L5"].value = True
    assert not app.settings_ok and app.run_btn.disabled
    assert "No selected expectation sensor has observations in 2012-2014" in app.relationship.value
    app.expectation_sensors["L7"].value = True
    assert app.settings_ok and not app.run_btn.disabled

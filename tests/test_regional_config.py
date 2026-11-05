"""Regional product spec, run configuration and tiling (docs/regional_plan.md,
step 3). No Earth Engine calls: the grid values checked here against Earth
Engine are recorded in docs/findings.md, 2026-10-22."""

import dataclasses
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

pytest.importorskip("pyproj")
pytest.importorskip("yaml")

from bulcd_early_detection import outputs
from bulcd_early_detection.config import DEFAULT_MONITORING_SENSORS, LEGACY_DEFAULTS
from bulcd_early_detection.regional import spec
from bulcd_early_detection.regional.run_config import AdvancedSettings, Region, RegionalRun, app_default_controls
from bulcd_early_detection.regional.tiling import Grid, lonlat_ring, tiles_around, to_grid_xy

PILOT = Path(__file__).parents[1] / "regional_runs" / "pilot_coast_range_2026.yaml"
TESTSITE = (-123.57, 44.84)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    pytest.importorskip("ipyleaflet")
    from bulcd_early_detection.app import EarlyDetectionApp
    with mock.patch("ee.data.setDeadline"):
        return EarlyDetectionApp(aoi_dir=tmp_path_factory.mktemp("aois"))


# ---------------------------------------------------------------- spec

def test_condition_codes_are_the_apps():
    assert (spec.DECREASE, spec.UNCHANGED, spec.INCREASE, spec.NOT_ANALYZED) == \
           (outputs.DECREASE, outputs.UNCHANGED, outputs.INCREASE, outputs.NOT_ANALYZED)


def test_bands_and_nodata():
    assert spec.BAND_NAMES == ("condition", "p_decrease", "p_unchanged", "p_increase", "first_detection_doy",
                               "last_detection_doy", "episode_count", "n_obs_monitoring", "n_obs_expectation")
    # nodata is never a valid value: condition <= 3, probabilities <= 10,000, day of year <= 366,
    # episodes and bins per season far below 255 (a year has 92 4-day bins).
    largest = {"condition": spec.NOT_ANALYZED, "p_decrease": spec.PROBABILITY_SCALE, "first_detection_doy": 366,
               "episode_count": 92, "n_obs_monitoring": 92, "n_obs_expectation": 92 * 40}
    for name, value in largest.items():
        assert value < spec.BAND[name].nodata
    assert spec.spec_dict()["bands"][1] == {"name": "p_decrease", "dtype": "uint16", "scale": 10_000,
                                            "description": spec.BAND["p_decrease"].description, "nodata": 65535}


def test_stack_is_the_season_tile_plus_detection_year():
    assert spec.STACK_BAND_NAMES == spec.BAND_NAMES + ("detection_year",)
    assert spec.STACK_PROPERTIES[:len(spec.PROPERTIES)] == spec.PROPERTIES
    assert spec.spec_dict()["stack"]["bands"][-1]["nodata"] == 65535


def test_probability_scaling_error_is_at_most_half_a_step():
    for p in (0.0, 1.0, 0.65, 0.043, 0.914, 0.123456789, 0.99995, 0.00004):
        assert abs(spec.unscale_probability(spec.scale_probability(p)) - p) <= 0.5 / spec.PROBABILITY_SCALE + 1e-15
    assert spec.scale_probability(1.0) == 10_000
    with pytest.raises(ValueError):
        spec.scale_probability(1.01)


# ---------------------------------------------------------------- grid and tiles

def test_grid_matches_earth_engine_epsg_5070():
    # Earth Engine's EPSG:5070 coordinates of the testsite point (docs/findings.md, 2026-10-22).
    x, y = to_grid_xy(Grid(), *TESTSITE)
    assert (x, y) == pytest.approx((-2145719.002, 2741360.734), abs=0.001)
    g = Grid()
    assert g.transform == [30, 0, -2493045.0, 0, -30, 3310005.0]
    assert g.tile_m == 9990


def test_pilot_tiles_meet_at_the_testsite():
    g = Grid()
    bounds = tiles_around(g, *TESTSITE, n=2)
    assert bounds == (-2153385.0, 2730585.0, -2133405.0, 2750565.0)
    tiles = g.tiles(bounds)
    assert [t.id for t in tiles] == ["r0056c0034", "r0056c0035", "r0057c0034", "r0057c0035"]
    # The seams cross within 2.5 km of the site point.
    x, y = to_grid_xy(g, *TESTSITE)
    assert abs(tiles[0].bounds[2] - x) < 2500 and abs(tiles[0].bounds[1] - y) < 2500
    with pytest.raises(ValueError):
        tiles_around(g, *TESTSITE, n=3)


def test_tiles_partition_a_region_on_the_pixel_grid():
    g = Grid()
    region = g.snap((-2150000.3, 2735000.7, -2131000.2, 2752000.1))
    tiles = g.tiles(region)
    parts = [t.clip(region) for t in tiles]
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])
    assert sum(area(p) for p in parts) == area(region)          # no gaps, no overlaps
    for t in tiles:
        for v, o in zip(t.bounds, (g.origin[0], g.origin[1]) * 2):
            assert (v - o) % g.scale == 0                          # tile edges on pixel edges
    for v, o in zip(region, (g.origin[0], g.origin[1]) * 2):
        assert (v - o) % g.scale == 0
    # A region ending exactly on a tile edge doesn't reach into the next tile.
    assert len(g.tiles(g.tile(56, 34).bounds)) == 1
    assert g.tile_index(*g.tile(56, 34).bounds[:1], g.tile(56, 34).bounds[3]) == (56, 34)


def test_lonlat_ring_covers_the_tile():
    g = Grid()
    tile = g.tile(56, 34)
    ring = lonlat_ring(g, tile.bounds)
    assert ring[0] == ring[-1] and len(ring) == 41
    xy = [to_grid_xy(g, lon, lat) for lon, lat in ring[:-1]]
    b = tile.bounds
    # Every ring point is outside the tile by about the one-pixel buffer.
    for x, y in xy:
        outside = max(b[0] - x, x - b[2], b[1] - y, y - b[3])
        assert outside == pytest.approx(30, abs=0.01)


# ---------------------------------------------------------------- run configuration

def test_defaults_are_the_apps():
    c = app_default_controls()
    assert (c.monitoring_year, c.season_start, c.season_end, c.baseline_first_year, c.baseline_last_year) == \
           (2026, "06-01", "09-30", 2018, 2023)
    assert c.thresholds == {"decrease": 0.65, "increase": 0.75}
    assert c.expectation_sensors == ("L8",)
    a = AdvancedSettings()
    # The apps' default boxes: Landsat 7 (a historical-years opt-in) is never on by default.
    assert a.monitoring_sensors == DEFAULT_MONITORING_SENSORS == ("L8", "L9", "S2")
    assert (a.dampening, a.posterior_leveler, a.mask_forest, a.mask_water) == \
           (LEGACY_DEFAULTS["dampening"], LEGACY_DEFAULTS["posterior_leveler"], False, True)
    assert a.timing_rule == "confirmed"


def test_pilot_run_file():
    run = RegionalRun.load(PILOT)
    assert run.run_id == "r6-pilot-coast-range-2026"
    assert run.controls == app_default_controls()
    assert run.controls.expectation_sensors == ("L8",)
    assert run.advanced == AdvancedSettings(monitoring_sensors=("L8", "L9"))
    assert run.grid == Grid()
    assert [t.id for t in run.tiles] == ["r0056c0034", "r0056c0035", "r0057c0034", "r0057c0035"]
    assert len(run.warnings()) == 1 and run.warnings()[0].startswith(
        "The expectation uses Landsat 8 and monitoring uses Landsat 8 and Landsat 9.")
    assert RegionalRun.from_yaml(run.to_yaml()) == run


def test_run_config_is_the_interactive_apps_config(app):
    """A run's BULCDConfig is the Python app's build() with the same settings."""
    run = RegionalRun.load(PILOT)
    before = {s: b.value for s, b in app.sensors.items()}
    try:
        app.sensors["S2"].value = False
        assert run.bulcd_config(aoi_asset="x") == app.build(app.controls(), aoi_asset="x")
    finally:
        for s, b in app.sensors.items():
            b.value = before[s]
    # Default settings: the app's default config.
    default = RegionalRun("x", Region("x", run.region.bounds))
    assert default.bulcd_config(aoi_asset="x") == app.build(app.controls(), aoi_asset="x")
    target = run.bulcd_config(aoi_asset="x").evidence.target.sensors
    assert {c: s.enabled for c, s in target.items()} == {"L8": True, "L9": True, "S2": False}


@pytest.mark.parametrize("change, message", [
    ({"run_id": "Pilot 1"}, "run_id"),
    ({"region": {"name": "x", "bounds": [-2153385.0, 2730585.0, -2133405.0, 2750566.0]}}, "not on the 30 m grid"),
    ({"product_version": 2}, "product version"),
    ({"extra": 1}, "unknown keys"),
    ({"advanced": {"monitoring_sensors": []}}, "monitoring_sensors"),
    ({"advanced": {"monitoring_sensors": ["L5", "L8"]}}, "monitoring_sensors"),   # Landsat 5 can't monitor
    ({"advanced": {"monitoring_sensors": ["L8", "LX"]}}, "monitoring_sensors"),
    ({"advanced": {"monitoring_sensors": ["L9"]}, "controls": {**RegionalRun.load(PILOT).to_dict()["controls"],
      "monitoring_year": 2021, "baseline_last_year": 2020}}, "No selected monitoring sensor"),
    ({"advanced": {"timing_rule": "late"}}, "timing_rule"),
    ({"controls": {"baseline_last_year": 2026}}, "baseline must end"),
])
def test_invalid_run_configs(change, message):
    d = RegionalRun.load(PILOT).to_dict() | change
    with pytest.raises((ValueError, TypeError), match=message):
        RegionalRun.from_dict(d)


def test_landsat_7_only_when_listed():
    """A run file without monitoring_sensors gets the apps' defaults (no Landsat 7);
    listing L7 adds it as in the app (config.with_monitoring_sensors())."""
    d = RegionalRun.load(PILOT).to_dict()
    del d["advanced"]["monitoring_sensors"]
    target = RegionalRun.from_dict(d).bulcd_config(aoi_asset="x").evidence.target.sensors
    assert {c: s.enabled for c, s in target.items()} == {"L8": True, "L9": True, "S2": True}
    d["advanced"]["monitoring_sensors"] = ["L7", "L8"]
    target = RegionalRun.from_dict(d).bulcd_config(aoi_asset="x").evidence.target.sensors
    assert {c: s.enabled for c, s in target.items()} == {"L7": True, "L8": True, "L9": False, "S2": False}
    assert dataclasses.replace(target["L7"]) == target["L8"]   # same years, window and cloud filter


def test_regional_config_needs_no_earth_engine():
    code = ("import sys; from bulcd_early_detection.regional import spec, run_config, tiling; "
            "run_config.RegionalRun.load(%r).tiles; print('ee' in sys.modules)" % str(PILOT))
    assert subprocess.check_output([sys.executable, "-c", code], text=True).strip() == "False"


def test_blocks_are_aligned_and_hold_whole_tiles():
    grid = Grid()
    tiles = [grid.tile(56, 34), grid.tile(57, 35), grid.tile(57, 36)]
    blocks = grid.blocks(tiles, 2)
    assert [b.id for b in blocks] == ["r0056c0034_2x2", "r0056c0036_2x2"]
    assert [t.id for t in blocks[0].tiles] == ["r0056c0034", "r0056c0035", "r0057c0034", "r0057c0035"]
    b = blocks[0].bounds
    assert (b[2] - b[0], b[3] - b[1]) == (2 * grid.tile_m, 2 * grid.tile_m)


def test_ecoregion_run_round_trips_and_old_runs_are_unchanged():
    pilot = RegionalRun.load(PILOT)
    d = pilot.to_dict()
    assert "block_tiles" not in d and "forest_mask_asset" not in d["advanced"]
    assert set(d["region"]) == {"name", "bounds"}
    run = dataclasses.replace(
        pilot, run_id="eco", block_tiles=2,
        region=Region("eco", pilot.region.bounds, ecoregion=1, tiles=["r0057c0035", "r0056c0034"]),
        advanced=dataclasses.replace(pilot.advanced, mask_forest=True, forest_mask_asset="projects/x/assets/f"))
    again = RegionalRun.from_yaml(run.to_yaml())
    assert again.to_dict() == run.to_dict()
    assert [t.id for t in again.tiles] == ["r0056c0034", "r0057c0035"]
    assert [u.id for u in again.units] == ["r0056c0034_2x2"]
    config = again.bulcd_config(aoi_coordinates=[[0, 0], [1, 0], [1, 1], [0, 0]])
    assert config.study_area.mask_non_forest and config.study_area.forest_mask_asset == "projects/x/assets/f"

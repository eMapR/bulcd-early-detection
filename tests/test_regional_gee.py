"""The GEE regional backend's tile images, built but not computed (needs Earth
Engine credentials to build the graphs; skipped without them): one BULC-D run
per tile, the spec's bands and properties, exact tile pixels."""

import datetime
import json
from pathlib import Path

import pytest

pytest.importorskip("pyproj")
pytest.importorskip("yaml")
ee = pytest.importorskip("ee")

from bulcd_early_detection import outputs
from bulcd_early_detection.regional import spec
from bulcd_early_detection.regional.run_config import RegionalRun

PILOT = Path(__file__).parents[1] / "regional_runs" / "pilot_coast_range_2026.yaml"


@pytest.fixture(scope="module")
def gee():
    try:
        ee.Initialize(project="bulcd-python-rebuild")
    except Exception as e:  # no credentials on this machine
        pytest.skip(f"Earth Engine not available: {e}")
    from bulcd_early_detection.regional.backends import gee as module
    return module


@pytest.fixture(scope="module")
def run():
    return RegionalRun.load(PILOT)


def _calls(image, name):
    return ee.serializer.toJSON(image).count(f'"{name}"')


def test_one_bulcd_run_per_tile(gee, run):
    """One harmonic fit and one BULC pass (+ the episode pass) in a tile's whole graph."""
    image = gee.product_image(run, gee.tile_config(run, run.tiles[0]))
    assert _calls(image, "Reducer.linearRegression") == 1
    assert _calls(image, "Collection.iterate") == 2


def test_result_variants_build_the_same_graph(gee, run):
    """The *_from_result variants are what detection_timing_image() and
    detection_episode_image() now delegate to."""
    from bulcd.engine import run_bulcd
    config = gee.tile_config(run, run.tiles[0])
    result = run_bulcd(config)
    for confirmed in (True, False):
        assert ee.serializer.toJSON(outputs.detection_episode_image(config, 0.65, 0.75, confirmed)) == \
               ee.serializer.toJSON(outputs.detection_episode_from_result(result, config, 0.65, 0.75, confirmed))
    assert ee.serializer.toJSON(outputs.detection_timing_image(config, 0.65, 0.75)) == \
           ee.serializer.toJSON(outputs.detection_timing_from_result(result, config, 0.65, 0.75))


def test_tile_config_is_the_runs(gee, run):
    tile = run.tiles[0]
    config = gee.tile_config(run, tile)
    ring = config.study_area.aoi_coordinates
    assert config == run.bulcd_config(aoi_coordinates=ring)
    assert ring[0] == ring[-1]


def test_tile_pixels_are_exact(gee, run):
    for tile in run.tiles:
        transform, dimensions = gee.tile_transform(run, tile)
        assert dimensions == "333x333"
        assert transform == [30, 0, tile.bounds[0], 0, -30, tile.bounds[3]]


def test_properties_follow_the_spec(gee, run):
    tile = run.tiles[0]
    config = gee.tile_config(run, tile)
    now = datetime.datetime(2026, 10, 22, 12, 0, tzinfo=datetime.timezone.utc)
    props = gee.tile_properties(run, tile, config, now=now)
    assert set(props) == set(spec.PROPERTIES)
    assert (props["tile_id"], props["run_id"], props["timing_rule"], props["bin_days"]) == \
           ("r0056c0034", "r6-pilot-coast-range-2026", "confirmed", 4)
    assert props["as_of_date"] == "2026-09-30"   # the season ended before the export
    assert props["as_of_date"] == gee.tile_properties(
        run, tile, config, now=datetime.datetime(2026, 11, 1, tzinfo=datetime.timezone.utc))["as_of_date"]
    early = gee.tile_properties(run, tile, config, now=datetime.datetime(2026, 7, 4, tzinfo=datetime.timezone.utc))
    assert early["as_of_date"] == "2026-07-04"
    assert RegionalRun.from_dict(json.loads(props["run_json"])) == run
    assert json.loads(props["grid_json"]) == {"crs": "EPSG:5070", "transform": gee.tile_transform(run, tile)[0],
                                              "dimensions": "333x333"}
    prov = json.loads(props["provenance_json"])
    assert set(prov) == {"bulcd_early_detection", "bulcd", "earthengine_api"}


def test_band_names(gee, run):
    image = gee.product_image(run, gee.tile_config(run, run.tiles[0]))
    assert image.bandNames().getInfo() == list(spec.BAND_NAMES)

"""Local comparison classification and drawn-AOI GeoJSON round trip (no Earth Engine calls)."""

import numpy as np
import pytest

from bulcd_early_detection.compare import classify
from bulcd_early_detection.drawing import _ring, load_polygon, save_polygon
from bulcd_early_detection.outputs import DECREASE, INCREASE, NOT_ANALYZED, UNCHANGED


def _run(**overrides):
    # 1 x 6 pixels: decrease, unchanged, increase, non-forest land, water, outside the area.
    run = {
        "decrease": np.array([[0.95, 0.10, 0.02, 0.95, 0.95, 0.95]]),
        "unchanged": np.array([[0.04, 0.85, 0.03, 0.04, 0.04, 0.04]]),
        "increase": np.array([[0.01, 0.05, 0.95, 0.01, 0.01, 0.01]]),
        "land": np.array([[1, 1, 1, 1, 0, 1]], dtype=float),
        "forest": np.array([[1, 1, 1, 0, 0, 1]], dtype=float),
        "inside": np.array([[1, 1, 1, 1, 1, 0]], dtype=float),
    }
    run.update(overrides)
    return run


def test_classify_matches_outcome_rule():
    classes = classify(_run(), threshold=0.5, mask_water=True, mask_non_forest=True)[0]
    assert list(classes[:4]) == [DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED]
    assert np.isnan(classes[4]) and np.isnan(classes[5])  # water, outside


def test_forest_mask_off_analyzes_non_forest_land():
    classes = classify(_run(), threshold=0.5, mask_water=True, mask_non_forest=False)[0]
    assert classes[3] == DECREASE


def test_threshold_applied_to_same_probabilities():
    classes = classify(_run(), threshold=0.96, mask_water=True, mask_non_forest=True)[0]
    assert classes[0] == UNCHANGED and classes[2] == UNCHANGED


def test_no_data_pixels_not_analyzed():
    run = _run(decrease=np.array([[-1.0, 0.1, 0.02, 0.95, 0.95, 0.95]]))
    assert classify(run, 0.5, True, True)[0][0] == NOT_ANALYZED


def test_geojson_round_trip(tmp_path):
    ring = [[-90.58, 46.914], [-90.58, 46.928], [-90.555, 46.928], [-90.58, 46.914]]
    save_polygon("shore", ring, tmp_path)
    assert load_polygon("shore", tmp_path) == ring


def test_missing_saved_area_has_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Draw a polygon"):
        load_polygon("nope", tmp_path)


def test_ring_rejects_non_polygon():
    with pytest.raises(ValueError):
        _ring({"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}})

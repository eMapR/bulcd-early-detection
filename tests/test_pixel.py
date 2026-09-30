"""Pixel-history helpers that don't need Earth Engine."""

import datetime
from pathlib import Path

from bulcd_early_detection.config import PRODUCTION_TRANSITION_MATRIX
from bulcd_early_detection.pixel import first_crossing, history_from_replay_csv, supported_class

CUTS = [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2]


def test_supported_class_follows_transition_matrix_rows():
    assert supported_class(-10, CUTS, PRODUCTION_TRANSITION_MATRIX) == "decrease"
    assert supported_class(0.1, CUTS, PRODUCTION_TRANSITION_MATRIX) == "unchanged"
    assert supported_class(10, CUTS, PRODUCTION_TRANSITION_MATRIX) == "increase"
    assert supported_class(None, CUTS, PRODUCTION_TRANSITION_MATRIX) is None


def test_first_crossing():
    d = datetime.date
    rows = [{"date": d(2026, 6, 5), "decrease": 0.2}, {"date": d(2026, 7, 1), "decrease": 0.51},
            {"date": d(2026, 8, 1), "decrease": 0.9}]
    assert first_crossing(rows, 0.5) == d(2026, 7, 1)
    assert first_crossing(rows, 0.95) is None


def test_history_from_replay_csv_matches_known_fire_crossing():
    csv = Path(__file__).parents[1] / "experiments" / "output" / "fire_2026_production_matrix.csv"
    rows = history_from_replay_csv(csv, CUTS, PRODUCTION_TRANSITION_MATRIX)
    assert rows[0]["date"] == datetime.date(2026, 6, 5)
    assert first_crossing(rows, 0.5) is not None and first_crossing(rows, 0.5) > datetime.date(2026, 7, 21)
    assert any(r["supports"] == "decrease" for r in rows)

"""MonitoringControls -> BULCDConfig mapping (no Earth Engine calls)."""

import pytest

from bulcd_early_detection.config import (
    PRODUCTION_TRANSITION_MATRIX,
    MonitoringControls,
    build_config,
)

RING = [[-90.6, 46.9], [-90.6, 47.0], [-90.5, 47.0], [-90.5, 46.9]]


def test_defaults_match_validated_2026_baseline():
    config = build_config(MonitoringControls(), aoi_coordinates=RING)
    expectation = config.evidence.expectation.sensors
    target = config.evidence.target.sensors

    assert list(expectation) == ["L8"]
    # bulcd's last_year is exclusive: 2018-2025 inclusive baseline.
    assert (expectation["L8"].first_year, expectation["L8"].last_year) == (2018, 2026)
    assert sorted(target) == ["L8", "L9", "S2"]
    assert all((s.first_year, s.last_year) == (2026, 2027) for s in target.values())
    # Jun 1 - Sep 30 in a non-leap year.
    assert all((s.first_doy, s.last_doy) == (152, 273) for s in [*expectation.values(), *target.values()])

    adv = config.bulc_advanced_params
    assert adv.custom_transition_matrix == PRODUCTION_TRANSITION_MATRIX
    assert (adv.recency_factor, adv.dampening_factor, adv.posterior_leveler) == (1.0, 0.5, 1.0)
    assert config.sensitivity.z_score_numerator_factor == 1.0


def test_sensitivity_maps_to_zscore_numerator_factor():
    config = build_config(MonitoringControls(sensitivity=1.5), aoi_coordinates=RING)
    assert config.sensitivity.z_score_numerator_factor == 1.5


def test_asset_aoi():
    config = build_config(MonitoringControls(), aoi_asset="projects/p/assets/fc")
    assert config.study_area.aoi_asset == "projects/p/assets/fc"
    assert config.study_area.aoi_coordinates is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"decision_threshold": 0.4},
        {"decision_threshold": 1.0},
        {"baseline_last_year": 2026},
        {"sensitivity": 0},
        {"season_start": "10-01"},
    ],
)
def test_invalid_controls_rejected(kwargs):
    with pytest.raises(ValueError):
        MonitoringControls(**kwargs)


def test_exactly_one_aoi():
    with pytest.raises(ValueError):
        build_config(MonitoringControls())
    with pytest.raises(ValueError):
        build_config(MonitoringControls(), aoi_coordinates=RING, aoi_asset="projects/p/assets/fc")

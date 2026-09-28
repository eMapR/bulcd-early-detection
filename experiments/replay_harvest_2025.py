"""Chronological replay: 2025 clearcut/timber harvest.

Milestone 1 real-disturbance test (see docs/PROJECT_STATE.md). Site was
identified from Sentinel-2 imagery as a progressive harvest: activity
observed starting 2025-07-25, completed by 2025-08-19 (~25 days).
`disturbance_window` below spans exactly those two OBSERVED activity
dates, inclusive - unlike the fire replay, these are direct observations
of the harvest itself, not inferred bounds around an unknown event.

Uses BULC-D_rebuild's public API only (organize_inputs, run_bulcd) via
_replay_common.py. No BULC-D_rebuild code is modified. Shared BULC-D
parameters (dampening/recency/posterior_leveler, modality, sensitivity,
bin_cuts, the Willis NBR12 transition matrix) are all left at the same
defaults used in the validated B&B Complex Fire test - only the
evidence-period dates/sensors/AOI differ, so this experiment isolates
the effect of accumulating observations, not new parameter choices.

Usage:
    conda run -n bulcd python experiments/replay_harvest_2025.py
"""

from __future__ import annotations

import datetime
from pathlib import Path

import ee

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.config.schema import (
    BULCAdvancedParams,
    BULCDConfig,
    EvidenceConfig,
    EvidencePeriodConfig,
    ModalityConfig,
    ReductionConfig,
    SensitivityConfig,
    SensorEvidenceConfig,
    StudyAreaConfig,
)

from _replay_common import print_summary, run_replay

LON, LAT = -121.63691, 45.11982
_HALF_WIDTH_DEGREES = 0.01
SMALL_AOI = [
    [LON - _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
    [LON - _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
]
POINT = ee.Geometry.Point([LON, LAT])

# Observed activity bounds (not inferred) - see module docstring.
WINDOW_START = datetime.date(2025, 7, 25)
WINDOW_END = datetime.date(2025, 8, 19)

# Willis (2022)'s worked NBR12 example - same matrix as the validated
# B&B Complex Fire test, not a new/unvalidated choice.
NBR12_TRANSITION_MATRIX = [
    [0.16, 0.11, 0.02],
    [0.14, 0.07, 0.02],
    [0.07, 0.12, 0.02],
    [0.03, 0.16, 0.02],
    [0.015, 0.2, 0.01],
    [0.015, 0.195, 0.025],
    [0.02, 0.1255, 0.07],
    [0.02, 0.07, 0.11],
    [0.02, 0.05, 0.12],
    [0.02, 0.02, 0.08],
]

# Growing-season DOY window (Jun 1 - Sep 30), avoids winter snow z-score
# contamination - same as the validated B&B fire test.
_FIRST_DOY, _LAST_DOY = 152, 273
# Permissive scene-level prefilter: per-pixel QA/Cloud-Score+ masking is
# what actually screens data at our point, so a strict scene-level
# CLOUD_COVER/CLOUDY_PIXEL_PERCENTAGE filter would risk discarding whole
# scenes that are clear locally but cloudy elsewhere in the tile.
_CLOUD_COVER_THRESHOLD = 70

def build_config(
    recency_factor: float = 1.0,
    transition_matrix: list[list[float]] = NBR12_TRANSITION_MATRIX,
    aoi_coordinates: list[list[float]] = SMALL_AOI,
) -> BULCDConfig:
    """Same config approved for this site, with `recency_factor`,
    `transition_matrix`, and `aoi_coordinates` parametrized (for the
    recency_factor sweep, the production-matrix baseline, and the
    spatial-validation buffer - experiments/replay_recency_sweep.py,
    replay_production_matrix.py, spatial_validation.py). Everything else -
    expectation/target periods/sensors, bin_cuts, modality, sensitivity,
    dampening_factor/posterior_leveler - is unchanged."""
    return BULCDConfig(
        study_area=StudyAreaConfig(aoi_coordinates=aoi_coordinates),
        evidence=EvidenceConfig(
            # last_year is EXCLUSIVE (bulcd/inputs.py) - 2025 here means
            # "up through 2024", cleanly excluding the harvest year.
            #
            # L8 only (not the originally-approved L8+S2): the 2-sensor,
            # 7-year (217 binned Events) expectation baseline triggered
            # Earth Engine's "User memory limit exceeded" inside
            # organize_inputs()'s harmonic-fit code for both sites - isolated
            # to the fit itself (confirmed independent of tileScale, so a
            # graph-complexity limit, not spatial/raster memory). Not a
            # BULC-D_rebuild bug we're working around by changing the
            # algorithm - narrowing OUR config's expectation period,
            # approved by the user 2026-09-18 after this was found. See
            # docs/PROJECT_STATE.md and experiments/*_findings.md.
            expectation=EvidencePeriodConfig(
                sensors={
                    "L8": SensorEvidenceConfig(
                        enabled=True, first_year=2018, last_year=2025,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                }
            ),
            # last_year=2026 (exclusive) -> 2025 only.
            target=EvidencePeriodConfig(
                sensors={
                    "L8": SensorEvidenceConfig(
                        enabled=True, first_year=2025, last_year=2026,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                    "L9": SensorEvidenceConfig(
                        enabled=True, first_year=2025, last_year=2026,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                    "S2": SensorEvidenceConfig(
                        enabled=True, first_year=2025, last_year=2026,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                }
            ),
        ),
        reduction=ReductionConfig(band="nbr"),
        modality=ModalityConfig(constant=True, unimodal=True),
        sensitivity=SensitivityConfig(),
        bulc_advanced_params=BULCAdvancedParams(
            custom_transition_matrix=transition_matrix, recency_factor=recency_factor
        ),
    )


DECREASE_THRESHOLD = 0.5
OUTPUT_CSV = Path(__file__).parent / "output" / "harvest_2025_replay.csv"


def main() -> None:
    rows, year_at_point = run_replay(
        config=build_config(1.0),
        point=POINT,
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        decrease_threshold=DECREASE_THRESHOLD,
        output_csv=OUTPUT_CSV,
    )
    print_summary(rows, OUTPUT_CSV, year_at_point)


if __name__ == "__main__":
    main()

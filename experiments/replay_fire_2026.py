"""Chronological replay: 2026 fire, exact date unknown.

Milestone 1 real-disturbance test (see docs/PROJECT_STATE.md). Only two
facts are known from imagery: the site was pre-fire on 2026-07-17 and
post-fire by 2026-07-22. The fire happened somewhere in the OPEN
interval between those two confirmed-state dates - we never assign an
exact ignition date. `disturbance_window` below is constructed as that
open interval, shifted one day in from each known-state date
(2026-07-18 through 2026-07-21) so `_replay_common.phase_for()`'s
inclusive-bounds convention doesn't misclassify the two confirmed dates
themselves as uncertain.

Uses BULC-D_rebuild's public API only (organize_inputs, run_bulcd) via
_replay_common.py. No BULC-D_rebuild code is modified. Shared BULC-D
parameters are identical to the harvest replay and the validated B&B
Complex Fire test - only evidence-period dates/sensors/AOI differ.

Usage:
    conda run -n bulcd python experiments/replay_fire_2026.py
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

LON, LAT = -118.26335, 48.10561
_HALF_WIDTH_DEGREES = 0.01
SMALL_AOI = [
    [LON - _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
    [LON - _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
]
POINT = ee.Geometry.Point([LON, LAT])

# Confirmed states, not inferred - see module docstring.
KNOWN_PRE_FIRE_DATE = datetime.date(2026, 7, 17)
KNOWN_POST_FIRE_DATE = datetime.date(2026, 7, 22)
WINDOW_START = KNOWN_PRE_FIRE_DATE + datetime.timedelta(days=1)  # 2026-07-18
WINDOW_END = KNOWN_POST_FIRE_DATE - datetime.timedelta(days=1)  # 2026-07-21

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

_FIRST_DOY, _LAST_DOY = 152, 273
_CLOUD_COVER_THRESHOLD = 70

def build_config(
    recency_factor: float = 1.0,
    transition_matrix: list[list[float]] = NBR12_TRANSITION_MATRIX,
    aoi_coordinates: list[list[float]] = SMALL_AOI,
) -> BULCDConfig:
    """Same config approved for this site, with `recency_factor`,
    `transition_matrix`, and `aoi_coordinates` parametrized (for the
    recency_factor sweep, the production-matrix baseline, and the
    spatial-validation buffer). Everything else is unchanged."""
    return BULCDConfig(
        study_area=StudyAreaConfig(aoi_coordinates=aoi_coordinates),
        evidence=EvidenceConfig(
            # last_year is EXCLUSIVE - 2026 here means "up through 2025".
            #
            # L8 only (not the originally-approved L8+S2): see the matching
            # comment in replay_harvest_2025.py - the 2-sensor, multi-year
            # expectation baseline triggered Earth Engine's "User memory
            # limit exceeded" inside organize_inputs()'s harmonic-fit code.
            # Narrowing approved by the user 2026-09-18 after that was found.
            expectation=EvidencePeriodConfig(
                sensors={
                    "L8": SensorEvidenceConfig(
                        enabled=True, first_year=2018, last_year=2026,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                }
            ),
            # last_year=2027 (exclusive) -> 2026 only. DOY range extends to
            # Sep 30 even though "today" is 2026-09-18 - trailing bins with
            # no data yet are harmless masked placeholders (bulcd/inputs.py's
            # _bin_evidence_by_day_step is explicitly designed for this).
            target=EvidencePeriodConfig(
                sensors={
                    "L8": SensorEvidenceConfig(
                        enabled=True, first_year=2026, last_year=2027,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                    "L9": SensorEvidenceConfig(
                        enabled=True, first_year=2026, last_year=2027,
                        first_doy=_FIRST_DOY, last_doy=_LAST_DOY,
                        cloud_cover_threshold=_CLOUD_COVER_THRESHOLD,
                    ),
                    "S2": SensorEvidenceConfig(
                        enabled=True, first_year=2026, last_year=2027,
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
OUTPUT_CSV = Path(__file__).parent / "output" / "fire_2026_replay.csv"


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

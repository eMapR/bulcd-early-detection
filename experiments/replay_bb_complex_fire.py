"""Chronological replay experiment (Milestone 1, see docs/PROJECT_STATE.md):
how does BULC-D's Bayesian output evolve as target-period observations
arrive one at a time, in order?

Plumbing/probability-trajectory test, NOT a definitive detection-latency
result: this config's target period (2004-2005) starts AFTER the known
2003 ignition, so it doesn't span the actual pre/post-fire transition -
see the "Caveat" note this script's own docstring below and
docs/PROJECT_STATE.md's Milestone 1 section.

Reuses ../BULC-D_rebuild/scripts/debug_bb_complex_fire.py's config
unmodified - the repo's best-validated real-disturbance reference point
(2003 B&B Complex Fire, central Oregon Cascades) - via BULC-D_rebuild's
public API only (bulcd.inputs.organize_inputs, bulcd.engine.run_bulcd).
No BULC-D_rebuild code is modified or duplicated.

Key point this exploits: bulc.run_bulc()'s BulcResult.probability_stack
already holds one posterior-probability image per target-period Event,
in chronological order - so a SINGLE engine.run_bulcd() call gives the
full progressive-observation trajectory; no need to rerun BULC-D at
different cutoff dates.

Usage:
    conda run -n bulcd python experiments/replay_bb_complex_fire.py
"""

from __future__ import annotations

import csv
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
from bulcd.engine import run_bulcd
from bulcd.inputs import organize_inputs
from bulcd.interpret import first_change_year

# Unmodified from debug_bb_complex_fire.py.
LON, LAT = -121.90249210117729, 44.53142096854933
_HALF_WIDTH_DEGREES = 0.01
SMALL_AOI = [
    [LON - _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
    [LON - _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT + _HALF_WIDTH_DEGREES],
    [LON + _HALF_WIDTH_DEGREES, LAT - _HALF_WIDTH_DEGREES],
]
POINT = ee.Geometry.Point([LON, LAT])

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

CONFIG = BULCDConfig(
    study_area=StudyAreaConfig(aoi_coordinates=SMALL_AOI),
    evidence=EvidenceConfig(
        expectation=EvidencePeriodConfig(
            sensors={
                "L5": SensorEvidenceConfig(
                    enabled=True,
                    first_year=2000,
                    last_year=2003,
                    first_doy=152,
                    last_doy=273,
                    cloud_cover_threshold=40,
                ),
            }
        ),
        target=EvidencePeriodConfig(
            sensors={
                "L5": SensorEvidenceConfig(
                    enabled=True,
                    first_year=2004,
                    last_year=2005,
                    first_doy=152,
                    last_doy=273,
                    cloud_cover_threshold=40,
                ),
            }
        ),
    ),
    reduction=ReductionConfig(band="nbr"),
    modality=ModalityConfig(constant=True, unimodal=True),
    sensitivity=SensitivityConfig(),
    bulc_advanced_params=BULCAdvancedParams(custom_transition_matrix=NBR12_TRANSITION_MATRIX),
)

DECREASE_THRESHOLD = 0.5
OUTPUT_CSV = Path(__file__).parent / "output" / "bb_complex_fire_replay.csv"

# bulc.py's fixed band-order/name contract (bulcd/engine.py's
# _DECISION_CLASS_NAMES); classification_stack's "class" band is the
# integer index into this list.
_CLASS_NAMES = ["decrease", "unchanged", "increase"]


def _to_date(millis: float) -> str:
    return datetime.datetime.fromtimestamp(millis / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")


def _region_rows(image_collection: ee.ImageCollection, band: str) -> dict[int, float | None]:
    """time (millis) -> band value, via getRegion() at POINT."""
    region = image_collection.select(band).getRegion(POINT, 30).getInfo()
    header, rows = region[0], region[1:]
    time_idx, value_idx = header.index("time"), header.index(band)
    return {row[time_idx]: row[value_idx] for row in rows}


def main() -> None:
    organized = organize_inputs(CONFIG)
    zscore_by_time = _region_rows(organized.lof_zscore, "zscore")

    result = run_bulcd(CONFIG)
    decrease_by_time = _region_rows(result.probability_stack, "decrease")
    unchanged_by_time = _region_rows(result.probability_stack, "unchanged")
    increase_by_time = _region_rows(result.probability_stack, "increase")
    class_by_time = _region_rows(result.classification_stack, "class")

    times = sorted(decrease_by_time)
    rows = []
    first_crossing_seen = False
    for i, t in enumerate(times, start=1):
        zscore = zscore_by_time.get(t)
        decrease = decrease_by_time[t]
        unchanged = unchanged_by_time[t]
        increase = increase_by_time[t]
        class_idx = class_by_time[t]
        is_first_crossing = False
        if not first_crossing_seen and decrease is not None and decrease > DECREASE_THRESHOLD:
            is_first_crossing = True
            first_crossing_seen = True
        rows.append(
            {
                "observation_date": _to_date(t),
                "valid": zscore is not None,
                "zscore": zscore,
                "decrease_probability": decrease,
                "unchanged_probability": unchanged,
                "increase_probability": increase,
                "argmax_class": _CLASS_NAMES[int(class_idx)],
                "observation_number": i,
                "first_decrease_crossing": is_first_crossing,
            }
        )

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    n_valid = sum(1 for r in rows if r["valid"])
    print(f"Wrote {len(rows)} Events ({n_valid} valid) to {OUTPUT_CSV}")
    crossing = next((r for r in rows if r["first_decrease_crossing"]), None)
    if crossing:
        print(
            f"First decrease-probability > {DECREASE_THRESHOLD} crossing: "
            f"{crossing['observation_date']} (observation #{crossing['observation_number']})"
        )
    else:
        print(f"No decrease-probability > {DECREASE_THRESHOLD} crossing in this run.")

    # Cross-check against BULC-D's own public interpretation logic
    # (bulcd.interpret.first_change_year), rather than trusting only this
    # script's own client-side threshold scan.
    year = first_change_year(
        result.probability_stack, class_name="decrease", threshold=DECREASE_THRESHOLD
    )
    year_at_point = year.reduceRegion(ee.Reducer.first(), POINT, 30).getInfo()
    print(f"bulcd.interpret.first_change_year() at point: {year_at_point}")


if __name__ == "__main__":
    main()

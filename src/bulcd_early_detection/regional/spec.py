"""Regional product specification, version 1 (docs/regional_plan.md).

What every regional tile contains, whatever backend computed it: bands,
data types, scaling, nodata and their definitions. No Earth Engine here; the
backends build images to this spec and the validation reads it back.

One image per tile, one BULC-D run per tile, one monitoring season
(`monitoring_year`, season start to end). All bands share the tile's grid
(run_config.Grid).

Masking: a pixel outside the region or on water (the apps' JRC water mask)
is masked in a GEE asset and holds the band's `nodata` value in a file;
masked <=> nodata, in every band. Every other pixel has a value in every
band, except the probabilities where BULC-D produced none (condition 3).
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass

PRODUCT_VERSION = 1

# condition codes: the apps' outcome codes (outputs.DECREASE ... NOT_ANALYZED;
# tests/test_regional_config.py checks they agree).
DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED = 0, 1, 2, 3
CONDITION_LABELS = {DECREASE: "decrease", UNCHANGED: "unchanged", INCREASE: "increase",
                    NOT_ANALYZED: "not analyzed"}

# Probabilities are stored as round(p * PROBABILITY_SCALE): at most 0.5 / 10,000
# from the float value. condition is classified from the float values before
# scaling, so it is exact; reclassifying from the stored probabilities can differ
# only where a probability is within 0.00005 of a threshold.
PROBABILITY_SCALE = 10_000

# "No detection" in the timing bands. Day of year starts at 1, so 0 is free.
NONE = 0

DTYPE_NODATA = {"uint8": 255, "uint16": 65535}

# BULC-D bins the observations into day_step_size-day bins (bulcd default 4,
# unchanged by the apps). Each bin is dated by its END date: bulcd's
# binEvidenceByDayStep stamps system:time_start with the bin end.
TIMING_DATE = "end date of the observation bin"


@dataclass(frozen=True)
class Band:
    name: str
    dtype: str
    description: str
    scale: int = 1   # stored = round(value * scale)

    @property
    def nodata(self) -> int:
        return DTYPE_NODATA[self.dtype]


BANDS = (
    Band("condition", "uint8",
         "Condition at the end of the season: 0 decrease (final P(decrease) > the decrease threshold), "
         "2 increase (final P(increase) > the increase threshold), else 1 unchanged; 3 not analyzed "
         "(land without a BULC-D result, e.g. excluded by an optional land-cover mask). The apps' "
         "condition layer."),
    Band("p_decrease", "uint16", "Final P(decrease) x 10,000; masked where BULC-D produced no probabilities.",
         PROBABILITY_SCALE),
    Band("p_unchanged", "uint16", "Final P(unchanged) x 10,000.", PROBABILITY_SCALE),
    Band("p_increase", "uint16", "Final P(increase) x 10,000.", PROBABILITY_SCALE),
    Band("first_detection_doy", "uint16",
         "Day of year of the first bin in which P(decrease) exceeded the decrease threshold; 0 = no "
         "detection that counts under timing_rule, or not analyzed. The apps' first-detected date."),
    Band("last_detection_doy", "uint16",
         "Day of year of the start of the most recent detection episode; 0 as for first_detection_doy. "
         "Equals first_detection_doy when episode_count is 1."),
    Band("episode_count", "uint8",
         "Detection episodes in the season (docs/findings.md, 2026-10-13: an episode starts at a bin where "
         "P(decrease) > threshold after a bin at or below it); 0 as for first_detection_doy."),
    Band("n_obs_monitoring", "uint16",
         "Monitoring-season bins with at least one valid observation (any enabled monitoring sensor)."),
    Band("n_obs_expectation", "uint16",
         "Expectation-period bins with at least one valid observation (the harmonic fit's sample size)."),
)
BAND_NAMES = tuple(b.name for b in BANDS)
BAND = {b.name: b for b in BANDS}

# Timing rules (the apps' Detection timing setting). confirmed (the apps'
# default): the timing bands count only where the season ends as decrease
# (condition 0); raw: any crossing counts, including one BULC-D later retracts.
TIMING_RULES = ("confirmed", "raw")

# Image properties every tile carries. Values are strings or numbers (GEE asset
# properties); *_json hold JSON.
PROPERTIES = (
    "product_version",       # PRODUCT_VERSION
    "run_id",                # run_config.RegionalRun.run_id
    "tile_id",               # tiling.Tile.id
    "monitoring_year",
    "season_start", "season_end",   # MM-DD, inclusive
    "timing_rule",           # one of TIMING_RULES
    "timing_date",           # TIMING_DATE
    "bin_days",              # bulcd day_step_size
    "grid_json",             # {"crs", "transform"} of the tile's pixels
    "run_json",              # the whole RegionalRun (RegionalRun.to_dict())
    "config_json",           # the BULCDConfig the tile ran (aoi left out, as outputs.run_metadata)
    "as_of_date",            # end of the input window, YYYY-MM-DD: the season end, or the export date if earlier
                             # (scenes acquired by then but not yet in the collections are missing)
    "export_date",           # when the tile was computed, YYYY-MM-DDTHH:MM:SSZ
    "provenance_json",       # git commits of both repos, bulcd and ee versions (provenance.py)
)


def scale_probability(p: float) -> int:
    """Stored value of a probability (the backends do the same on images)."""
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"probability out of range: {p}")
    return int(round(p * PROBABILITY_SCALE))


def unscale_probability(stored: int) -> float:
    return stored / PROBABILITY_SCALE


def spec_dict() -> dict:
    """The spec as data, e.g. to store beside a run's outputs."""
    return {"product_version": PRODUCT_VERSION, "bands": [dataclasses.asdict(b) | {"nodata": b.nodata} for b in BANDS],
            "condition_labels": CONDITION_LABELS, "probability_scale": PROBABILITY_SCALE, "none": NONE,
            "timing_rules": TIMING_RULES, "timing_date": TIMING_DATE, "properties": PROPERTIES}


def spec_json() -> str:
    return json.dumps(spec_dict(), sort_keys=True)

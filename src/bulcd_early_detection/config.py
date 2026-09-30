"""Monitoring-facing controls -> a full `bulcd` BULCDConfig.

The interface layer exposes a handful of settings an end user can reason
about directly (`MonitoringControls`); everything else comes from the
current validated baseline - the exact configuration behind Milestone 1's
production-matrix replays and spatial validation (experiments/
replay_fire_2026.py's build_config() with PRODUCTION_TRANSITION_MATRIX,
recency_factor=1.0). The returned BULCDConfig is a plain bulcd dataclass,
so every advanced field stays reachable and editable after it's built.

No detection logic lives here - this only assembles bulcd's own config.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime
from dataclasses import dataclass

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

# Verbatim from ../BULC-D_rebuild/configs/cell_8c_comparison.yaml, and
# byte-for-byte identical to the legacy GEE app's hardcoded default
# (legacy/6003.3c-BULC-AdvancedParameters.txt lines 142-153) - see
# docs/findings.md, 2026-09-19 and 2026-09-20 entries. Rows are the 10
# z-score bins (most negative first); columns decrease/unchanged/increase.
PRODUCTION_TRANSITION_MATRIX = [
    [0.83, 0.08, 0.08],
    [0.66, 0.24, 0.08],
    [0.53, 0.37, 0.08],
    [0.14, 0.76, 0.08],
    [0.08, 0.83, 0.08],
    [0.08, 0.83, 0.08],
    [0.08, 0.76, 0.14],
    [0.08, 0.37, 0.53],
    [0.08, 0.24, 0.66],
    [0.08, 0.08, 0.83],
]

# Same as every Milestone 1 replay: permissive scene-level prefilter,
# since per-pixel cloud masking is what actually screens the data.
CLOUD_COVER_THRESHOLD = 70

# Expectation (baseline) sensors: L8 only. The validated L8+S2 multi-year
# baseline hit Earth Engine's "User memory limit exceeded" inside
# organize_inputs()'s harmonic fit (docs/findings.md, 2026-09-18).
BASELINE_SENSORS = ("L8",)
MONITORING_SENSORS = ("L8", "L9", "S2")


@dataclass
class MonitoringControls:
    """The small set of settings exposed by default.

    `season_start`/`season_end` define both the monitoring window (in
    `monitoring_year`) and the same-season window used every baseline
    year - the validated approach compares like season to like season.
    Baseline years are inclusive.
    """

    monitoring_year: int = 2026
    season_start: str = "06-01"  # MM-DD
    season_end: str = "09-30"  # MM-DD
    baseline_first_year: int = 2018
    baseline_last_year: int = 2025
    # A change class is mapped only where its final probability exceeds
    # this. Kept >= 0.5 so at most one class can qualify.
    decision_threshold: float = 0.5
    # bulcd SensitivityConfig.z_score_numerator_factor: multiplies
    # (observed - expected) before it becomes a z-score. 1.0 = legacy
    # default; >1 treats smaller departures from the baseline as stronger
    # evidence of change. Not yet tested away from 1.0.
    sensitivity: float = 1.0

    def __post_init__(self) -> None:
        if not 0.5 <= self.decision_threshold < 1.0:
            raise ValueError("decision_threshold must be in [0.5, 1.0)")
        if self.baseline_last_year >= self.monitoring_year:
            raise ValueError("baseline must end before the monitoring year")
        if self.sensitivity <= 0:
            raise ValueError("sensitivity must be positive")
        if self.first_doy > self.last_doy:
            raise ValueError("season_start must be before season_end")

    def _doy(self, month_day: str) -> int:
        date = datetime.date.fromisoformat(f"{self.monitoring_year}-{month_day}")
        return date.timetuple().tm_yday

    @property
    def first_doy(self) -> int:
        return self._doy(self.season_start)

    @property
    def last_doy(self) -> int:
        return self._doy(self.season_end)

    @property
    def monitoring_start(self) -> datetime.date:
        return datetime.date.fromisoformat(f"{self.monitoring_year}-{self.season_start}")

    @property
    def monitoring_end(self) -> datetime.date:
        return datetime.date.fromisoformat(f"{self.monitoring_year}-{self.season_end}")


def build_config(
    controls: MonitoringControls,
    aoi_coordinates: list[list[float]] | None = None,
    aoi_asset: str | None = None,
) -> BULCDConfig:
    """Validated baseline config for one study area: either
    `aoi_coordinates` (one polygon ring) or `aoi_asset` (an Earth Engine
    FeatureCollection asset ID - bulcd uses its union geometry)."""
    if (aoi_coordinates is None) == (aoi_asset is None):
        raise ValueError("pass exactly one of aoi_coordinates / aoi_asset")

    def sensors(names, first_year, last_year):
        # bulcd's last_year is EXCLUSIVE; controls use inclusive years.
        return {
            name: SensorEvidenceConfig(
                enabled=True,
                first_year=first_year,
                last_year=last_year + 1,
                first_doy=controls.first_doy,
                last_doy=controls.last_doy,
                cloud_cover_threshold=CLOUD_COVER_THRESHOLD,
            )
            for name in names
        }

    return BULCDConfig(
        study_area=StudyAreaConfig(aoi_coordinates=aoi_coordinates, aoi_asset=aoi_asset),
        evidence=EvidenceConfig(
            expectation=EvidencePeriodConfig(
                sensors=sensors(BASELINE_SENSORS, controls.baseline_first_year, controls.baseline_last_year)
            ),
            target=EvidencePeriodConfig(
                sensors=sensors(MONITORING_SENSORS, controls.monitoring_year, controls.monitoring_year)
            ),
        ),
        reduction=ReductionConfig(band="nbr"),
        modality=ModalityConfig(constant=True, unimodal=True),
        sensitivity=SensitivityConfig(z_score_numerator_factor=controls.sensitivity),
        bulc_advanced_params=BULCAdvancedParams(
            custom_transition_matrix=PRODUCTION_TRANSITION_MATRIX, recency_factor=1.0
        ),
    )


_SENSOR_NAMES = {"L5": "Landsat 5", "L7": "Landsat 7", "L8": "Landsat 8", "L9": "Landsat 9", "S2": "Sentinel-2"}


def _doy_label(doy: int) -> str:
    return (datetime.date(2025, 1, 1) + datetime.timedelta(days=doy - 1)).strftime("%b %-d")  # non-leap reference year


def config_summary(config: BULCDConfig) -> list[tuple[str, str]]:
    """(setting, value) rows in plain language for display - the parameters
    that define a run, not a replacement for the full config."""
    ev = config.evidence
    adv = config.bulc_advanced_params

    def period(p):
        on = {n: s for n, s in p.sensors.items() if s.enabled}
        years = sorted({(s.first_year, s.last_year - 1) for s in on.values()})
        doys = sorted({(s.first_doy, s.last_doy) for s in on.values()})
        yr = ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in years)
        window = ", ".join(f"{_doy_label(a)} – {_doy_label(b)}" for a, b in doys)
        return f"{yr}, {window} ({', '.join(_SENSOR_NAMES.get(n, n) for n in on)})"

    modality = [f.name for f in dataclasses.fields(config.modality) if getattr(config.modality, f.name)]
    model = {("constant", "unimodal"): "average level + one annual cycle"}.get(tuple(modality), ", ".join(modality))
    masks = [m for m, on in (("water", config.study_area.mask_water), ("non-forest land", config.study_area.mask_non_forest)) if on]
    return [
        ("Baseline (expectation)", period(ev.expectation)),
        ("Monitoring season", period(ev.target)),
        ("Vegetation index", config.reduction.band.upper()),
        ("Seasonal model", model),
        ("Sensitivity", f"{config.sensitivity.z_score_numerator_factor}"),
        ("Evidence table", "legacy app's default" if adv.custom_transition_matrix == PRODUCTION_TRANSITION_MATRIX else "custom"),
        ("Dampening", f"{adv.dampening_factor}"),
        ("Posterior leveler", f"{adv.posterior_leveler}" + (" (off)" if adv.posterior_leveler == 1.0 else "")),
        ("Starting odds", "even" if adv.initializing_leveler == 0.0 else f"initial leveler {adv.initializing_leveler}"),
        ("Recency weighting", "off" if adv.recency_factor == 1.0 else f"{adv.recency_factor}"),
        ("Not analyzed", ", ".join(masks) or "nothing masked"),
    ]


def set_monitoring_years(config: BULCDConfig, first_year: int, last_year: int) -> BULCDConfig:
    """Copy of `config` whose monitoring (target) period spans first_year..
    last_year inclusive, same seasonal window each year. bulcd bins each
    year's season separately and runs them as one continuous sequence, so
    this answers "when was a departure first detected?" across years. The
    baseline must end before first_year (not checked here - build the config
    from controls whose baseline_last_year < first_year)."""
    config = copy.deepcopy(config)
    for sensor in config.evidence.target.sensors.values():
        if sensor.enabled:
            sensor.first_year = first_year
            sensor.last_year = last_year + 1  # bulcd's last_year is exclusive
    return config

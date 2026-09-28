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


def config_summary(config: BULCDConfig) -> list[tuple[str, str]]:
    """(setting, value) rows for the parameters that define the baseline -
    for display, not a replacement for the full config."""
    ev = config.evidence
    adv = config.bulc_advanced_params

    def period(p):
        on = {n: s for n, s in p.sensors.items() if s.enabled}
        years = {(s.first_year, s.last_year - 1) for s in on.values()}
        doys = {(s.first_doy, s.last_doy) for s in on.values()}
        return f"{', '.join(on)}; years {sorted(years)}; DOY {sorted(doys)}"

    matrix = (
        "production (legacy default)"
        if adv.custom_transition_matrix == PRODUCTION_TRANSITION_MATRIX
        else "custom / non-production"
    )
    return [
        ("Baseline (expectation) period", period(ev.expectation)),
        ("Monitoring (target) period", period(ev.target)),
        ("Spectral index", config.reduction.band.upper()),
        ("Expectation model", ", ".join(f.name for f in dataclasses.fields(config.modality) if getattr(config.modality, f.name))),
        ("Sensitivity (z-score numerator factor)", str(config.sensitivity.z_score_numerator_factor)),
        ("Transition matrix", matrix),
        ("dampening_factor", str(adv.dampening_factor)),
        ("posterior_leveler", str(adv.posterior_leveler)),
        ("initializing_leveler", str(adv.initializing_leveler)),
        ("recency_factor", str(adv.recency_factor)),
        ("Water mask / non-forest mask", f"{config.study_area.mask_water} / {config.study_area.mask_non_forest}"),
    ]

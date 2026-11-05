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

# Sensors either period can use, in display order (gee/config.js SENSORS).
SENSORS = ("L5", "L7", "L8", "L9", "S2")
# Default expectation (baseline) sensors: L8 only, unchanged since the
# validated L8+S2 multi-year baseline hit Earth Engine's "User memory limit
# exceeded" inside organize_inputs()'s harmonic fit (docs/findings.md,
# 2026-09-18). MonitoringControls.expectation_sensors selects others.
BASELINE_SENSORS = ("L8",)
# Monitoring can't use Landsat 5: it stopped imaging in 2011, before the
# earliest monitoring year (MONITORING_YEARS).
MONITORING_SENSORS = ("L7", "L8", "L9", "S2")
# Monitoring sensors on by default (Landsat 7 is an opt-in for historical years).
DEFAULT_MONITORING_SENSORS = ("L8", "L9", "S2")
# The widgets' year limits (gee/config.js RANGES): expectation years from
# 2010 (Landsat 5/7 before Landsat 8), monitoring years from 2015 (the first
# year a 2-year Landsat 8 expectation fits before; docs/findings.md, 2026-11-02).
EXPECTATION_YEARS = (2010, 2025)
MONITORING_YEARS = tuple(range(2015, 2027))
# Algorithm defaults: the original BULC-D GUI's, as in the GEE app (gee/config.js
# APP_DEFAULTS; read from the legacy source, see gee/tests/legacy_gui.js).
# The expectation years, monitoring year, season and sensors had no default
# there (the user entered them); the apps' are Early Detection choices.
LEGACY_DEFAULTS = {"sensitivity": 1.0, "decrease_threshold": 0.65, "increase_threshold": 0.75, "dampening": 0.7,
                   "posterior_leveler": 0.9, "mask_forest": False, "mask_water": True, "fit_order": 1}
# Detection timing (first detected season, last detection, detection episodes):
# confirmed = only a season that ends as decrease counts (the first-detected
# season's definition since 2026-09-30); raw = any crossing counts. Not an
# original-GUI setting (it had no such product). gee/config.js APP_DEFAULTS.timing_confirmed.
TIMING_CONFIRMED_DEFAULT = True
# Starting probabilities 0.1 decrease / 0.8 unchanged / 0.1 increase
# (initializingLeveler 0.7 on "unchanged"). Fixed; not a control.
INITIALIZING_LEVELER = 0.7
# Years each sensor has no or fewer observations in, for the default Jun-Sep
# season: (first year, last year, inclusive; None = open-ended, "none" or
# "fewer", what is missing). From scene and clear-observation counts over the
# testsite and two Apostle Islands forests (docs/findings.md, 2026-10-19 and
# 2026-11-02). gee/config.js SENSOR_GAPS holds the same table.
SENSOR_GAPS = {
    "L5": [(2012, None, "none", "no observations after 2011 (it stopped imaging in November 2011)")],
    "L7": [(2024, None, "none", "no observations after 2023 (none from 2024 in tests)"),
           (2022, 2023, "fewer", "fewer observations in 2022-2023 (its orbit was lowered in 2022: about two "
                                 "thirds to three quarters as many scenes in tests)")],
    "L8": [(None, 2012, "none", "no observations before 2013 (its first scenes are from April 2013)")],
    "L9": [(None, 2021, "none", "no observations before 2022 (its first scenes are from Oct 31, 2021)")],
    "S2": [(None, 2015, "none", "no observations before 2016 (none in Earth Engine's surface-reflectance "
                                "collection at the testsite in tests)"),
           (2016, 2017, "fewer", "fewer observations before 2018 (one satellite until Sentinel-2B joined in "
                                 "mid-2017: about a quarter to half as many scenes in tests)")],
}
# Said whenever a sensor is chosen for either period.
SENSOR_NOTES = {
    "L7": ("Landsat 7 images since 2003 have striped gaps (its scan-line corrector failed; about a fifth of each "
           "scene is missing), so it gives fewer clear observations per pixel than Landsat 8: about 75-95% as many "
           "in tests."),
}
# Landsat 5 and 7 (TM/ETM+) vs Landsat 8 and 9 (OLI): different instruments.
_TM_ETM = ("L5", "L7")

# Expectation length (years) above which a Sentinel-2 expectation is likely
# to exceed Earth Engine's interactive memory limit: with L8+S2 or L8+L9+S2, the
# pixel inspector failed at every length over 2 years (docs/findings.md, 2026-10-19).
S2_EXPECTATION_MAX_YEARS = 2

# Expectation fit order N = a constant plus the first N annual harmonics
# (1, 2 and 3 cycles per year): the legacy modalityDictionary's unimodal,
# bimodal and trimodal flags, which add their terms cumulatively. Order 1
# (constant + unimodal) is the original BULC-D GUI's default.
FIT_ORDERS = (1, 2, 3)
_ORDER_FLAGS = ("unimodal", "bimodal", "trimodal")
# Shortest seasonal window (days) at which an order-2/3 fit stays well
# conditioned. Within a shorter window the harmonics are nearly collinear and
# the fit can chase noise (docs/findings.md, 2026-10-13). gee/config.js holds
# the same values.
MIN_WINDOW_DAYS = {2: 183, 3: 245}


def class_thresholds(threshold: float, increase_threshold: float | None = None) -> dict[str, float]:
    """{"decrease": threshold, "increase": increase_threshold, or threshold
    when that is None}."""
    return {"decrease": threshold, "increase": threshold if increase_threshold is None else increase_threshold}


def modality_for_order(order: int) -> ModalityConfig:
    """bulcd ModalityConfig for expectation fit order 1, 2 or 3."""
    if order not in FIT_ORDERS:
        raise ValueError(f"fit_order must be one of {FIT_ORDERS}")
    return ModalityConfig(constant=True, **{flag: i < order for i, flag in enumerate(_ORDER_FLAGS)})


def order_of_modality(modality: ModalityConfig) -> int | None:
    """The fit order a ModalityConfig corresponds to, or None if it isn't one
    of modality_for_order()'s (e.g. linear, or bimodal without unimodal)."""
    return next((n for n in FIT_ORDERS if modality == modality_for_order(n)), None)


def _sensor_list(codes) -> str:
    names = [_SENSOR_NAMES.get(c, c) for c in SENSORS if c in codes]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _years_label(first: int, last: int) -> str:
    return f"year {first}" if first == last else f"years {first}-{last}"


def _gaps_within(code: str, first_year: int, last_year: int):
    """(kind, text, overlap first, overlap last) for each of `code`'s gaps
    that overlaps first_year..last_year."""
    out = []
    for g0, g1, kind, text in SENSOR_GAPS.get(code, []):
        a, b = max(first_year, g0 if g0 is not None else first_year), min(last_year, g1 if g1 is not None else last_year)
        if a <= b:
            out.append((kind, text, a, b))
    return out


def has_data(code: str, first_year: int, last_year: int) -> bool:
    """Whether `code` has observations in at least one of first_year..last_year."""
    covered = sum(b - a + 1 for kind, _, a, b in _gaps_within(code, first_year, last_year) if kind == "none")
    return covered < last_year - first_year + 1


def availability_problem(expectation_sensors, monitoring_sensors, first_year: int, last_year: int,
                         monitoring_year: int) -> str | None:
    """The data-availability problem that blocks a run, or None: no chosen
    expectation sensor has observations in any expectation year, or no chosen
    monitoring sensor has observations in the monitoring year. Same text as
    gee/config.js availabilityProblem()."""
    for label, codes, y0, y1 in (("expectation", expectation_sensors, first_year, last_year),
                                 ("monitoring", monitoring_sensors, monitoring_year, monitoring_year)):
        codes = [c for c in SENSORS if c in codes]
        if codes and not any(has_data(c, y0, y1) for c in codes):
            reasons = "; ".join(f"{_SENSOR_NAMES[c]} has {t}" for c in codes
                                for k, t, _, _ in _gaps_within(c, y0, y1) if k == "none")
            when = str(y0) if y0 == y1 else f"{y0}-{y1}"
            return f"No selected {label} sensor has observations in {when}: {reasons}. Choose other sensors or years."
    return None


def sensor_warnings(expectation_sensors, monitoring_sensors, first_year: int, last_year: int,
                    monitoring_year: int | None = None, timing_years=None) -> list[str]:
    """Warnings about the sensor choice (none blocks a run). Same text as
    gee/config.js sensorWarnings().
      - the two periods use different sensors (among those with observations
        in each period);
      - an expectation sensor has no or fewer data in some expectation years;
      - a monitoring sensor has no or fewer data in the monitoring year
        (`monitoring_year`; skipped when None);
      - a first-detected-season year (`timing_years`, optional) in which no
        monitoring sensor has data: its run has nothing to evaluate and ends
        with no detection (docs/findings.md, 2026-11-02);
      - notes on a chosen sensor (Landsat 7's striped gaps);
      - a Sentinel-2 expectation long enough to likely exceed Earth Engine's
        interactive memory limit."""
    exp, mon = [c for c in SENSORS if c in expectation_sensors], [c for c in SENSORS if c in monitoring_sensors]
    out = []
    exp_used = [c for c in exp if has_data(c, first_year, last_year)]
    mon_used = [c for c in mon if monitoring_year is None or has_data(c, monitoring_year, monitoring_year)]
    if exp_used and mon_used and exp_used != mon_used:
        differ = set(exp_used) ^ set(mon_used)
        text = f"The expectation uses {_sensor_list(exp_used)} and monitoring uses {_sensor_list(mon_used)}. "
        if "S2" not in differ and differ & set(_TM_ETM):
            text += ("Landsat 5 and 7 (TM/ETM+) and Landsat 8 and 9 (OLI) measure slightly different wavelengths, "
                     "and BULC-D does not adjust for it. In tests the NBR difference between them was small "
                     "(median 0.013 or less) and caused no false change in stable forest, but decreases agreed best "
                     "with real change when Landsat 8 was in both periods.")
        else:
            text += ("Differences between sensors can register as change: in earlier tests, Sentinel-2 in "
                     "monitoring but not in the expectation produced false decreases at stable sites that "
                     "disappeared when both periods used the same sensors.")
        out.append(text)
    for c in exp:
        for _, text, a, b in _gaps_within(c, first_year, last_year):
            out.append(f"{_SENSOR_NAMES[c]} has {text}, which affects expectation {_years_label(a, b)}"
                       + ("; the sensor mix changes partway through the expectation." if len(exp) > 1 else "."))
    if monitoring_year is not None:
        for c in mon:
            for _, text, _, _ in _gaps_within(c, monitoring_year, monitoring_year):
                out.append(f"{_SENSOR_NAMES[c]} has {text}, which affects the monitoring year ({monitoring_year}).")
    empty = [y for y in (timing_years or []) if y != monitoring_year and not any(has_data(c, y, y) for c in mon)]
    if empty:
        out.append(f"No selected monitoring sensor has observations in {', '.join(map(str, empty))}, so the "
                   f"first-detected-season run for {'that season' if len(empty) == 1 else 'those seasons'} has "
                   "nothing to evaluate and shows no detection there.")
    for c in SENSORS:
        if c in SENSOR_NOTES and (c in exp or c in mon):
            out.append(SENSOR_NOTES[c])
    n = last_year - first_year + 1
    if "S2" in exp and n > S2_EXPECTATION_MAX_YEARS:
        out.append(f"A {n}-year expectation with Sentinel-2 is likely to exceed Earth Engine's memory limit: in "
                   f"tests, Sentinel-2 expectations longer than {S2_EXPECTATION_MAX_YEARS} years failed "
                   "with the pixel inspector failing every time (usually \"User memory limit exceeded\") and map "
                   "layers failing intermittently. Use fewer expectation years or leave Sentinel-2 out of the "
                   "expectation.")
    return out


def fit_order_warning(order: int, window_days: int) -> str | None:
    """Warning for a higher-order fit over a short seasonal window, or None.
    Same text as gee/config.js fitOrderWarning()."""
    need = MIN_WINDOW_DAYS.get(order)
    if need is None or window_days >= need:
        return None
    return (f"Expectation fit order {order} with a {window_days}-day season may be unstable: within a window "
            f"shorter than about {need} days the harmonics are hard to tell apart, so the fitted curve can follow "
            "noise, especially with few expectation years or clear observations. Check the fit in the pixel "
            "inspector.")


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
    # its threshold: decision_threshold for decrease, and for increase too
    # unless increase_threshold is set (the original BULC-D GUI used 0.65
    # for decrease and 0.75 for increase). Kept >= 0.5 so at most one class
    # can qualify.
    decision_threshold: float = 0.5
    increase_threshold: float | None = None
    # bulcd SensitivityConfig.z_score_numerator_factor: multiplies
    # (observed - expected) before it becomes a z-score. 1.0 = legacy
    # default; >1 treats smaller departures from the baseline as stronger
    # evidence of change. Not yet tested away from 1.0.
    sensitivity: float = 1.0
    # Expectation fit order (FIT_ORDERS): 1 = the original GUI's constant +
    # one annual cycle; 2 and 3 add the second and third annual harmonics.
    fit_order: int = 1
    # Expectation sensors (a subset of SENSORS); default Landsat 8 only.
    expectation_sensors: tuple[str, ...] = BASELINE_SENSORS

    def __post_init__(self) -> None:
        if not 0.5 <= self.decision_threshold < 1.0:
            raise ValueError("decision_threshold must be in [0.5, 1.0)")
        if self.increase_threshold is not None and not 0.5 <= self.increase_threshold < 1.0:
            raise ValueError("increase_threshold must be in [0.5, 1.0)")
        if self.baseline_last_year >= self.monitoring_year:
            raise ValueError("baseline must end before the monitoring year")
        if self.sensitivity <= 0:
            raise ValueError("sensitivity must be positive")
        if self.first_doy > self.last_doy:
            raise ValueError("season_start must be before season_end")
        if self.fit_order not in FIT_ORDERS:
            raise ValueError(f"fit_order must be one of {FIT_ORDERS}")
        if not self.expectation_sensors or not set(self.expectation_sensors) <= set(SENSORS):
            raise ValueError(f"expectation_sensors must be a non-empty subset of {SENSORS}")

    def _doy(self, month_day: str) -> int:
        date = datetime.date.fromisoformat(f"{self.monitoring_year}-{month_day}")
        return date.timetuple().tm_yday

    @property
    def thresholds(self) -> dict[str, float]:
        """The threshold for each change class."""
        return class_thresholds(self.decision_threshold, self.increase_threshold)

    @property
    def first_doy(self) -> int:
        return self._doy(self.season_start)

    @property
    def last_doy(self) -> int:
        return self._doy(self.season_end)

    @property
    def window_days(self) -> int:
        """Length of the seasonal window in days, both ends included."""
        return self.last_doy - self.first_doy + 1

    @property
    def fit_order_warning(self) -> str | None:
        return fit_order_warning(self.fit_order, self.window_days)

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

    # The default monitoring sensors, all on (EarlyDetectionApp.build() applies
    # the user's choice: with_monitoring_sensors()).
    monitoring = sensors(DEFAULT_MONITORING_SENSORS, controls.monitoring_year, controls.monitoring_year)

    return BULCDConfig(
        study_area=StudyAreaConfig(aoi_coordinates=aoi_coordinates, aoi_asset=aoi_asset),
        evidence=EvidenceConfig(
            expectation=EvidencePeriodConfig(
                sensors=sensors([c for c in SENSORS if c in controls.expectation_sensors], controls.baseline_first_year, controls.baseline_last_year)
            ),
            target=EvidencePeriodConfig(sensors=monitoring),
        ),
        reduction=ReductionConfig(band="nbr"),
        modality=modality_for_order(controls.fit_order),
        sensitivity=SensitivityConfig(z_score_numerator_factor=controls.sensitivity),
        bulc_advanced_params=BULCAdvancedParams(
            custom_transition_matrix=PRODUCTION_TRANSITION_MATRIX, recency_factor=1.0
        ),
    )


def with_monitoring_sensors(config: BULCDConfig, chosen) -> BULCDConfig:
    """`config` (from build_config()) with the monitoring sensors switched to
    `chosen`, in place: the default sensors stay listed, enabled or not (as
    before Landsat 7 was added), and an opt-in sensor (Landsat 7) is added,
    with the same years, window and cloud prefilter, only when chosen. Same as
    gee/config.js buildConfig()."""
    target = config.evidence.target.sensors
    template = next(iter(target.values()))
    out = {}
    for code in MONITORING_SENSORS:
        if code in target:
            out[code] = target[code]
            out[code].enabled = code in chosen
        elif code in chosen:
            out[code] = dataclasses.replace(template, enabled=True)
    config.evidence.target.sensors = out
    return config


def apply_advanced(config: BULCDConfig, *, dampening: float, posterior_leveler: float, monitoring_sensors,
                   mask_forest: bool, mask_water: bool) -> BULCDConfig:
    """build_config() plus the apps' Advanced settings, in place: dampening,
    posterior leveler, the fixed starting odds (INITIALIZING_LEVELER), which
    monitoring sensors are enabled (with_monitoring_sensors(): the default ones
    stay in the config, disabled, as the GUI's unticked boxes leave them; an
    opt-in Landsat 7 is added only when chosen) and the masks. The interactive app's
    build() and the regional runs both use it. Returns `config`."""
    config.bulc_advanced_params.dampening_factor = dampening
    config.bulc_advanced_params.posterior_leveler = posterior_leveler
    config.bulc_advanced_params.initializing_leveler = INITIALIZING_LEVELER
    with_monitoring_sensors(config, monitoring_sensors)
    config.study_area.mask_non_forest = mask_forest
    config.study_area.mask_water = mask_water
    return config


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

    order = order_of_modality(config.modality)
    if order is None:
        model = ", ".join(f.name for f in dataclasses.fields(config.modality) if getattr(config.modality, f.name))
    else:
        model = (f"expectation fit order {order}: average level + "
                 + ("one annual cycle", "cycles of 1 and 2 per year", "cycles of 1, 2 and 3 per year")[order - 1])
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
        ("Starting odds", "even" if adv.initializing_leveler == 0.0 else
         "{0:.2f} decrease / {1:.2f} unchanged / {0:.2f} increase".format((1 - adv.initializing_leveler) / 3,
                                                                          adv.initializing_leveler + (1 - adv.initializing_leveler) / 3)),
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

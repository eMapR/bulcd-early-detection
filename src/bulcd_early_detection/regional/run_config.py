"""Regional run configuration (no Earth Engine): what to compute, where, and
on which grid, as one YAML file per run.

A RegionalRun holds the apps' settings - MonitoringControls plus the Advanced
settings - so a tile's BULCDConfig is built exactly as the interactive app
builds it (config.build_config + config.apply_advanced). Defaults are the
apps' defaults (the original BULC-D GUI's algorithm settings, Early Detection's
years and season), except where docs/regional_plan.md decided otherwise.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from pathlib import Path

from bulcd.config.schema import BULCDConfig

from ..config import (DEFAULT_MONITORING_SENSORS, LEGACY_DEFAULTS, MONITORING_SENSORS, TIMING_CONFIRMED_DEFAULT,
                      MonitoringControls, apply_advanced, availability_problem, build_config, fit_order_warning,
                      sensor_warnings)
from . import spec
from .tiling import Grid, Tile


def app_default_controls(**changes) -> MonitoringControls:
    """The interactive apps' default settings (app.py widgets, gee/config.js
    APP_DEFAULTS) as MonitoringControls, with `changes` applied."""
    d = LEGACY_DEFAULTS
    defaults = dict(monitoring_year=2026, season_start="06-01", season_end="09-30", baseline_first_year=2018,
                    baseline_last_year=2023, decision_threshold=d["decrease_threshold"],
                    increase_threshold=d["increase_threshold"], sensitivity=d["sensitivity"],
                    fit_order=d["fit_order"])
    return MonitoringControls(**(defaults | changes))


@dataclass
class AdvancedSettings:
    """The apps' Advanced settings (config.apply_advanced), plus the detection
    timing rule. Defaults: the apps'. Monitoring sensors default to the apps'
    default boxes (DEFAULT_MONITORING_SENSORS: no Landsat 7, which is an
    opt-in for historical years and must be listed explicitly)."""
    monitoring_sensors: tuple[str, ...] = DEFAULT_MONITORING_SENSORS
    dampening: float = LEGACY_DEFAULTS["dampening"]
    posterior_leveler: float = LEGACY_DEFAULTS["posterior_leveler"]
    mask_forest: bool = LEGACY_DEFAULTS["mask_forest"]
    mask_water: bool = LEGACY_DEFAULTS["mask_water"]
    timing_rule: str = "confirmed" if TIMING_CONFIRMED_DEFAULT else "raw"

    def __post_init__(self) -> None:
        chosen = tuple(self.monitoring_sensors)
        self.monitoring_sensors = tuple(c for c in MONITORING_SENSORS if c in chosen)
        if not self.monitoring_sensors or len(self.monitoring_sensors) != len(set(chosen)):
            raise ValueError(f"monitoring_sensors must be a non-empty subset of {MONITORING_SENSORS}: {chosen}")
        if self.timing_rule not in spec.TIMING_RULES:
            raise ValueError(f"timing_rule must be one of {spec.TIMING_RULES}")


@dataclass
class Region:
    """The area to compute: a rectangle in the grid CRS, snapped outward to
    whole pixels. (Ecoregion polygons come later.)"""
    name: str
    bounds: tuple[float, float, float, float]   # xmin, ymin, xmax, ymax

    def __post_init__(self) -> None:
        self.bounds = tuple(float(v) for v in self.bounds)
        if not (self.bounds[0] < self.bounds[2] and self.bounds[1] < self.bounds[3]):
            raise ValueError(f"region bounds must be (xmin, ymin, xmax, ymax): {self.bounds}")


@dataclass
class RegionalRun:
    run_id: str
    region: Region
    controls: MonitoringControls = field(default_factory=app_default_controls)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    grid: Grid = field(default_factory=Grid)
    product_version: int = spec.PRODUCT_VERSION
    description: str = ""

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", self.run_id):
            # It names the run's ImageCollection asset and tile assets.
            raise ValueError("run_id: lowercase letters, digits, '_' and '-' only")
        if self.product_version != spec.PRODUCT_VERSION:
            raise ValueError(f"this code writes product version {spec.PRODUCT_VERSION}, not {self.product_version}")
        if self.region.bounds != self.grid.snap(self.region.bounds):
            raise ValueError(f"region bounds are not on the {self.grid.scale} m grid: {self.region.bounds} "
                             f"(snapped: {self.grid.snap(self.region.bounds)})")
        # The apps block a run with no data in a period (config.availability_problem()).
        problem = self.availability_problem()
        if problem:
            raise ValueError(problem)

    @property
    def tiles(self) -> list[Tile]:
        return self.grid.tiles(self.region.bounds)

    def bulcd_config(self, **aoi) -> BULCDConfig:
        """One tile's BULCDConfig (aoi_coordinates= or aoi_asset=), built as the
        interactive app builds it."""
        a = self.advanced
        return apply_advanced(build_config(self.controls, **aoi), dampening=a.dampening,
                              posterior_leveler=a.posterior_leveler, monitoring_sensors=a.monitoring_sensors,
                              mask_forest=a.mask_forest, mask_water=a.mask_water)

    def availability_problem(self) -> str | None:
        """The apps' blocking data-availability check (config.availability_problem())."""
        c = self.controls
        return availability_problem(c.expectation_sensors, self.advanced.monitoring_sensors, c.baseline_first_year,
                                    c.baseline_last_year, c.monitoring_year)

    def warnings(self) -> list[str]:
        """The apps' warnings for these settings (none blocks a run)."""
        c = self.controls
        out = sensor_warnings(c.expectation_sensors, self.advanced.monitoring_sensors, c.baseline_first_year,
                              c.baseline_last_year, monitoring_year=c.monitoring_year)
        w = fit_order_warning(c.fit_order, c.window_days)
        return out + ([w] if w else [])

    def to_dict(self) -> dict:
        controls = dataclasses.asdict(self.controls)
        controls["expectation_sensors"] = list(controls["expectation_sensors"])
        advanced = dataclasses.asdict(self.advanced)
        advanced["monitoring_sensors"] = list(advanced["monitoring_sensors"])
        return {"run_id": self.run_id, "description": self.description, "product_version": self.product_version,
                "region": {"name": self.region.name, "bounds": list(self.region.bounds)},
                "grid": self.grid.to_dict(), "controls": controls, "advanced": advanced}

    @classmethod
    def from_dict(cls, d: dict) -> RegionalRun:
        known = {"run_id", "description", "product_version", "region", "grid", "controls", "advanced"}
        if set(d) - known:
            raise ValueError(f"unknown keys in run config: {sorted(set(d) - known)}")
        controls = dict(d.get("controls", {}))
        if "expectation_sensors" in controls:
            controls["expectation_sensors"] = tuple(controls["expectation_sensors"])
        return cls(run_id=d["run_id"], description=d.get("description", ""),
                   product_version=d.get("product_version", spec.PRODUCT_VERSION),
                   region=Region(**d["region"]),
                   grid=Grid.from_dict(d["grid"]) if "grid" in d else Grid(),
                   controls=app_default_controls(**controls),
                   advanced=AdvancedSettings(**d.get("advanced", {})))

    def to_yaml(self) -> str:
        import yaml
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> RegionalRun:
        import yaml
        return cls.from_dict(yaml.safe_load(text))

    @classmethod
    def load(cls, path: str | Path) -> RegionalRun:
        return cls.from_yaml(Path(path).read_text())

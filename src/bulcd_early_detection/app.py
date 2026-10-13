"""Interactive Early Detection prototype (ipywidgets + ipyleaflet).

A functional prototype / specification for a future Early Detection GUI:
choose an area -> set expectation and monitoring -> run -> view condition
and timing -> compare imagery -> click a pixel to see why and when it was
flagged. Everything is computed live in Earth Engine from the same helpers
the demonstration notebooks use; nothing here changes BULC-D.

    from bulcd_early_detection.app import EarlyDetectionApp
    EarlyDetectionApp().show()
"""

from __future__ import annotations

import dataclasses
import datetime
import math
import urllib.request
from pathlib import Path

import ee
import ipyleaflet
import ipywidgets as W
from IPython.display import Markdown, display

from . import compare, drawing, outputs, pixel, render, report
from .config import FIT_ORDERS, MonitoringControls, build_config

# Earth Engine requests have no deadline by default, so one stalled request can
# freeze the whole app; fail it after this long instead (ms).
REQUEST_DEADLINE_MS = 300_000
EXAMPLE_ASSETS = {"testsite (western Oregon, 26 km²)": "projects/bulcd-python-rebuild/assets/testsite"}
MAX_TIMING_SEASONS = 3
# Algorithm defaults: the original BULC-D GUI's, as in the GEE app (gee/config.js
# APP_DEFAULTS; read from the legacy source, see gee/tests/legacy_gui.js).
# The expectation years, monitoring year, season and sensors had no default
# there (the user entered them); theirs below are Early Detection choices.
LEGACY_DEFAULTS = {"sensitivity": 1.0, "decrease_threshold": 0.65, "increase_threshold": 0.75, "dampening": 0.7,
                   "posterior_leveler": 0.9, "mask_forest": False, "mask_water": True, "fit_order": 1}
# Detection timing (first detected season, last detection, detection episodes):
# confirmed = only a season that ends as decrease counts (the first-detected
# season's definition since 2026-09-30); raw = any crossing counts. Not an
# original-GUI setting (it had no such product). gee/config.js APP_DEFAULTS.timing_confirmed.
TIMING_CONFIRMED_DEFAULT = True
# Expectation fit order choices (config.FIT_ORDERS); gee/config.js FIT_ORDER_LABELS holds the same labels.
FIT_ORDER_LABELS = {1: "1: one annual cycle (original BULC-D)", 2: "2: adds 2 cycles per year",
                    3: "3: adds 2 and 3 cycles per year"}
# The Parameter behavior tab's response curves, "default" marked at the values above.
APP_PARAMETER_SWEEPS = [
    ("Sensitivity", "scales every departure from normal", [0.5, 0.75, 1.0, 1.5, 2.0],
     lambda v: {"controls": {"sensitivity": v}}, LEGACY_DEFAULTS["sensitivity"]),
    ("Decrease threshold", "how sure before a decrease is mapped", [0.5, 0.6, 0.65, 0.7, 0.8, 0.9, 0.95],
     lambda v: {"controls": {"decision_threshold": v}}, LEGACY_DEFAULTS["decrease_threshold"]),
    ("Increase threshold", "how sure before an increase is mapped", [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 0.95],
     lambda v: {"controls": {"increase_threshold": v}}, LEGACY_DEFAULTS["increase_threshold"]),
    ("Dampening", "weight of each single observation", [0.3, 0.5, 0.7, 0.9, 1.0],
     lambda v: {"edit": compare._set_advanced("dampening_factor", v)}, LEGACY_DEFAULTS["dampening"]),
    ("Posterior leveler", "pull toward even odds after each update (1 = off)", [0.7, 0.8, 0.9, 0.95, 1.0],
     lambda v: {"edit": compare._set_advanced("posterior_leveler", v)}, LEGACY_DEFAULTS["posterior_leveler"]),
]
# Starting probabilities 0.1 decrease / 0.8 unchanged / 0.1 increase
# (initializingLeveler 0.7 on "unchanged"). Fixed; not a control.
INITIALIZING_LEVELER = 0.7


_MONTHS = [(datetime.date(2025, m, 1).strftime("%b"), m) for m in range(1, 13)]
_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]   # Feb 29 left out: it doesn't exist most years


class SeasonWindow:
    """Start and end month/day pickers covering the whole year - any window BULC-D supports:
    a start day and an end day within one calendar year, applied to every expectation and
    monitoring year (a window can't wrap past Dec 31). `.value` is ("MM-DD", "MM-DD")."""

    def __init__(self, start=(6, 1), end=(9, 30)):
        self.start_month, self.start_day = self._pair("Season starts:", *start)
        self.end_month, self.end_day = self._pair("ends:", *end)
        self.widget = W.HBox([self.start_month, self.start_day, W.HTML("&nbsp;&nbsp;"), self.end_month, self.end_day])

    @staticmethod
    def _pair(label, month, day):
        m = W.Dropdown(options=_MONTHS, value=month, description=label,
                       style={"description_width": "170px" if label.startswith("Season") else "40px"},
                       layout=W.Layout(width="260px" if label.startswith("Season") else "130px"))
        d = W.Dropdown(options=list(range(1, _DAYS_IN_MONTH[month - 1] + 1)), value=day, layout=W.Layout(width="70px"))
        def fit_days(ch):
            keep = min(d.value, _DAYS_IN_MONTH[ch["new"] - 1])
            d.options = list(range(1, _DAYS_IN_MONTH[ch["new"] - 1] + 1))
            d.value = keep
        m.observe(fit_days, "value")
        return m, d

    @property
    def value(self) -> tuple[str, str]:
        return (f"{self.start_month.value:02d}-{self.start_day.value:02d}", f"{self.end_month.value:02d}-{self.end_day.value:02d}")

    def observe(self, handler, names="value"):
        for w in (self.start_month, self.start_day, self.end_month, self.end_day):
            w.observe(handler, names)


def _tile_xyz(lon: float, lat: float, zoom: int) -> tuple[int, int, int]:
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return zoom, x, y


def _check_tile(layer: ipyleaflet.TileLayer, lon: float, lat: float, zoom: int = 12) -> None:
    """Fetches one tile over the study area; raises if Earth Engine can't serve it.
    (Catches failures that would otherwise only show up as a blank layer.)"""
    z, x, y = _tile_xyz(lon, lat, zoom)
    url = layer.url.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    urllib.request.urlopen(url, timeout=180).read()


class EarlyDetectionApp:
    def __init__(self, center=(44.834, -123.552), zoom=12, aoi_dir: Path = drawing.AOI_DIR):
        ee.data.setDeadline(REQUEST_DEADLINE_MS)
        self.aoi_dir = Path(aoi_dir)
        self.area: outputs.StudyArea | None = None
        self.run_state: dict | None = None
        self._build_area_step(center, zoom)
        self._build_settings_step()
        self._build_results()

    # ------------------------------------------------------------------ step 1: area
    def _build_area_step(self, center, zoom):
        self.drawer = drawing.AOIDrawer(center=center, zoom=zoom)
        self.area_source = W.ToggleButtons(options=["Drawn polygon", "Saved area", "Earth Engine asset"],
                                           description="Area from:", style={"description_width": "initial"})
        saved = sorted(p.stem for p in self.aoi_dir.glob("*.geojson")) if self.aoi_dir.exists() else []
        self.saved_area = W.Dropdown(options=saved or ["(none saved)"], description="Saved area:")
        self.asset_id = W.Combobox(placeholder="projects/<project>/assets/<feature_collection>",
                                   options=list(EXAMPLE_ASSETS.values()), description="Asset ID:",
                                   layout=W.Layout(width="520px"))
        self.save_name = W.Text(placeholder="optional name to save a drawn polygon", description="Save as:")
        self.allow_large = W.Checkbox(False, description="Allow areas over 1,000 km² (slow; may time out)",
                                      style={"description_width": "initial"})
        self.use_area_btn = W.Button(description="Use this area", button_style="info", icon="check")
        self.area_info = W.HTML()
        self.use_area_btn.on_click(self._use_area)

    def _use_area(self, _=None):
        try:
            src = self.area_source.value
            if src == "Drawn polygon":
                if self.drawer.ring is None:
                    raise ValueError("Draw a polygon or rectangle on the map first.")
                if self.save_name.value.strip():
                    drawing.save_polygon(self.save_name.value.strip(), self.drawer.ring, self.aoi_dir)
                name = self.save_name.value.strip() or "drawn_area"
                area = outputs.StudyArea(name, ee.Geometry.Polygon([self.drawer.ring]), {"aoi_coordinates": self.drawer.ring})
            elif src == "Saved area":
                area = drawing.study_area(self.saved_area.value, self.aoi_dir)
            else:
                if not self.asset_id.value.strip():
                    raise ValueError("Enter an Earth Engine FeatureCollection asset ID.")
                area = outputs.from_asset(self.asset_id.value.strip())
            size = outputs.aoi_size_report(area)
        except Exception as exc:  # show the problem, keep the app alive
            self.area_info.value = f"<b style='color:#b00'>Could not use this area:</b> {exc}"
            return
        km2 = size["area_km2"]
        if size["verdict"] == "large" and not self.allow_large.value:
            self.area = None
            self.area_info.value = (f"<b style='color:#b00'>{km2:,.0f} km² is over the 1,000 km² limit.</b> "
                                    "Use a smaller area, or tick 'Allow areas over 1,000 km²'.")
            return
        note = {"ok": "size is fine for a live run.",
                "slow": f"<b>larger than anything run live so far (~{outputs.TESTED_LIVE_KM2} km²)</b>; maps may be slow.",
                "large": "<b>very large</b>; live maps will very likely time out."}[size["verdict"]]
        self.area = area
        self.area_info.value = f"Using <b>{area.name}</b>: {km2:,.1f} km², {note}"
        w, s, e, n = size["bbox_degrees"]
        self.drawer.map.fit_bounds([[s, w], [n, e]])
        self.run_btn.disabled = not self.settings_ok

    # ------------------------------------------------------------------ step 2: settings
    def _build_settings_step(self):
        style = {"description_width": "170px"}
        wide = W.Layout(width="560px")
        self.expectation = W.IntRangeSlider(value=(2018, 2023), min=2016, max=2025, description="Expectation years:",
                                            style=style, layout=wide)
        self.monitoring_year = W.Dropdown(options=[2024, 2025, 2026], value=2026, description="Monitoring year:", style=style)
        self.window = SeasonWindow()
        d = LEGACY_DEFAULTS
        self.sensitivity = W.FloatSlider(value=d["sensitivity"], min=0.25, max=3.0, step=0.05, description="Sensitivity:",
                                         style=style, layout=wide)
        self.decrease_threshold = W.FloatSlider(value=d["decrease_threshold"], min=0.5, max=0.99, step=0.01,
                                                description="Decrease threshold:", style=style, layout=wide)
        self.increase_threshold = W.FloatSlider(value=d["increase_threshold"], min=0.5, max=0.99, step=0.01,
                                                description="Increase threshold:", style=style, layout=wide)
        self.timing = W.Checkbox(value=True, description="Also map the first-detected season", style={"description_width": "initial"})
        self.timing_confirmed = W.Checkbox(value=TIMING_CONFIRMED_DEFAULT,
                                           description="Detection timing: count only seasons that end as decrease (confirmed)",
                                           style={"description_width": "initial"})
        self.relationship = W.HTML()
        # advanced
        self.dampening = W.FloatSlider(value=d["dampening"], min=0.1, max=1.0, step=0.05, description="Dampening:",
                                       style=style, layout=wide)
        self.posterior = W.FloatSlider(value=d["posterior_leveler"], min=0.5, max=1.0, step=0.05,
                                       description="Posterior leveler:", style=style, layout=wide)
        self.fit_order = W.Dropdown(options=[(FIT_ORDER_LABELS[n], n) for n in FIT_ORDERS], value=d["fit_order"],
                                    description="Expectation fit order:", style=style, layout=W.Layout(width="480px"))
        self.sensors = {s: W.Checkbox(value=True, description=label) for s, label in
                        (("L8", "Landsat 8"), ("L9", "Landsat 9"), ("S2", "Sentinel-2"))}
        self.mask_forest = W.Checkbox(value=d["mask_forest"], description="Analyze forest only (Hansen tree cover ≥ 10%)",
                                      style={"description_width": "initial"})
        self.mask_water = W.Checkbox(value=d["mask_water"], description="Leave out water",
                                     style={"description_width": "initial"})
        self.advanced = W.Accordion(children=[W.VBox([
            W.HTML("<i>Normally left alone. Dampening, posterior leveler, the expectation fit order and the masks "
                   "start at the original BULC-D GUI's settings.</i>"),
            self.fit_order, W.HTML("&nbsp;&nbsp;shape of the expected seasonal curve; higher orders follow sharper "
                                   "seasonal transitions but need a long season to fit reliably"),
            self.dampening, W.HTML("&nbsp;&nbsp;how much weight each single observation carries (1 = full)"),
            self.posterior, W.HTML("&nbsp;&nbsp;pull toward even odds after each update (1 = off)"),
            W.HTML("<b>Monitoring sensors</b> (the expectation always uses Landsat 8)"), W.HBox(list(self.sensors.values())),
            self.mask_forest, self.mask_water, self.allow_large,
            self.timing_confirmed, W.HTML("&nbsp;&nbsp;for first detected season, last detection and detection episodes; "
                                          "unticked (raw), a crossing BULC-D later retracts also counts"),
        ])])
        self.advanced.set_title(0, "Advanced settings")
        self.advanced.selected_index = None
        for w in (self.expectation, self.monitoring_year, self.window, self.timing, self.fit_order, self.timing_confirmed):
            w.observe(lambda _: self._describe(), "value")
        self._describe()
        self.run_btn = W.Button(description="Run Early Detection", button_style="primary", icon="play", disabled=True,
                                layout=W.Layout(width="220px"))
        self._describe()
        self.run_btn.on_click(self._run)
        self.status = W.HTML()

    def _timing_years(self) -> list[int]:
        first = self.expectation.value[1] + 1
        years = list(range(first, self.monitoring_year.value + 1))
        return years[-MAX_TIMING_SEASONS:]

    def _describe(self):
        (e0, e1), m = self.expectation.value, self.monitoring_year.value
        start, end = self.window.value
        fmt = lambda md: datetime.date.fromisoformat(f"2025-{md}").strftime("%b %-d")
        problem = None
        if e1 >= m:
            problem = f"The expectation years must end before the monitoring year. Now: {e0}–{e1} vs {m}."
        elif start >= end:
            problem = (f"The season must start before it ends. Now: {fmt(start)} to {fmt(end)}. "
                       "(A window can't wrap past Dec 31; each year's window runs within that calendar year.)")
        self.settings_ok = problem is None
        if hasattr(self, "run_btn"):
            self.run_btn.disabled = not (self.settings_ok and self.area is not None)
        if problem:
            self.relationship.value = (f"<div style='padding:6px;border-left:4px solid #b00'><b>{problem}</b> "
                                       "Run is disabled until this is fixed.</div>")
            return
        timing = (f"<br><b>First detected season:</b> separate runs for {', '.join(map(str, self._timing_years()))}, "
                  "each judged against the same expectation and starting from the same odds (10% decrease, "
                  "80% unchanged, 10% increase). " +
                  ("A season counts only if it ends as decrease (confirmed)." if self.timing_confirmed.value else
                   "Any threshold crossing counts, even one BULC-D later retracts (raw).")
                  if self.timing.value else "")
        warning = MonitoringControls(monitoring_year=m, season_start=start, season_end=end, baseline_first_year=e0,
                                     baseline_last_year=e1, fit_order=self.fit_order.value).fit_order_warning
        warning = f"<br><b style='color:#b45f06'>Warning:</b> {warning}" if warning else ""
        self.relationship.value = (
            "<div style='padding:6px;border-left:4px solid #2a78d6'>"
            f"<b>Expectation ({e0}–{e1}, {fmt(start)}–{fmt(end)} each year)</b> defines what is <i>normal</i> for each pixel.<br>"
            f"<b>Monitoring ({fmt(start)}–{fmt(end)}, {m})</b> is what gets evaluated against that normal."
            f"{timing}{warning}</div>")

    def controls(self, monitoring_year: int | None = None) -> MonitoringControls:
        (e0, e1), (start, end) = self.expectation.value, self.window.value
        return MonitoringControls(monitoring_year=monitoring_year or self.monitoring_year.value, season_start=start,
                                  season_end=end, baseline_first_year=e0, baseline_last_year=e1,
                                  decision_threshold=round(self.decrease_threshold.value, 2),
                                  increase_threshold=round(self.increase_threshold.value, 2),
                                  sensitivity=round(self.sensitivity.value, 2), fit_order=self.fit_order.value)

    def build(self, controls, **aoi):
        """build_config() plus the advanced settings - the same shape as the notebooks' build()."""
        config = build_config(controls, **aoi)
        config.bulc_advanced_params.dampening_factor = round(self.dampening.value, 2)
        config.bulc_advanced_params.posterior_leveler = round(self.posterior.value, 2)
        config.bulc_advanced_params.initializing_leveler = INITIALIZING_LEVELER
        for code, box in self.sensors.items():
            if code in config.evidence.target.sensors:
                config.evidence.target.sensors[code].enabled = box.value
        config.study_area.mask_non_forest = self.mask_forest.value
        config.study_area.mask_water = self.mask_water.value
        return config

    # ------------------------------------------------------------------ step 3: results
    def _build_results(self):
        self.results_map = ipyleaflet.Map(center=self.drawer.map.center, zoom=self.drawer.map.zoom,
                                          basemap=ipyleaflet.basemaps.Esri.WorldImagery, scroll_wheel_zoom=True)
        self.results_map.layout.height = "560px"
        # A layers panel instead of Leaflet's layer control: in ipyleaflet a raster layer's
        # visible=False only sets opacity 0, so the Leaflet control could never reveal a
        # layer that started hidden. Checking a layer here adds it on top; unchecking removes it.
        self.layer_panel = W.VBox()
        self.layer_rows: dict[str, dict] = {}
        self.outline = None
        self.results_map.on_interaction(self._on_click)
        self.click_marker = ipyleaflet.CircleMarker(radius=8, color="#00e5ff", fill_opacity=0, weight=3)
        self.out = {k: W.Output() for k in ("Condition", "Timing", "Imagery", "Parameter behavior", "Pixel inspector")}
        # Coordinate entry: a map click fills these; Submit re-inspects exactly this coordinate, so a
        # rerun with other parameters can be compared at the same 30 m pixel. Text (not FloatText)
        # boxes keep the coordinate exactly as clicked or typed.
        self.pixel_lon = W.Text(description="Longitude", placeholder="e.g. -123.54330", layout=W.Layout(width="260px"))
        self.pixel_lat = W.Text(description="Latitude", placeholder="e.g. 44.84753", layout=W.Layout(width="260px"))
        self.pixel_btn = W.Button(description="Submit Pixel", icon="crosshairs", layout=W.Layout(width="140px"))
        self.pixel_btn.on_click(self._submit_pixel)
        tabs = dict(self.out)
        tabs["Pixel inspector"] = W.VBox([W.HBox([self.pixel_lon, self.pixel_lat, self.pixel_btn]), self.out["Pixel inspector"]])
        self.tabs = W.Tab(children=list(tabs.values()))
        for i, k in enumerate(self.out):
            self.tabs.set_title(i, k)
        with self.out["Pixel inspector"]:
            display(Markdown("After a run, **click any pixel on the results map**, or enter a longitude and latitude and "
                             "press **Submit Pixel**, to see its observations, departure from expectation, the "
                             "probabilities, the thresholds, and when they first crossed. A click fills the boxes, so "
                             "after changing parameters and rerunning, Submit Pixel inspects the same 30 m pixel again."))
        self.sens_btn = W.Button(description="Sensitivity maps (0.5 | 1.0 | 2.0)", icon="th", layout=W.Layout(width="280px"))
        self.resp_btn = W.Button(description="Response curves (4 parameters)", icon="line-chart", layout=W.Layout(width="280px"))
        self.sens_btn.on_click(self._sensitivity_maps)
        self.resp_btn.on_click(self._response_curves)

    def _clear_results_layers(self):
        for layer in list(self.results_map.layers):
            if not getattr(layer, "base", False):
                self.results_map.remove(layer)
        self.layer_rows = {}
        self.layer_panel.children = [W.HTML("<b>Map layers</b> (checked layers are drawn; the most recently checked is on top)")]

    def _keep_on_top(self):
        for layer in (self.outline, self.click_marker):
            if layer is not None and layer in self.results_map.layers:
                self.results_map.remove(layer)
                self.results_map.add(layer)

    def _toggle_layer(self, name: str, on: bool):
        layer = self.layer_rows[name]["layer"]
        if layer in self.results_map.layers:
            self.results_map.remove(layer)
        if on:
            self.results_map.add(layer)
            self._keep_on_top()

    def _add_result_layer(self, name: str, build_vis, on: bool = False, opacity: float = 1.0, note: str = ""):
        """Builds one Earth Engine layer, checks a tile over the study area, and adds a row to
        the layers panel. A failure is shown on its row instead of being skipped silently."""
        lon, lat = self.run_state["center"]
        try:
            layer = drawing.ee_tile_layer(build_vis(), name, opacity)
            _check_tile(layer, lon, lat)
        except Exception as exc:
            reason = str(exc).splitlines()[0][:200]
            self.layer_rows[name] = {"layer": None, "error": reason}
            self.layer_panel.children += (W.HTML(f"<span style='color:#b00'>✗ {name}: failed to load ({reason})</span>"),)
            return
        box = W.Checkbox(value=on, description=name, indent=False, layout=W.Layout(width="330px"))
        slider = W.FloatSlider(value=opacity, min=0, max=1, step=0.05, readout=False, layout=W.Layout(width="140px"))
        W.dlink((slider, "value"), (layer, "opacity"))   # python-side, so it also holds without a live browser
        box.observe(lambda ch, n=name: self._toggle_layer(n, ch["new"]), "value")
        self.layer_rows[name] = {"layer": layer, "error": None}
        self.layer_panel.children += (W.HBox([box, W.HTML("opacity"), slider, W.HTML(f"<i style='color:#666'>{note}</i>")]),)
        if on:
            self._toggle_layer(name, True)

    def _run(self, _=None):
        if self.area is None:
            self.status.value = "<b style='color:#b00'>Choose an area first (step 1).</b>"
            return
        try:
            controls = self.controls()
        except ValueError as exc:
            self.status.value = f"<b style='color:#b00'>Check the settings:</b> {exc}"
            return
        self.run_btn.disabled = True
        try:
            self._compute(controls)
        except Exception as exc:
            self.status.value = f"<b style='color:#b00'>Run failed:</b> {exc}"
        finally:
            self.run_btn.disabled = False

    def _compute(self, controls):
        area, geom = self.area, self.area.geometry
        self.status.value = "Setting up the run (condition map)…"
        config = self.build(controls, **area.aoi)
        condition = outputs.outcome_image(config, controls.decision_threshold, controls.increase_threshold).clip(geom)
        years = self._timing_years() if self.timing.value else []
        timing = episodes = None
        confirmed = self.timing_confirmed.value
        if years:
            # First-detected season, last detection and detection episodes: the decrease threshold.
            seasons = {y: outputs.detection_timing_image(self.build(self.controls(y), **area.aoi), controls.decision_threshold,
                                                         controls.increase_threshold, episodes=True)
                       for y in years}
            timing = outputs.combine_season_timing(seasons, confirmed=confirmed).clip(geom)
            episodes = outputs.combine_episode_metrics(seasons, confirmed=confirmed).clip(geom)
        img_years = [controls.monitoring_year - 2, controls.monitoring_year - 1, controls.monitoring_year]
        window = (controls.season_start, controls.season_end)
        self.run_state = {"controls": controls, "config": config, "condition": condition, "timing": timing,
                          "episodes": episodes, "timing_confirmed": confirmed,
                          "timing_years": years, "img_years": img_years, "window": window}

        # --- map layers (drawn lazily by Earth Engine as you pan/zoom); each is checked independently
        self._clear_results_layers()
        w, s_, e, n = outputs.aoi_size_report(area)["bbox_degrees"]
        self.run_state["center"] = ((w + e) / 2, (s_ + n) / 2)
        self.results_map.fit_bounds([[s_, w], [n, e]])
        self.outline = ipyleaflet.GeoJSON(data=geom.getInfo(), name="Study area",
                                          style={"color": "#ffd400", "weight": 2, "fillOpacity": 0})
        self.results_map.add(self.outline)
        self.status.value = "Preparing map layers…"
        large = outputs.aoi_size_report(area)["area_km2"] > outputs.TESTED_LIVE_KM2
        low = high = None
        for y in img_years:
            self._add_result_layer(f"True color {y}", lambda y=y: outputs.annual_true_color(geom, y, window).clip(geom)
                                   .visualize(**render.TRUE_COLOR), note="reference imagery")
        def nbr_vis():
            nonlocal low, high
            nbrs = [outputs.annual_nbr(geom, y, window, reproject=not large) for y in img_years]
            land = [n_.updateMask(render._not_water()) for n_ in nbrs]
            low, high = outputs.nbr_stretch(land, geom, scale=120 if large else outputs.SCALE)
            return ee.Image.cat(land).clip(geom).visualize(min=[low] * 3, max=[high] * 3)
        self.status.value = "Preparing the NBR composite…"
        self._add_result_layer(f"NBR composite R={img_years[0]} G={img_years[1]} B={img_years[2]}", nbr_vis,
                               note="spectral timing clues")
        if timing is not None:
            self._add_result_layer("First detected season (decrease)", lambda: timing.select("first_decrease_year").visualize(
                min=years[0], max=years[-1], palette=[c[1:] for c in render.YEAR_COLORS[:len(years)]]),
                note="see Timing tab for the legend")
            self._add_result_layer("Last detection (decrease)", lambda: render.last_detection_image(
                episodes, years, controls.first_doy, controls.last_doy).visualize(**render.last_detection_vis(years)),
                note="see Timing tab for the legend")
            self._add_result_layer("Detection episodes (decrease)", lambda: render.episodes_image(episodes).visualize(
                **render.episodes_vis()), note="see Timing tab for the legend")
        outcome = condition.select("outcome")
        self.status.value = "Preparing the condition layer…"
        self._add_result_layer(f"Condition {controls.monitoring_year}", lambda: outcome.updateMask(outcome.lte(outputs.INCREASE)).visualize(
            min=0, max=2, palette=[render.OUTCOME_COLORS[k][1:] for k in (outputs.DECREASE, outputs.UNCHANGED, outputs.INCREASE)]),
            on=True, opacity=0.85, note="see Condition tab for the legend")

        # --- tabs
        token = render.auth_token()
        frame, bbox = report.frame_for(geom, pad_m=150)
        for k in ("Condition", "Timing", "Imagery", "Parameter behavior"):
            self.out[k].clear_output()
        self.status.value = "Summarizing the condition map (the first full computation; can take a minute)…"
        with self.out["Condition"]:
            display(Markdown(f"**{controls.monitoring_year} condition relative to expectation** "
                             f"(expectation {controls.baseline_first_year}–{controls.baseline_last_year}). "
                             "Decrease means below its expected condition during the monitoring season, "
                             "not necessarily that the disturbance happened then."))
            display(Markdown(report.area_table(condition, geom)[0]))
            display(W.HTML(render_legend(render.outcome_legend())))
        with self.out["Timing"]:
            if timing is None:
                display(Markdown("First-detected season not requested, or no season falls between the expectation years "
                                 "and the monitoring year."))
            else:
                self.status.value = "Summarizing first-detected seasons…"
                rule = ("that BULC-D finished classified as decrease (a crossing it later retracted doesn't count; "
                        "confirmed)" if confirmed else
                        "in which P(decrease) crossed the threshold at all, even if BULC-D later retracted it (raw)")
                display(Markdown(f"**First detected season**: the earliest of {', '.join(map(str, years))} {rule}; the date is "
                                 "the first crossing within that season. Each season is a separate run against the same "
                                 "expectation, starting from the same odds (10% decrease, 80% unchanged, 10% increase). It shows detection timing, not a verified disturbance "
                                 f"date; the first season ({years[0]}) also gathers everything already different by then. "
                                 "Turn the layer on in the Map layers panel."))
                display(Markdown(report.detection_year_table(timing, geom, years)))
                display(W.HTML(render_legend(render.detection_year_legend(years))))
                fmt = lambda doy: (datetime.date(2025, 1, 1) + datetime.timedelta(days=doy - 1)).strftime("%b %-d")
                display(Markdown("**Last detection** (layer *Last detection (decrease)*): in that same season, the start of "
                                 "the most recent period with P(decrease) above the threshold. " +
                                 ("Because the season ends as decrease, that period lasted to the end of the season. "
                                  if confirmed else "") +
                                 "Where BULC-D first flagged a pixel and later retracted it (for example a spring snowmelt "
                                 "false detection before a fall fire), last detection gives the later date."))
                display(W.HTML(render_legend(render.last_detection_legend(years, fmt(controls.first_doy),
                                                                          fmt(controls.last_doy)))))
                display(Markdown("**Detection episodes** (layer *Detection episodes (decrease)*): in that season, how many "
                                 "separate times P(decrease) rose above the threshold. An episode ends when it falls back to "
                                 "or below the threshold; no smoothing or minimum length, so a probability hovering near the "
                                 "threshold counts every crossing."))
                display(Markdown(report.episode_table(episodes, geom)))
                display(W.HTML(render_legend(render.episodes_legend())))
        with self.out["Imagery"]:
            self.status.value = "Drawing annual true color…"
            display(Markdown("Reference imagery, independent of BULC-D. The true-color and NBR-composite layers can also "
                             "be turned on in the Map layers panel above the results map."))
            report.annual_true_color_row(area, frame, bbox, token, img_years, window,
                                         suptitle="True color: clear-sky median, same window and stretch each year")
            stretch = f"one stretch {low:.2f}–{high:.2f}" if low is not None else "layer failed to load"
            display(Markdown(f"**NBR composite** (R = {img_years[0]}, G = {img_years[1]}, B = {img_years[2]}; "
                             f"{stretch}): colors are spectral timing clues, not confirmed disturbance dates."))
            display(W.HTML(render_legend(render.nbr_rgb_legend(img_years))))
        with self.out["Parameter behavior"]:
            display(Markdown("Optional, and slower: each runs BULC-D several times on the whole area. Only one "
                             "parameter changes at a time; everything else stays as set above."))
            display(W.HBox([self.sens_btn, self.resp_btn]))
        loaded = [k for k, v in self.layer_rows.items() if v["error"] is None]
        failed = {k: v["error"] for k, v in self.layer_rows.items() if v["error"] is not None}
        layers_msg = (f"Map layers: all {len(loaded)} loaded." if not failed else
                      f"<b style='color:#b00'>Map layers: {len(loaded)} of {len(self.layer_rows)} loaded.</b> "
                      + "; ".join(f"{k}: failed to load ({v})" for k, v in failed.items()))
        self.status.value = ("<b>Analysis complete.</b> " + layers_msg +
                             " Turn layers on in the Map layers panel; click any pixel to inspect it.")
        self.tabs.selected_index = 0

    # ------------------------------------------------------------------ parameter behavior (on demand)
    def _sensitivity_maps(self, _=None):
        if not self.run_state:
            return
        c = self.run_state["controls"]
        variants = [compare.Variant(f"Sensitivity {v}", "", controls={"sensitivity": v}) for v in (0.5, 1.0, 2.0)]
        with self.out["Parameter behavior"]:
            self.status.value = "Running three sensitivity maps…"
            effects = compare.run_comparison(self.area, c, self.build, variants)
            compare.show_comparison(effects, f"{self.area.name}: only sensitivity changes")
            self.status.value = "<b>Done.</b>"

    def _response_curves(self, _=None):
        if not self.run_state:
            return
        with self.out["Parameter behavior"]:
            self.status.value = "Running the parameter response curves (about 16 BULC-D runs)…"
            rows = compare.parameter_response(self.area, self.run_state["controls"], self.build, APP_PARAMETER_SWEEPS)
            compare.plot_parameter_response(rows, f"{self.area.name}: detected area as one parameter moves",
                                            APP_PARAMETER_SWEEPS)
            self.status.value = "<b>Done.</b>"

    # ------------------------------------------------------------------ pixel inspector
    def _on_click(self, **event):
        if event.get("type") != "click" or not self.run_state:
            return
        lat, lon = event["coordinates"]
        self._inspect_safely(lon, lat)

    def _submit_pixel(self, _=None):
        try:
            lon, lat = float(self.pixel_lon.value), float(self.pixel_lat.value)
        except ValueError:
            self.status.value = "<b style='color:#b00'>Enter a numeric longitude and latitude (decimal degrees).</b>"
            return
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            self.status.value = "<b style='color:#b00'>Longitude must be within ±180 and latitude within ±90.</b>"
            return
        if not self.run_state:
            self.status.value = "<b style='color:#b00'>Run the analysis first, then submit a pixel.</b>"
            return
        self._inspect_safely(lon, lat)

    def _inspect_safely(self, lon: float, lat: float):
        try:
            self.inspect(lon, lat)
        except Exception as exc:  # e.g. an Earth Engine timeout: report it, keep the app usable
            self.status.value = f"<b style='color:#b00'>Pixel history failed:</b> {exc}. Try again or another pixel."

    def inspect(self, lon: float, lat: float):
        """Pixel history at (lon, lat) - the click handler; callable directly."""
        state = self.run_state
        self.pixel_lon.value, self.pixel_lat.value = repr(lon), repr(lat)
        self.click_marker.location = (lat, lon)
        if self.click_marker not in self.results_map.layers:
            self.results_map.add(self.click_marker)
        seasons = state["timing_years"] or [state["controls"].monitoring_year]
        out = self.out["Pixel inspector"]
        out.clear_output()
        self.tabs.selected_index = list(self.out).index("Pixel inspector")
        self.status.value = f"Loading the pixel history at {lat:.5f}, {lon:.5f} ({len(seasons)} season(s); ~20 s each)…"
        histories = {}
        with out:
            for y in seasons:
                histories[f"{y} season"] = pixel.pixel_history(self.build(self.controls(y), **self.area.aoi), lon, lat)
            if not any(r["zscore"] is not None for rows in histories.values() for r in rows):
                display(Markdown("No clear observations here: outside the study area, masked (water or non-forest), "
                                 "or always cloudy. Try another pixel."))
            else:
                c = state["controls"]
                pixel.plot_pixel_history(histories, c.decision_threshold, classes=pixel.CLASSES,
                                         increase_threshold=c.increase_threshold,
                                         title=f"Pixel at {lat:.5f} N, {abs(lon):.5f} {'W' if lon < 0 else 'E'}")
                print(f"Coordinate: {lon!r}, {lat!r} (lon, lat); sampled on the 30 m result grid")
                print(f"Expectation fit order {c.fit_order}: {FIT_ORDER_LABELS[c.fit_order].split(': ', 1)[1]}")
                if c.fit_order_warning:
                    print(f"Warning: {c.fit_order_warning}")
                for label, rows in histories.items():
                    for note in pixel.crossing_notes(rows, c.decision_threshold, c.increase_threshold):
                        print(f"{label}: {note}")
                    for note in pixel.episode_notes(rows, c.decision_threshold):
                        print(f"{label}: {note}")
        self.status.value = "<b>Done.</b> Click another pixel to compare."
        return histories

    # ------------------------------------------------------------------ layout
    def show(self):
        step1 = W.VBox([W.HTML("<h3>1. Choose an area</h3>Draw a polygon or rectangle (left toolbar), pick a saved "
                               "area, or enter an Earth Engine FeatureCollection asset ID. Then press <b>Use this area</b>."),
                        self.drawer.map, self.area_source, W.HBox([self.save_name, self.saved_area]), self.asset_id,
                        self.use_area_btn, self.area_info])
        step2 = W.VBox([W.HTML("<h3>2. Expectation and monitoring</h3>"), self.expectation, self.monitoring_year,
                        self.window.widget, self.relationship, self.sensitivity,
                        W.HTML("&nbsp;&nbsp;higher flags smaller departures from normal"),
                        self.decrease_threshold, self.increase_threshold,
                        W.HTML("&nbsp;&nbsp;how sure BULC-D must be before flagging each kind of change"), self.timing, self.advanced])
        step3 = W.VBox([W.HTML("<h3>3. Run and inspect</h3>"), self.run_btn, self.status, self.layer_panel,
                        self.results_map, self.tabs])
        display(W.VBox([step1, step2, step3]))


def render_legend(items: dict[str, str]) -> str:
    """Small HTML legend (label -> color) for widget panels."""
    rows = "".join(f"<div><span style='display:inline-block;width:14px;height:14px;background:{c};"
                   f"border:1px solid #999;margin-right:6px;vertical-align:middle'></span>{label}</div>"
                   for label, c in items.items())
    return f"<div style='font-size:12px;line-height:1.7'>{rows}</div>"

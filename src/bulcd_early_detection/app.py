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
from pathlib import Path

import ee
import ipyleaflet
import ipywidgets as W
from IPython.display import Markdown, display

from . import compare, drawing, outputs, pixel, render, report
from .config import MonitoringControls, build_config

# Earth Engine requests have no deadline by default, so one stalled request can
# freeze the whole app; fail it after this long instead (ms).
REQUEST_DEADLINE_MS = 300_000
EXAMPLE_ASSETS = {"testsite (western Oregon, 26 km²)": "projects/bulcd-python-rebuild/assets/testsite"}
MAX_TIMING_SEASONS = 3


def _season_options() -> list[tuple[str, str]]:
    """Weekly MM-DD choices from April through October."""
    day, out = datetime.date(2025, 4, 1), []
    while day <= datetime.date(2025, 10, 31):
        out.append((f"{day:%b %-d}", f"{day:%m-%d}"))
        day += datetime.timedelta(days=7)
    for label, value in (("Jun 1", "06-01"), ("Sep 30", "09-30")):
        if (label, value) not in out:
            out.append((label, value))
    return sorted(out, key=lambda o: o[1])


def _tile(vis: ee.Image, name: str, visible: bool = True, opacity: float = 1.0) -> ipyleaflet.TileLayer:
    layer = drawing.ee_tile_layer(vis, name, opacity)
    layer.visible = visible
    return layer


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
        self.run_btn.disabled = False

    # ------------------------------------------------------------------ step 2: settings
    def _build_settings_step(self):
        style = {"description_width": "170px"}
        wide = W.Layout(width="560px")
        self.expectation = W.IntRangeSlider(value=(2018, 2023), min=2016, max=2025, description="Expectation years:",
                                            style=style, layout=wide)
        self.monitoring_year = W.Dropdown(options=[2024, 2025, 2026], value=2026, description="Monitoring year:", style=style)
        opts = _season_options()
        self.window = W.SelectionRangeSlider(options=opts, index=(opts.index(("Jun 1", "06-01")), opts.index(("Sep 30", "09-30"))),
                                             description="Seasonal window:", style=style, layout=wide)
        self.sensitivity = W.FloatSlider(value=1.0, min=0.25, max=3.0, step=0.05, description="Sensitivity:", style=style, layout=wide)
        self.threshold = W.FloatSlider(value=0.5, min=0.5, max=0.99, step=0.01, description="Decision threshold:", style=style, layout=wide)
        self.timing = W.Checkbox(value=True, description="Also map the first-detected season", style={"description_width": "initial"})
        self.relationship = W.HTML()
        # advanced
        self.dampening = W.FloatSlider(value=0.5, min=0.1, max=1.0, step=0.05, description="Dampening:", style=style, layout=wide)
        self.posterior = W.FloatSlider(value=1.0, min=0.5, max=1.0, step=0.05, description="Posterior leveler:", style=style, layout=wide)
        self.sensors = {s: W.Checkbox(value=True, description=label) for s, label in
                        (("L8", "Landsat 8"), ("L9", "Landsat 9"), ("S2", "Sentinel-2"))}
        self.mask_forest = W.Checkbox(value=True, description="Analyze forest only (Hansen tree cover ≥ 10%)",
                                      style={"description_width": "initial"})
        self.mask_water = W.Checkbox(value=True, description="Leave out water", style={"description_width": "initial"})
        self.advanced = W.Accordion(children=[W.VBox([
            W.HTML("<i>Normally left alone. Defaults match the demonstration notebooks.</i>"),
            self.dampening, W.HTML("&nbsp;&nbsp;how much weight each single observation carries (1 = full)"),
            self.posterior, W.HTML("&nbsp;&nbsp;pull toward even odds after each update (1 = off)"),
            W.HTML("<b>Monitoring sensors</b> (the expectation always uses Landsat 8)"), W.HBox(list(self.sensors.values())),
            self.mask_forest, self.mask_water, self.allow_large,
        ])])
        self.advanced.set_title(0, "Advanced settings")
        self.advanced.selected_index = None
        for w in (self.expectation, self.monitoring_year, self.window, self.timing):
            w.observe(lambda _: self._describe(), "value")
        self._describe()
        self.run_btn = W.Button(description="Run Early Detection", button_style="primary", icon="play", disabled=True,
                                layout=W.Layout(width="220px"))
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
        if e1 >= m:
            self.relationship.value = (f"<div style='padding:6px;border-left:4px solid #b00'><b>The expectation years must end "
                                       f"before the monitoring year.</b> Now: {e0}–{e1} vs {m}.</div>")
            return
        timing = (f"<br><b>First detected season:</b> separate runs for {', '.join(map(str, self._timing_years()))}, "
                  "each judged against the same expectation and starting from even odds."
                  if self.timing.value else "")
        self.relationship.value = (
            "<div style='padding:6px;border-left:4px solid #2a78d6'>"
            f"<b>Expectation ({e0}–{e1}, {fmt(start)}–{fmt(end)} each year)</b> defines what is <i>normal</i> for each pixel.<br>"
            f"<b>Monitoring ({fmt(start)}–{fmt(end)}, {m})</b> is what gets evaluated against that normal."
            f"{timing}</div>")

    def controls(self, monitoring_year: int | None = None) -> MonitoringControls:
        (e0, e1), (start, end) = self.expectation.value, self.window.value
        return MonitoringControls(monitoring_year=monitoring_year or self.monitoring_year.value, season_start=start,
                                  season_end=end, baseline_first_year=e0, baseline_last_year=e1,
                                  decision_threshold=round(self.threshold.value, 2), sensitivity=round(self.sensitivity.value, 2))

    def build(self, controls, **aoi):
        """build_config() plus the advanced settings - the same shape as the notebooks' build()."""
        config = build_config(controls, **aoi)
        config.bulc_advanced_params.dampening_factor = round(self.dampening.value, 2)
        config.bulc_advanced_params.posterior_leveler = round(self.posterior.value, 2)
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
        self.results_map.add(ipyleaflet.LayersControl(position="topright"))
        self.results_map.on_interaction(self._on_click)
        self.click_marker = ipyleaflet.CircleMarker(radius=8, color="#00e5ff", fill_opacity=0, weight=3)
        self.out = {k: W.Output() for k in ("Condition", "Timing", "Imagery", "Parameter behavior", "Pixel inspector")}
        self.tabs = W.Tab(children=list(self.out.values()))
        for i, k in enumerate(self.out):
            self.tabs.set_title(i, k)
        with self.out["Pixel inspector"]:
            display(Markdown("After a run, **click any pixel on the results map** to see its observations, departure from "
                             "expectation, probability of decrease, the threshold, and when it first crossed."))
        self.sens_btn = W.Button(description="Sensitivity maps (0.5 | 1.0 | 2.0)", icon="th", layout=W.Layout(width="280px"))
        self.resp_btn = W.Button(description="Response curves (4 parameters)", icon="line-chart", layout=W.Layout(width="280px"))
        self.sens_btn.on_click(self._sensitivity_maps)
        self.resp_btn.on_click(self._response_curves)

    def _clear_results_layers(self):
        for layer in list(self.results_map.layers):
            if isinstance(layer, ipyleaflet.TileLayer) and layer.name not in ("Esri.WorldImagery",) and layer.base is False:
                self.results_map.remove(layer)
            if isinstance(layer, (ipyleaflet.GeoJSON, ipyleaflet.CircleMarker)):
                self.results_map.remove(layer)

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
        condition = outputs.outcome_image(config, controls.decision_threshold).clip(geom)
        years = self._timing_years() if self.timing.value else []
        timing = None
        if years:
            seasons = {y: outputs.detection_timing_image(self.build(self.controls(y), **area.aoi), controls.decision_threshold)
                       for y in years}
            timing = outputs.combine_season_timing(seasons).clip(geom)
        img_years = [controls.monitoring_year - 2, controls.monitoring_year - 1, controls.monitoring_year]
        window = (controls.season_start, controls.season_end)
        self.run_state = {"controls": controls, "config": config, "condition": condition, "timing": timing,
                          "timing_years": years, "img_years": img_years, "window": window}

        # --- map layers (drawn lazily by Earth Engine as you pan/zoom)
        self._clear_results_layers()
        w, s, e, n = outputs.aoi_size_report(area)["bbox_degrees"]
        self.results_map.fit_bounds([[s, w], [n, e]])
        self.results_map.add(ipyleaflet.GeoJSON(data=geom.getInfo(), name="Study area",
                                                style={"color": "#ffd400", "weight": 2, "fillOpacity": 0}))
        for y in img_years:
            tc = outputs.annual_true_color(geom, y, window).clip(geom).visualize(**render.TRUE_COLOR)
            self.results_map.add(_tile(tc, f"True color {y}", visible=False))
        large = outputs.aoi_size_report(area)["area_km2"] > outputs.TESTED_LIVE_KM2
        nbrs = [outputs.annual_nbr(geom, y, window, reproject=not large) for y in img_years]
        self.status.value = "Computing the NBR composite stretch…"
        land = [n_.updateMask(render._not_water()) for n_ in nbrs]
        low, high = outputs.nbr_stretch(land, geom, scale=120 if large else outputs.SCALE)
        nbr_vis = ee.Image.cat(land).clip(geom).visualize(min=[low] * 3, max=[high] * 3)
        self.results_map.add(_tile(nbr_vis, f"NBR composite R={img_years[0]} G={img_years[1]} B={img_years[2]}", visible=False))
        if timing is not None:
            yv = timing.select("first_decrease_year").visualize(min=years[0], max=years[-1],
                                                                palette=[c[1:] for c in render.YEAR_COLORS[:len(years)]])
            self.results_map.add(_tile(yv, "First detected season (decrease)", visible=False))
        outcome = condition.select("outcome")
        cv = outcome.updateMask(outcome.lte(outputs.INCREASE)).visualize(
            min=0, max=2, palette=[render.OUTCOME_COLORS[k][1:] for k in (outputs.DECREASE, outputs.UNCHANGED, outputs.INCREASE)])
        self.results_map.add(_tile(cv, f"Condition {controls.monitoring_year}", opacity=0.85))

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
                display(Markdown(f"**First detected season**: the earliest of {', '.join(map(str, years))} in which "
                                 "BULC-D's probability of decrease crossed the threshold. Each season is a separate run "
                                 "against the same expectation, starting from even odds. It shows detection timing, not a "
                                 f"verified disturbance date; the first season ({years[0]}) also gathers everything that "
                                 "was already different by then. Turn on the layer in the map's layer control."))
                display(Markdown(report.detection_year_table(timing, geom, years)))
                display(W.HTML(render_legend(render.detection_year_legend(years))))
        with self.out["Imagery"]:
            self.status.value = "Drawing annual true color…"
            display(Markdown("Reference imagery, independent of BULC-D. The true-color and NBR-composite layers can also "
                             "be switched on in the map's layer control, over the condition map."))
            report.annual_true_color_row(area, frame, bbox, token, img_years, window,
                                         suptitle="True color: clear-sky median, same window and stretch each year")
            display(Markdown(f"**NBR composite** (R = {img_years[0]}, G = {img_years[1]}, B = {img_years[2]}; "
                             f"one stretch {low:.2f}–{high:.2f}): colors are spectral timing clues, not confirmed "
                             "disturbance dates."))
            display(W.HTML(render_legend(render.nbr_rgb_legend(img_years))))
        with self.out["Parameter behavior"]:
            display(Markdown("Optional, and slower: each runs BULC-D several times on the whole area. Only one "
                             "parameter changes at a time; everything else stays as set above."))
            display(W.HBox([self.sens_btn, self.resp_btn]))
        self.status.value = ("<b>Done.</b> Switch layers with the control at the top right of the results map, and "
                             "click any pixel to inspect it.")
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
            rows = compare.parameter_response(self.area, self.run_state["controls"], self.build)
            compare.plot_parameter_response(rows, f"{self.area.name}: detected area as one parameter moves")
            self.status.value = "<b>Done.</b>"

    # ------------------------------------------------------------------ pixel inspector
    def _on_click(self, **event):
        if event.get("type") != "click" or not self.run_state:
            return
        lat, lon = event["coordinates"]
        try:
            self.inspect(lon, lat)
        except Exception as exc:  # e.g. an Earth Engine timeout: report it, keep the app usable
            self.status.value = f"<b style='color:#b00'>Pixel history failed:</b> {exc}. Try again or another pixel."

    def inspect(self, lon: float, lat: float):
        """Pixel history at (lon, lat) - the click handler; callable directly."""
        state = self.run_state
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
                pixel.plot_pixel_history(histories, state["controls"].decision_threshold,
                                         title=f"Pixel at {lat:.5f} N, {abs(lon):.5f} {'W' if lon < 0 else 'E'}")
                for label, rows in histories.items():
                    crossed = pixel.first_crossing(rows, state["controls"].decision_threshold)
                    print(f"{label}: " + (f"first crossed the threshold on {crossed}" if crossed else "never crossed the threshold"))
        self.status.value = "<b>Done.</b> Click another pixel to compare."
        return histories

    # ------------------------------------------------------------------ layout
    def show(self):
        step1 = W.VBox([W.HTML("<h3>1. Choose an area</h3>Draw a polygon or rectangle (left toolbar), pick a saved "
                               "area, or enter an Earth Engine FeatureCollection asset ID. Then press <b>Use this area</b>."),
                        self.drawer.map, self.area_source, W.HBox([self.save_name, self.saved_area]), self.asset_id,
                        self.use_area_btn, self.area_info])
        step2 = W.VBox([W.HTML("<h3>2. Expectation and monitoring</h3>"), self.expectation, self.monitoring_year,
                        self.window, self.relationship, self.sensitivity,
                        W.HTML("&nbsp;&nbsp;higher flags smaller departures from normal"), self.threshold,
                        W.HTML("&nbsp;&nbsp;how sure BULC-D must be before flagging"), self.timing, self.advanced])
        step3 = W.VBox([W.HTML("<h3>3. Run and inspect</h3>"), self.run_btn, self.status, self.results_map, self.tabs])
        display(W.VBox([step1, step2, step3]))


def render_legend(items: dict[str, str]) -> str:
    """Small HTML legend (label -> color) for widget panels."""
    rows = "".join(f"<div><span style='display:inline-block;width:14px;height:14px;background:{c};"
                   f"border:1px solid #999;margin-right:6px;vertical-align:middle'></span>{label}</div>"
                   for label, c in items.items())
    return f"<div style='font-size:12px;line-height:1.7'>{rows}</div>"

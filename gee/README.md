# gee/ — Earth Engine Code Editor app

A GEE JavaScript version of the Early Detection interface. The interactive notebook's
app (`src/bulcd_early_detection/app.py`) is the UI/functionality reference, and the
validated Python `bulcd` is the algorithm reference. Nothing here is derived from the
legacy GUI's code.

BULC-D itself runs in `BULC-D_rebuild/gee/bulcd.js`, a port of the Python `bulcd`
package held to JS ↔ Python parity there (`gee/tests/run_parity.py`). Per this repo's
rule, no algorithm code is copied here: these modules only build configs and interpret
outputs.

| File | Role | Python counterpart |
|---|---|---|
| `config.js` | Settings → bulcd config, notebook defaults and limits | `config.build_config()` + `app.EarlyDetectionApp.build()` |
| `controls.js` | Settings panel (widgets) | `app.py _build_settings_step()` |
| `aoi.js` | Area size check and limits | `outputs.aoi_size_report()`, `app.py _use_area()` |
| `outputs.js` | Condition, first-detected season, last detection, detection episodes, true color, NBR composite | `outputs._outcome_from_result()`, `detection_timing_image()`, `combine_season_timing()`, `combine_episode_metrics()`, `annual_true_color()`, `annual_nbr()`, `nbr_stretch()`; `render` colors |
| `inspector.js` | Pixel history rows, the expectation fit at the pixel, the charts | `pixel.pixel_history()`, `plot_pixel_history()` |
| `app.js` | Code Editor UI: area, settings, run, layers, legend, inspector | `app.py` |

## What the app does

The app is for investigating Early Detection, not for validation: reference cases,
reference pixels and other test fixtures live only in `tests/` (`tests/reference_case.js`)
and are never deployed. Workflow: choose or draw an area → choose parameters → **Run
Early Detection** → explore the result and reference layers → click or enter a pixel →
inspect its NBR/fit and probability history.

1. **Area.** A polygon or rectangle drawn with the map's drawing tools (the default; only
   the latest shape is used), or an Earth Engine FeatureCollection asset. Same size rule
   as the notebook: over 100 km² warns, over 1,000 km² is blocked unless allowed under
   Advanced settings.
2. **Settings,** with the notebook's limits. A description states the periods in
   words and blocks invalid settings. Defaults (`config.js` `APP_DEFAULTS`; the Python
   app's `LEGACY_DEFAULTS` are the same):
   - **From the original BULC-D GUI's defaults** (read from its source; checked in
     `tests/controls_check.js` against `tests/legacy_gui.js`, and for the Python app in
     `tests/test_app_defaults.py`): sensitivity 1.0, decrease threshold 0.65 and
     increase threshold 0.75 (its drop/gain sliders), dampening 0.7 (`transitionLeveler`), posterior leveler 0.9, starting odds 0.10
     decrease / 0.80 unchanged / 0.10 increase (`initializingLeveler` 0.7; fixed, not a
     control), forest-only mask off, water mask on, expectation fit order 1 (its
     modality: constant + unimodal). Also fixed as in the original: the evidence table,
     bin cuts, z-score denominator 0.05, NBR.
   - **Expectation fit order** (Advanced settings; 1, 2 or 3): order N fits a constant
     plus the first N annual harmonics (1, 2 and 3 cycles per year). These are the
     original GUI's cumulative modality flags `unimodal`, `bimodal` and `trimodal`, run
     unchanged by bulcd. Every output uses it: condition, first-detected season, and the
     inspector's expectation fit and probabilities. The settings description warns
     (without blocking the run) when the season is shorter than 183 days at order 2, or
     245 days at order 3, because the fit can be unstable there. The inspector's run
     line and fit summary name the order. With more than one harmonic, the summary gives
     each harmonic's amplitude and the fitted curve's actual range over the season.
     Order 3 uses exactly 3 cycles per year, where legacy used 2.9985. That is a tiny
     known difference (`docs/findings.md`, 2026-10-13).
   - **Early Detection choices** (the original GUI had no default; the user typed or
     ticked them): expectation years 2018–2023, monitoring year 2026, season Jun 1–Sep
     30, monitoring sensors L8, L9, S2 (the expectation is always Landsat 8; the
     original GUI used one sensor selection for both periods), cloud cover 70.
   - **Different from the original:** day step 4 (the original slider starts at 3; it
     was set to 4 for the same-pixel comparison).

   The two thresholds, as in the original GUI: the condition layer is decrease where
   the final P(decrease) is above the decrease threshold and increase where P(increase)
   is above the increase threshold (strictly above, like its `.gt()`), else unchanged.
   The first-detected season uses the decrease threshold. The inspector's probability
   chart draws both thresholds, and its notes give each class's crossing against its
   own threshold.
   - Also: first-detected season (on), allow large areas (off), detection timing
     confirmed (Advanced settings; untick for raw).
3. **Run Early Detection** recomputes for the chosen area. Layers, bottom to top, in
   the map's Layers control: true color for the monitoring year and the two before;
   the NBR composite (R/G/B = those years, one stretch, water masked); first detected
   season (decrease; separate runs for up to three seasons, confirmed definition by
   default); last detection (in that same season, the start of the most recent period
   with P(decrease) above the decrease threshold; colored by its position in the
   seasons); detection episodes (how many separate times P(decrease) rose above the
   threshold in that season: 1, 2, 3+; no smoothing);
   **condition** (the primary layer, on at 0.85 opacity); the study-area outline.
4. **Pixel inspector.** Click the map or type a longitude/latitude and press **Submit
   Pixel**. "Expectation -> Monitoring" (the expectation-period observations the fit
   used, the fitted curve through both periods, and the monitoring observations) with
   a summary of the fit at the pixel, then "Target Year vs. Fit" and "Probability
   Through Time", all sampled on the 30 m result grid, probabilities at each observation's
   own date. Its notes list the monitoring season's detection episodes,
   with first and last detection. A run keeps the coordinate boxes, so Submit Pixel inspects the same pixel
   under new settings; the inspector names the settings of the run it shows.

Not ported yet (in the notebook): saved local areas (the Code Editor can't read local
files), the Condition/Timing/Imagery summary tabs, the Parameter behavior tab, and the
inspector's one-column-per-season view.

## Running it in the Code Editor

Git is the source of truth; the Code Editor holds generated copies. Two Code Editor
repositories, mirroring the two git repos:

```
users/<user>/BULC-D_rebuild           bulcd
users/<user>/bulcd-early-detection    app  config  outputs  inspector
```

`python tools/build_gee_deploy.py <user>` writes the five files to `dist/gee/` (not
tracked) with `app`'s module paths set for `<user>` and a header naming each file's
source commit.

**Code Editor requirement: `require()` paths must be string literals.** The Code
Editor only loads modules it finds as literal `require('users/…:…')` calls in a
script's source. A path held in a variable or built at run time, e.g.
`require(BULCD_MODULE)` or `require(root + 'config')`, fails with "Module not found
at <path>", even when the path is correct and the module exists. Found 2026-10-09:
all such calls failed (including a public module), while the same paths written as
literals loaded. So `app.js` writes each path in full, with `OWNER` as the placeholder
username (`require('users/OWNER/bulcd-early-detection:config')`), and the generator
substitutes the username. The generator also refuses to write output where any
`require()` lacks a literal path, or names a file it didn't generate. Keep any new
module imports in this form. Paste each into the matching Code Editor file and run `app`. After any
change in git, re-run the script and re-paste. The whole case is computed on the fly,
as in the legacy GUI, so map tiles take a while.

## Parity test (GEE app ↔ Python app)

`tests/run_app_parity.py` runs `app.js` under Node with a stub `ui`
(`tests/ui_stub.js`), drives it through its own buttons and map-click handler, and
compares with the Python app's code on the same settings:

1. **Legacy reference case** (`tests/reference_case.js`; not in the GUI), through the
   app's modules: config equals BULC-D_rebuild's `legacy_reference()`; inspector rows
   and chart values equal `pixel.pixel_history()` at pixels 1–3; condition equals
   `outputs._outcome_from_result()` over a 30 m box.
2. **The GUI** (asset area = the testsite, default widgets, Run): no validation
   shortcuts are exposed (checked buttons, area sources and labels); widget defaults
   equal the Python app's (both the original GUI's where it had one); the config and
   each first-detected-season config equal `EarlyDetectionApp.build()`; the condition
   layer follows the original GUI's rule at 0.65/0.75, recomputed from the run's final
   probabilities (the check reports how many pixels have 0.65 < P(increase) <= 0.75,
   which one shared threshold would have mapped as increase); condition and first-detected-season layers equal
   `outputs.outcome_image()` and `combine_season_timing()` over the box; the inspector
   equals `pixel_history()` at pixel 1 (map click) and pixel 3 (typed lon/lat + Submit
   Pixel); the inspector's expectation period (observations used in the fit, fitted
   curve, coefficients, residual SD, R2) equals Python bulcd's expectation fit at
   those pixels; layer list in the notebook's order, only condition shown. Detection
   timing:
   - last-detection and detection-episode layers equal `combine_episode_metrics()`;
   - the first-detected-season bands are identical with and without the episode bands;
   - at every pixel, first ≤ last detection, and one episode means last = first.

   2b. The same run with detection timing set to **raw** in the GUI equals the
   `confirmed=False` combinations.
3. **Non-default settings** (including fit order 2): configs equal `EarlyDetectionApp.build()` with the same
   widget values.
4. **Expectation fit orders 2 and 3**, each chosen in Advanced settings and run through
   the GUI. Order 1 is the default run in 2, which is also checked to be order 1. For
   each order:
   - configs and modality flags equal `build()`;
   - condition and first-detected-season layers equal Python over the box;
   - inspector rows and the expectation fit (regressors, coefficients, residual SD, R2)
     equal Python at pixel 1;
   - the run label and the fit summary name the order, and the short-season warning
     shows for the default 122-day season.
5. **Robert's Pine Mountain pixel** (`docs/findings.md`, 2026-10-13). These all agree with the
   documented values (first detection Apr 17, last detection Sep 24, 2 episodes):
   - the JS and Python detection timing images;
   - both inspectors' episodes, with identical notes.

The true-color and NBR layers are reference imagery outside BULC-D and aren't
compared. It uses BULC-D_rebuild's Node environment and Earth Engine token helper
(setup in `../BULC-D_rebuild/gee/README.md`). From the `bulcd` env:

```sh
cd gee/tests && python run_app_parity.py      # ~45 min
```

`tests/controls_check.js` is a quick offline check of the settings panel (no
Earth Engine). It covers four things:

- The defaults equal the original BULC-D GUI's settings where it had one
  (`tests/legacy_gui.js`, with the source line for each), through the widgets and the
  config they build; the inspector's crossing notes and threshold lines apply 0.65 to
  decrease and 0.75 to increase, strictly.
- The day list follows the month: Mar 31 switched to April becomes Apr 30, and February has 28 days.
- Dec 31 is valid.
- The expectation years are inclusive, with one season per year.

```sh
node gee/tests/controls_check.js
```

`tests/inspector_state_check.js` is a regression test for the inspector's coordinate
handling (live Earth Engine, ~5 min). It drives the app through this sequence:

1. A map click at coordinate A, then inspect.
2. Change the sensitivity.
3. Run Early Detection again.
4. Submit Pixel.

It checks that the coordinate boxes, every inspector query and the marker stay
exactly at A, and that the rerun keeps the click/Submit handlers and drawing-tool
state. It also checks that each inspection's charts equal a fresh computation at A
under that run's settings. Chart tables here and in the parity test are compared to 1e-6
(`tests/table_close.js`): Earth Engine can return the same computed value with a
different last digit from one evaluation to the next.

```sh
cd gee/tests && node inspector_state_check.js
```

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
| `outputs.js` | Condition, first-detected season, true color, NBR composite | `outputs._outcome_from_result()`, `detection_timing_image()`, `combine_season_timing()`, `annual_true_color()`, `annual_nbr()`, `nbr_stretch()`; `render` colors |
| `inspector.js` | Pixel history rows, the two charts | `pixel.pixel_history()`, `plot_pixel_history()` |
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
2. **Settings,** with the notebook's defaults and limits: expectation years
   (2018–2023), monitoring year (2026), season start/end (Jun 1–Sep 30), sensitivity
   (1.0), decision threshold (0.5), first-detected season (on); advanced: dampening
   (0.5), posterior leveler (1.0), monitoring sensors (L8, L9, S2; the expectation is
   always Landsat 8), forest-only and water masks (on), allow large areas. A
   description states the periods in words and blocks invalid settings. Fixed, as in
   the notebook: the legacy evidence table, cloud 70, day step 4, even starting odds,
   NBR, average level + one annual cycle.
3. **Run Early Detection** recomputes for the chosen area. Layers, bottom to top, in
   the map's Layers control: true color for the monitoring year and the two before;
   the NBR composite (R/G/B = those years, one stretch, water masked); first detected
   season (decrease; separate runs for up to three seasons, confirmed definition);
   **condition** (the primary layer, on at 0.85 opacity); the study-area outline.
4. **Pixel inspector.** Click the map or type a longitude/latitude and press **Submit
   Pixel**. "Target Year vs. Fit" and "Probability
   Through Time", sampled on the 30 m result grid, probabilities at each observation's
   own date. A run keeps the coordinate boxes, so Submit Pixel inspects the same pixel
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
2. **The GUI** (asset area = the testsite, notebook-default widgets, Run): no
   validation shortcuts are exposed (checked buttons, area sources and labels); widget
   defaults equal the notebook's; the config and each first-detected-season config
   equal `EarlyDetectionApp.build()`; condition and first-detected-season layers equal
   `outputs.outcome_image()` and `combine_season_timing()` over the box; the inspector
   equals `pixel_history()` at pixel 1 (map click) and pixel 3 (typed lon/lat + Submit
   Pixel); layer list in the notebook's order, only condition shown.
3. **Non-default settings:** configs equal `EarlyDetectionApp.build()` with the same
   widget values.

The true-color and NBR layers are reference imagery outside BULC-D and aren't
compared. It uses BULC-D_rebuild's Node environment and Earth Engine token helper
(setup in `../BULC-D_rebuild/gee/README.md`). From the `bulcd` env:

```sh
cd gee/tests && python run_app_parity.py      # ~20 min
```

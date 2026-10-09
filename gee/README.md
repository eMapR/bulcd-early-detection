# gee/ — Earth Engine Code Editor app (Milestone 1)

A GEE JavaScript version of the Early Detection interface. The Python app
(`src/bulcd_early_detection/app.py`) and notebooks are the specification; this is
not derived from the legacy GUI's code.

BULC-D itself runs in `BULC-D_rebuild/gee/bulcd.js`, a port of the Python `bulcd`
package held to JS ↔ Python parity there (`gee/tests/run_parity.py`). Per this repo's
rule, no algorithm code is copied here: these modules only interpret its outputs.

| File | Role | Python counterpart |
|---|---|---|
| `config.js` | Fixed, read-only reference case (JSON form of `BULCDConfig`) and display settings | `cases.py legacy_reference()` in BULC-D_rebuild |
| `outputs.js` | Classification map (decision threshold rule, colors) | `outputs._outcome_from_result()`, `render.OUTCOME_COLORS` |
| `inspector.js` | Pixel history rows, the two charts | `pixel.pixel_history()`, `plot_pixel_history()` |
| `app.js` | Code Editor UI: map, legend, map click / lon-lat entry, inspector panel | `app.py` |

## Milestone 1 scope

- One known case: the legacy reference case (testsite, 2024 expectation → 2025
  target, full year, L8+L9+S2, NBR, day step 3, legacy levelers). Python reproduces
  the legacy GUI exactly at its three reference pixels (BULC-D_rebuild decision 0011).
  The configuration is fixed; there is no control panel yet.
- Classification map: decrease / unchanged / increase where P > 0.5, water masked.
- Pixel selection: click the map (fills the Longitude/Latitude boxes) or type a
  coordinate and press **Submit Pixel**; a reference-pixel menu selects pixels 1–3.
- Inspector: "Target Year vs. Fit" (expected fit, observed NBR, each observation
  colored by the class its evidence favors) and "Probability Through Time"
  (P(decrease/unchanged/increase) with the decision threshold). Sampled on the 30 m
  UTM result grid; probabilities are plotted at each observation bin's own date,
  not one step late as in the legacy chart.

## Running it in the Code Editor

Git is the source of truth; the Code Editor holds generated copies. Two Code Editor
repositories, mirroring the two git repos:

```
users/<user>/BULC-D_rebuild           bulcd
users/<user>/bulcd-early-detection    app  config  outputs  inspector
```

`python tools/build_gee_deploy.py <user>` writes the five files to `dist/gee/` (not
tracked) with `app`'s module paths set for `<user>` and a header naming each file's
source commit. Paste each into the matching Code Editor file and run `app`. After any
change in git, re-run the script and re-paste. The whole case is computed on the fly,
as in the legacy GUI, so map tiles take a while.

## Parity test (GEE app ↔ Python app)

`tests/run_app_parity.py` runs `app.js` under Node with a stub `ui`
(`tests/ui_stub.js`), clicks each reference pixel through the app's own map-click
handler, and compares with the Python app's code on the same case:

- `config.js` equals BULC-D_rebuild's `legacy_reference()` config;
- inspector rows and chart values equal `pixel.pixel_history()` at pixels 1–3;
- the classification equals `outputs._outcome_from_result()` over a 30 m box.

It uses BULC-D_rebuild's Node environment and Earth Engine token helper (setup in
`../BULC-D_rebuild/gee/README.md`). From the `bulcd` env:

```sh
cd gee/tests && python run_app_parity.py      # ~10 min
```

# Project State

Last updated: 2026-10-08

Concise current-state/handoff doc. Detailed lessons, experimental
results, and their explanations live in `docs/findings.md` — read it for
the "why," not this file.

## Architecture

Two-repo split:

- **`BULC-D_rebuild`** (`../BULC-D_rebuild`, package `bulcd`) — the
  Bayesian change-detection engine. External dependency, not modified
  here. See its own `CLAUDE.md`/`docs/` for architecture/status.
- **`bulcd-early-detection`** (this repo) — will hold the early-detection/
  monitoring interface for land-cover, land-use, and vegetation change
  generally (harvest, insect/disease, fire, beaver-related change,
  clearing/development, recovery — not forest disturbance specifically).
  BULC-D detects spectral change; cause attribution is separate. No
  first interface-layer code is the Milestone 2 prototype notebook
  (`notebooks/`) and its small support package (`src/bulcd_early_detection/`).

## Completed work

- Repo scaffolding + `bulcd` dependency wired up (`engine` extra, not a
  default dependency — see `README.md` and `docs/findings.md`'s pip
  entry). `tests/test_bulcd_dependency.py` passing.
- **Milestone 1 — chronological replay experiments** (all via
  `bulcd.inputs.organize_inputs`/`bulcd.engine.run_bulcd`'s public API,
  reading `probability_stack`; no BULC-D_rebuild code modified):
  - `experiments/replay_bb_complex_fire.py` — plumbing test against the
    validated 2003 B&B Complex Fire point.
  - `experiments/replay_harvest_2025.py` / `replay_fire_2026.py` — two
    real, independently-dated disturbances, target periods spanning
    before/during/after each event.
  - `experiments/replay_recency_sweep.py` — `recency_factor` sweep
    (1.00/0.95/0.90/0.85/0.80) against the same two sites, isolating
    that one parameter.
  - `experiments/trace_fire_recency_mechanism.py` — diagnostic trace of
    the fire replay's per-step Bayesian update, validated exact-match
    against real `probability_stack` output.
  - `experiments/replay_production_matrix.py` — same two sites/configs,
    real production transition matrix (from BULC-D_rebuild's
    `configs/cell_8c_comparison.yaml`) instead of Willis's illustrative
    thesis example, `recency_factor=1.0`.
  - `experiments/spatial_validation.py` — same production-matrix config,
    run over a real ~5km buffer (not just the point) per site. Produces
    decrease_probability/mask/first-detection-year/reference-imagery
    PNGs (`experiments/output/spatial/`) and a published inspectable
    gallery (link in `docs/findings.md`'s 2026-09-20 entry).
  - All outputs in `experiments/output/`; full analysis in
    `experiments/*_findings.md` and `docs/findings.md`.

- **Milestone 2 (in progress) — NPS prototype notebook**,
  `notebooks/early_detection_demo.ipynb`, for a Wednesday 2026-09-30
  demo. Goal: simplify BULC-D for monitoring use. One primary map
  (decrease / unchanged / increase), plus supporting confidence,
  first-detection date, Sentinel-2 before/after imagery, and a zoom.
  - Simple controls: monitoring year and season, baseline years,
    decision threshold, and sensitivity (`z_score_numerator_factor`).
    The full `BULCDConfig` is editable in an `advanced()` hook.
  - Defaults reproduce the validated fire-replay config exactly (checked
    against `replay_fire_2026.build_config`; see also `tests/test_config.py`).
  - Two modes:
    - Apostle Islands (default) loads a precomputed asset,
      `projects/bulcd-python-rebuild/assets/apostle_islands/apostle_2026_v1_all`.
      The whole park ran as ONE batch export in 19 min. The notebook runs
      in ~1 min and is saved with outputs embedded.
    - `USE_CUSTOM_AOI` runs live on any FeatureCollection asset, with an
      AOI size check first. It's slow: ~4 min per map for 9 km², ~17 min
      for the whole notebook. Test asset: `.../apostle_islands/test_aoi_stockton_east`.
  - Third mode, `AOI_MODE = "draw"`: draw a polygon on an ipyleaflet
    map, saved as `notebooks/aois/<name>.geojson` and reloadable by
    name. No EE asset needed. Example: `stockton_south_shore` (3 km²).
  - Section 10, parameter comparison: named `compare.Variant`s over one
    saved drawn area; outcome map + area totals only. Each BULC-D run is
    fetched once via `ee.data.computePixels` (~10–30 s for a few km²).
    Threshold/mask variants reuse that run and are classified locally.
  - Package modules: `config.py`, `outputs.py`, `render.py`, `drawing.py`,
    `compare.py`. The
    production matrix and the thumbnail/reference-image helpers moved
    here; the experiments now import them, with behavior unchanged.

- **2026-09-29: notebook restructured as an NPS-facing walkthrough**
  (user direction: explain BULC-D; don't chase individual artifacts):
  1 What is BULC-D (with a one-pixel teaching figure from the fire replay),
  2 Setup and parameters, 3 Apostle Islands example (+ Devils Island
  close-up, `notebooks/aois/devils_island.geojson`, the park part containing
  USGS GNIS 1563935), 4 Parameter effects (Devils Island, same extent: default,
  threshold 0.9, sensitivity 0.5/2.0, dampening 0.7, posterior leveler 0.9;
  plus whole-park threshold totals via `outputs.reclassify`), 5 Try your own
  area (draw/asset, off by default). Runs in ~2 min. Notebook defaults and
  the precomputed result are unchanged.

- **2026-09-29: North Cascades notebook** (`notebooks/north_cascades_demo.ipynb`),
  same structure and unchanged default config. Boundary: WDPA "North Cascades"
  National Park (2,022 km², two units; Ross Lake/Lake Chelan NRAs excluded),
  `outputs.north_cascades()`. Whole park precomputed as ONE export in 40.2 min:
  `projects/bulcd-python-rebuild/assets/north_cascades/noca_2026_v1_all`.
  Comparison box: `notebooks/aois/noca_comparison_box.geojson` (23.4 km², north
  unit, 48.83 N 121.19 W). Reference imagery uses single clear S2 dates there
  (seasonal composites are hazed from ~Jul 20, 2026) and a Sep 5–30 composite
  park-wide. `outputs` now derives the UTM projection per area (Apostle results
  verified identical). Runs in ~1.5 min.

- **2026-09-29: testsite notebook** (`notebooks/testsite_demo.ipynb`), same
  structure and unchanged default config, study area = the supplied
  FeatureCollection `projects/bulcd-python-rebuild/assets/testsite` (1 feature,
  26.3 km², one contiguous polygon, western Oregon, no attributes). Precomputed
  in 1.4 min: `projects/bulcd-python-rebuild/assets/testsite_bulcd/testsite_2026_v1_all`.
  Parameter effects over the whole site. Adds a 2024 | 2025 | 2026 true-color
  Sentinel-2 row (single clear dates, Sep 16 each year, one fixed stretch) via
  `report.scene_row` / `render.show_map_row` / `render.TRUE_COLOR`. Runs in
  ~1.5 min. Three demo notebooks now: `early_detection_demo.ipynb` (Apostle
  Islands), `north_cascades_demo.ipynb`, `testsite_demo.ipynb`.

- **2026-09-29: notebooks restructured as user-facing demonstrations**, all three
  generated from `tools/build_demo_notebooks.py` (shared five-part structure,
  terminology, figure conventions):
  - "2026 condition relative to expectation" and "first detected" wording.
  - Section 4 rebuilt as a one-at-a-time sensitivity check:
    - sensitivity 0.5 | 1.0 | 2.0 maps;
    - `compare.parameter_response` charts for sensitivity, threshold, dampening
      and posterior leveler.
  - A pixel-history chart in every case study (`pixel.py`; rule-based
    `representative_pixel`), with the pixel marked on the maps.
  - The generic fire teaching figure was dropped in favor of the study-area pixel.
  - testsite: first-detected-season map from three independent annual runs
    (fixed 2018–2023 baseline; `outputs.combine_season_timing`), temporal NBR
    composite (`outputs.annual_nbr`, `report.nbr_rgb_map`), true-color 2024 / 2025 / 2026.
  - Runtime about 3–5 min each.

- **2026-09-29 (later): product suite synchronized across all three case studies**:
  - Apostle Islands and North Cascades gained the first-detected-season product. Annual runs
    `apostle_timing{y}_base2018_2023_v1` and `noca_timing{y}_base2018_2023_v1`, 25 min for all six.
  - Temporal NBR composite (water masked; large areas skip the forced 30 m reprojection).
  - Annual true color: clear-sky median composites for the parks
    (`outputs.annual_true_color`, `report.annual_true_color_row`); single dates for testsite.
  - Three-season pixel history for every site.
- **Interactive prototype** (`notebooks/early_detection_interactive.ipynb` →
  `app.EarlyDetectionApp`):
  - Draw, saved area or FeatureCollection asset, with size guards.
  - Expectation/monitoring sliders; advanced settings collapsed.
  - Live condition, first-detected season, NBR composite and true-color layers on an ipyleaflet map.
  - Click-to-inspect pixel history; on-demand sensitivity maps and response curves.
  - Tested in a kernel on testsite: run ~2–2.5 min, inspect ~75–100 s.
  - An Earth Engine request deadline (300 s) was added after unexplained 0%-CPU stalls in
    automated kernel tests.

- **2026-09-30: "first detected" is now end-of-season-confirmed (rule B)**
  (`combine_season_timing(confirmed=True)`, the default). A season counts only if it ends as
  decrease; the date is that season's first crossing. Raw first crossing is still available
  (`confirmed=False`) as a possible future diagnostic/alert product (not built). All notebooks were
  re-executed with it, and the pixel charts use the corrected product-grid sampling.

- **2026-09-30: interactive app fixes:**
  - **Layers never displayed** (root cause): in ipyleaflet a raster layer's `visible=False` only sets
    opacity 0, so Leaflet's layer control could never reveal the true-color, NBR or timing layers.
    Condition (added last, 85% opaque) also covered anything beneath. Replaced with a Map layers
    panel: checking a layer adds it on top, and each layer has an opacity slider.
  - **Failures are now visible:** each layer is built and tile-checked independently; failures show
    in red and in the status line ("Analysis complete. Map layers: N of M loaded …").
  - **Seasonal window:** was limited to weekly steps from Apr 1 to Oct 31. Now full-year start/end
    month-day pickers (Feb 29 excluded), with validation (start before end, no wrap past Dec 31;
    Run disabled with a message otherwise). The same window applies to expectation and monitoring.

- **2026-10-04: legacy GUI equivalence, one pixel** (`experiments/legacy_gui_equivalence.py`, testsite,
  2024 → 2025, L8+L9+S2, day step 3). Python reproduces the GUI's spring-2025 drop. Its formulas match the fetched
  legacy source stage by stage. The first input divergence is S2: legacy applies no scene-cloud filter; bulcd drops
  scenes > 70%. Chart semantics are inferred, not confirmed (`HelperFunctions-BULCD` not fetched). Details:
  `docs/findings.md`, 2026-10-04.
- **2026-10-04 (later): equivalence confirmed against the GUI's own chart CSVs** (`experiments/legacy_gui_csv_compare.py`).
  With native-pixel point sampling and no S2 scene filter, Python matches every stage within the CSVs' rounding.
  Bins match 60/60 and probabilities 363/363 (after the GUI chart's one-step offset). Remaining differences:
  - the bulcd S2 scene filter (first divergence; changes inputs);
  - the harmonic time axis (≤ 0.0013 NBR; legacy fracDOY reproduces GUI fits exactly);
  - the GUI probability chart plotting the prior first.
- **2026-10-04: pixel 2 (stable) confirms it.** At the location the GUI actually sampled, with S2 filter off: all NBR
  and residuals exact, bins 61/61, probabilities 363/363. That location is one S2 pixel about 1–11 m NE of the
  reported coordinate; at the reported coordinate, S2 values differ. The as-is S2 filter flips 12/60 bins here
  (max ΔP 0.155), so it matters at stable pixels.
- **2026-10-08: pixel 3 (increase) completes the set. GUI-vs-Python equivalence is validated for decrease,
  unchanged, and increase.** With legacy-compatible inputs/settings (native-pixel sampling, no S2 scene filter),
  all three pixels give exact NBR and residuals, exact bins (60/60, 61/61, 61/61), and probability trajectories
  that agree exactly once aligned (363/363 each). Pixel 3 ends at 0.044/0.055/0.900 (increase) in both. The three
  known differences stay separate:
  1. **S2 scene filter:** changes inputs. At pixel 3 it changes **30/61 bins**, so it can materially alter the
     classification evidence, not just the fit.
  2. **Harmonic-fit time axis:** ≤ 0.0019 NBR; the legacy fracDOY axis reproduces the GUI exactly.
  3. **GUI chart's one-step plotting offset:** chart only.

  GUI exports and their coordinates/settings are in `experiments/reference_data/legacy_gui_charts/`. Neither bulcd
  nor Early Detection behavior was changed. Details: `docs/findings.md`, 2026-10-08.

- **2026-10-08: BULC-D_rebuild decision 0011 (legacy S2 + fracDOY now default).** With normal/default settings,
  Python now exactly reproduces the legacy GUI for the controlled decrease, unchanged, and increase pixels through
  observed NBR, fitted expectation, residuals, bins, and aligned probability trajectories (bins 60/60, 61/61, 61/61;
  aligned probabilities 363/363 each). The remaining GUI probability-date difference is a plotting offset, not an
  algorithm difference. The GEE JavaScript engine (`BULC-D_rebuild/gee/bulcd.js`) in turn matches Python to
  floating-point precision (max diff 2.7e-15). The S2 scene filter is now an opt-in (`s2_scene_cloud_threshold`).
  - Effect on the Early Detection default testsite run: 0.39% of analyzed pixels change class, almost all from S2.
  - **All existing `_v1` precomputed assets are pre-0011 outputs and should not be treated as current results**;
    `load_precomputed()` warns. Regenerate the important ones as `_v2` after reviewing the impact.
  - Details: `docs/findings.md` 2026-10-08 (later).

- **2026-10-08: GEE app Milestone 1 (`gee/`, see `gee/README.md`).** Code Editor app on
  `BULC-D_rebuild/gee/bulcd.js`: the fixed legacy reference case (read-only config), classification map,
  map-click and lon/lat + Submit Pixel selection, and the two-chart inspector ("Target Year vs. Fit",
  "Probability Through Time" at correct dates, 30 m grid). `gee/tests/run_app_parity.py` drives the app's own
  click handler under Node and passed: config equals BULC-D_rebuild's `legacy_reference()`; inspector rows and
  chart values equal `pixel.pixel_history()` at pixels 1–3 (122 rows each); classification equals
  `outputs._outcome_from_result()` on 6,339 box pixels. Not yet run in the Code Editor (deployment location TBD).
  Pixel 2's final values on the 30 m grid (0.046/0.911/0.043) differ from the GUI's native-pixel ones; that is
  the documented sampling difference.

## Reproducibility notes

- **Earth Engine input imagery can change between runs.** Late-September 2026 Sentinel-2 scenes over
  North Cascades were re-ingested (EE version 2026-09-30 04:20 UTC) between two exports of
  identical configurations. The outputs differed in 126 pixels (0.11 km²). Compare runs exported
  close together, re-export the comparison baseline alongside new variants (as the sensor
  experiment does), and note that a monitoring season still in progress keeps changing.
- **Leap-year window shift:** `MonitoringControls` computes the seasonal day-of-year window from the
  monitoring year, so 2024 runs use days 153–274 in every year (Jun 2 – Oct 1 in non-leap baseline
  years) while 2025/2026 runs use 152–273. A one-day difference; noted, not changed.

## Unresolved (needs validation; not being investigated in the notebook work)

- **Apostle Islands early-June pattern:** ~76% of 2026 flagged area first crossed the
  threshold in the first two weeks of June. Leading lead is the Landsat-only baseline vs
  Sentinel-2 monitoring mismatch (sensor-consistency experiment); not confirmed park-wide.
- **North Cascades widespread decrease:** ~32% of analyzed forest flagged, mostly later in the
  season. Candidates: real 2026 change, haze/smoke, baseline-model fit in steep terrain.
- **First-detected-season product at the parks:** against the fixed 2018–2023 expectation it flags
  39% of Apostle Islands' analyzed forest (85% first in 2026) and 73% of North Cascades' (82% in 2024).
  That is far more than the 2026 condition products (2018–2025 expectation). At North Cascades it
  agrees poorly with the NBR composite. Looks systematic (baseline years / sensors / seasonal
  conditions), not investigated. Decide whether to show it in the park notebooks.
- **Superseded Earth Engine assets** (continuous 2024–2026 timing run, first season exports)
  are intentionally kept for now; clean up later.

## Future GUI requirements

- **Pixel inspector:** click a map → that pixel's observation time series, its
  departure from expectation, the decrease/unchanged/increase probability history,
  and the first threshold-crossing date. The data side exists:
  `pixel.pixel_history(config, lon, lat)` returns plain rows for any coordinate.
  The notebook chart (`pixel.plot_pixel_history`) is the prototype.
  2026-10-08: the app's inspector now follows the legacy GUI's "Target Year vs. Fit" and "Probability
  Through Time" layout: all three probabilities, plotted at each observation's own date (no one-step
  offset), and first crossings for both decrease and increase. It still samples the clicked 30 m result
  pixel, not GUI-style native pixels (user decision).
- **Intended flow:** choose area → configure monitoring → run/view results →
  inspect detections → click pixels. Google Earth Engine is the current likely
  deployment environment (users may not be able to install software). Not final.

## Active problem

Wednesday (2026-09-30) NPS demo prep. Notebook works end-to-end in both modes.

**Open interpretation issue (post-demo, deliberately not addressed yet):**
~76% of Apostle Islands' 2026 changed area was already detected in the
first two weeks of June. The current output therefore mostly identifies
places that differ from the 2018–2025 expectation, not necessarily
changes that began during the 2026 monitoring season. Detection behavior
is unchanged until this is investigated. Details: `docs/findings.md`,
2026-09-28.

## Key findings (see `docs/findings.md` for full explanations)

- `probability_stack` already contains the full progressive-observation
  trajectory from one `run_bulcd()` call — materially simplifies the
  eventual monitoring architecture (no need to rerun BULC-D per cutoff
  date).
- Willis (2022)'s illustrative thesis transition matrix (used in the
  earliest replays) turned out to be the wrong baseline — hand-picked,
  not production-calibrated, giving extreme-bin evidence far too weak
  (1.45:1 raw odds) to cross 0.5 within available data at either site.
- **The real production matrix** (`configs/cell_8c_comparison.yaml`) is
  now traced all the way to the actual legacy GEE source file
  (`legacy/6003.3c-BULC-AdvancedParameters.txt`, byte-for-byte match) —
  it's the app's real hardcoded default, not a one-off analyst choice,
  and this exact matrix+config was quantitatively validated against a
  real legacy GUI render (97.9% argmax agreement). With it,
  `recency_factor=1.0` (no extension needed), **both sites cross 0.5
  cleanly** — harvest in 9 valid observations (+38d), fire in 6 (+21d),
  both >0.99 confidence. Our `dampening_factor=0.5`/`posterior_leveler=1.0`
  still don't match production's real levelers (0.7/0.7/0.9) — a known,
  pre-existing gap, not something changed this session.
- **First spatial check (~5km buffers, production matrix):** harvest
  shows several distinct real-looking cutblock shapes plus
  road-correlated speckle (9.85% of buffer >0.5); fire shows one large
  coherent mass matching a clearly visible burn scar in reference
  imagery — initially-puzzling sharp boundary turned out to be a lake
  shoreline, not an artifact (44.75% of buffer >0.5). Visual, not a
  false-positive rate — no independent disturbance-perimeter data exists
  for the buffers. Gallery link in `docs/findings.md`.

- **Apostle Islands 2026, first read:**
  - Mapped change: 2.3 km² decrease and 0.3 km² increase out of
    164 km² analyzed. About 5 km² of non-forest land isn't analyzed.
  - ~76% of the changed area was first detected in the first two weeks
    of the season, so it's mostly "differs from 2018–2025 normal", not
    "disturbed this summer".
  - Detections concentrate on island shorelines and at the Stockton
    Island wetland/sandspit edges.
  - None of it has been checked against any record — see
    `docs/findings.md`, 2026-09-28.

- **Forest mask is NOT a BULC-D requirement.** Legacy has none; the
  rebuild's default `mask_non_forest=True` is post-processing only; the
  legacy-matched cell 8C config has it off. Precomputed Apostle result
  stays forest-only for Wednesday (user decision). See `docs/findings.md`.
- **Lead from the first comparison (one 3 km² shoreline area only):**
  Landsat-only monitoring removed almost all decrease (0.049 → 0.001 km²);
  a post-high-water 2022–2025 baseline did not (0.062 km²). Suggests a
  Sentinel-2-in-monitoring vs Landsat-8-only-baseline mismatch, possibly
  also behind the 76%-early-June issue. Not yet tested more widely.

## Next steps

- Legacy equivalence: done. BULC-D_rebuild decision 0011 matches legacy (no default S2 scene filter, fracDOY), and
  pixels 1–3 are exact with the default implementation. Next: the GEE app on `BULC-D_rebuild/gee/bulcd.js`, held to
  JS ↔ Python parity (`gee/tests/run_parity.py`), Milestone 1 = the legacy reference case. Regenerate `_v1` assets
  as `_v2` after reviewing the impact. Still open:
  - The pixel-2 location offset. Capturing the charted point reliably needs `HelperFunctions-BULCD`'s
    `getChartResults` source (it handles its own clicks on all four maps), or click listeners on all four maps.
  - The app/notebooks sample on a 30 m UTM grid, not the GUI's native-pixel sampling.

- Post-demo: decide the Early Detection masking default (recommended:
  water on, forest off, forest optional/custom mask asset).
- Post-demo: test the Sentinel-2 mismatch lead on more areas (inland
  forest, other shorelines) and against the early-June timing issue.

- Before the demo: a quick look at the notebook with the user; decide
  whether to present the shoreline ring as a known limitation.
- Identify a known historical Apostle Islands disturbance for a real
  validation case.
- Shoreline ring: check whether it's water-mask-edge mixing
  (JRC occurrence threshold) or Lake Superior level change vs the
  2018–2025 baseline.
- Live custom-AOI mode recomputes BULC-D for every map. If that's too
  slow for experimenting, export custom AOIs as assets too (the same
  path Apostle Islands uses).

- Fire's second, smaller, unexplained detached detection patch (east of
  the lake) — not investigated.
- Harvest's road-correlated speckle pattern — worth a closer look before
  trusting spatial detections near linear features.
- `recency_factor` sweep against the production matrix hasn't been run
  yet.
- Interface/monitoring-system design remains undiscussed — needs
  explicit scoping with the user before implementation starts.

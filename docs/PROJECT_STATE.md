# Project State

Last updated: 2026-09-29

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

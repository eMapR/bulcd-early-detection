# Regional batch processing plan (USFS Region 6, 2026)

Agreed with the user 2026-10-21. Status and the next step to take are in
`docs/PROJECT_STATE.md` ("Pick up here"); this file is the plan and the decisions.

**Goal.** Regional 2026 disturbance (general landscape change) products for the R6 ecoregions, computed as
Earth Engine batch exports, stored as GEE assets, and displayed in the GEE app without rerunning BULC-D. Later,
the same products from a local backend (DataLoader + OSU Slurm), compared against GEE over Oregon. Since the
2026 season may still be in progress, products are year-to-date snapshots with an as-of date.

## Decisions

- **Branch:** `feature/regional-batch-processing`, created from `legacy-parity-0011-app` after the
  expectation-sensor work is finished and committed. Don't merge into `main` yet.
- **Orchestration in Python;** Python `bulcd` builds the Earth Engine computation (held to parity with
  `bulcd.js`, which the interactive app uses). No algorithm code copied or modified.
- **Backend-neutral where practical:** configuration, tiling, job tracking and the product spec don't import
  `ee`. GEE is one backend; a local Slurm backend comes later (not now).
- **Pilot configuration:** monitoring year 2026; season Jun 1-Sep 30; 30 m; EPSG:5070, grid aligned to the
  NLCD/LCMS 30 m grid (verify the alignment); 400 km^2 Oregon Coast Range box (20 x 20 km around the testsite,
  -123.57, 44.84); 10 x 10 km tiles (4 tiles, with seams inside the box); single-season 2026 timing
  products. Existing BULC-D defaults (the original GUI's, as in the apps) otherwise.
- **Expectation years and sensors: not final** until the user has reviewed the expectation-sensor results.
- **No forest-only mask** (general landscape change). Water masked as in the apps. Optional land-cover masks
  evaluated later.
- **Probabilities as scaled uint16;** measure the quantization error during validation.
- **Ecoregions:** the existing R6 ecoregion boundaries from the FS Multi-Model project. Asset paths to be
  identified when expanding beyond the pilot.
- **Validation:** engineering validation (does the batch workflow reproduce BULC-D?) is separate from
  scientific validation (are detections real disturbances?). Engineering equivalence and performance first;
  the reference-data assessment after the pilot works. Include Robert's Pine Mountain pixel/box
  (-120.959, 43.695; `docs/findings.md` 2026-10-13) as a seasonal false-detection (snowmelt) test.
- **Infrastructure later:** don't build much infrastructure before the core processing is confirmed at
  regional scale.

## Order of work

1. Finish and commit the expectation-sensor work (placeholder resolved, tests complete); report the results.
2. Create the feature branch.
3. Regional configuration and output specification.
4. Minimal GEE batch-export prototype on the existing engine.
5. Verify that one BULC-D run per tile produces every output (no redundant runs).
6. Run the four-tile pilot.
7. Validate against the interactive implementation, including tile seams.
8. Benchmark performance; investigate memory limits (expectation sensors x length x `shardSize`).
9. Then expand job tracking, resumability and the regional viewer.

## Key technical points (from the 2026-10-21 investigation)

- **Tiling should be exact per pixel:** no neighborhood operations; `binEvidenceByDayStep` makes the same bins
  for every area (a masked placeholder in each bin), an empty bin leaves the probabilities unchanged
  (`posterior.unmask(prior)`), and `filterBounds` only drops scenes that miss the tile. To be confirmed by the
  seam test, not assumed.
- **One run per tile:** `outputs.detection_timing_image(config)` / `detection_episode_image(config)` each call
  `run_bulcd` themselves, and the apps run BULC-D once for condition plus once per timing season. Add
  variants that take an existing result (the current functions delegate to them, so behavior is unchanged;
  `layer_size_check.js` and the parity tests confirm it).
- **Memory:** the expectation harmonic fit's memory depends on years x bins x sensors per pixel, not area, so
  smaller tiles don't help; in batch, `Export.image` `shardSize` is the lever to test. A 6-year L8+S2
  expectation completed as a batch export at North Cascades while interactive requests failed.
- **"Description length exceeds maximum"** is a Code Editor map-layer limit; batch exports and displaying stored
  assets avoid it.
- **Bin time is the bin's end date** (`binEvidenceByDayStep` stamps `system:time_start` with the bin end). The
  product spec must say so.
- **Existing export path to start from:** `outputs.export_study_area`, `run_metadata`, `load_precomputed`,
  `wait_for` (Apostle 280 km^2 in 19 min, North Cascades 2,022 km^2 in 40 min, testsite 26 km^2 in 1.4 min,
  each one task).

## Proposed layout

```
src/bulcd_early_detection/regional/
  spec.py        product spec: bands, dtypes, scaling, nodata, class codes, timing definitions, version  (no ee)
  run_config.py  RegionalRun: run_id, region, MonitoringControls, grid, tile size, product version -> YAML  (no ee)
  tiling.py      fixed grid -> tile IDs (row/col) intersected with the region polygon (no ee)
  jobs.py        manifest: tile x state {pending, submitted, running, succeeded, failed}, attempts, task id,
                 error, timestamps, output URI; resume = reconcile with the backend, resubmit the rest
  provenance.py  git commits of both repos, bulcd version, ee version, sensors, input as-of date, timestamps
  backends/gee.py    one run_bulcd -> product image -> Export.image.toAsset into an ImageCollection per run
  (backends/slurm.py later)
  cli.py         plan | submit | status | resume | assemble | validate  run.yaml
gee/regional.js  viewer (later): the run's ImageCollection mosaicked, outputs.js styling, inspector from the
                 stored config; the interactive app is unchanged
```

## Product spec v1 (draft)

| Band | Type | Values |
|---|---|---|
| `condition` | uint8 | 0 decrease, 1 unchanged, 2 increase, 3 not analyzed; masked = water / outside |
| `p_decrease`, `p_unchanged`, `p_increase` | uint16 | final probability x 10,000 |
| `first_detection_doy`, `last_detection_doy` | uint16 | day of year (bin end date), 0 = none |
| `episode_count` | uint8 | detection episodes (2026-10-13 definition) |
| `n_obs_monitoring`, `n_obs_expectation` | uint16 | valid observations (bins) per period |

Image properties: `controls_json`, `config_json`, product version, both repos' commits, export date, input as-of
date, tile id, grid.

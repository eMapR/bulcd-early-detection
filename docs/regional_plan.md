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
- **Pilot configuration** (in `regional_runs/pilot_coast_range_2026.yaml`): monitoring year 2026; season
  Jun 1-Sep 30; 30 m; EPSG:5070 on the NLCD/LCMS grid (verified 2026-10-22: transform
  `[30, 0, -2493045, 0, -30, 3310005]`, `docs/findings.md`); tiles of 333 x 333 pixels (9.99 km; 10 km is not
  a whole number of pixels), numbered from NLCD's origin; the pilot is 2 x 2 tiles (20 x 20 km) around the
  tile corner nearest the testsite (-123.57, 44.84), so the seams cross the testsite; single-season 2026
  timing products. Existing BULC-D defaults (the original GUI's, as in the apps) otherwise.
- **Sensors (decided 2026-10-22, after the expectation-sensor results, `docs/findings.md` 2026-10-19):**
  expectation Landsat 8 only, 2018-2023 (the app default); monitoring Landsat 8 + Landsat 9, no Sentinel-2.
  Sentinel-2 in the expectation fails interactively beyond 2 years, and Sentinel-2 in monitoring without it in
  the expectation produced false decreases (findings 2026-09-28/30). The expectation/monitoring mismatch
  warning still appears (L9 in monitoring only); L9 is Landsat 8's twin sensor, so this is not expected to
  matter. Check in validation.
- **No forest-only mask** (general landscape change). Water masked as in the apps. Optional land-cover masks
  evaluated later.
- **Probabilities as scaled uint16;** measure the quantization error during validation.
- **Ecoregions:** the existing R6 ecoregion boundaries from the FS Multi-Model project. Asset paths to be
  identified when expanding beyond the pilot.
- **Extent (decided 2026-10-26):** the first regional product covers National Forest land in Oregon and
  Washington, not the whole states. Candidate boundaries: `users/clarype/National_Forest_Boundaries_R6`, filtered
  to `REGION == '06'` (17 administrative units; see `docs/findings.md` 2026-10-26).
- **Detection year (decided 2026-10-26):** the product is a 10-band stack, the monitoring season's 9 bands plus
  `detection_year`. That band is the earliest confirmed season among 2024 (fixed floor, meaning "2024 or
  earlier"), 2025 and 2026, and 0 means none. It is built from one season run per year. The season tiles stay as
  they are.
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
   *Steps 4-5 done 2026-10-23: tile r0056c0034 exported and identical to live (`docs/findings.md`).*
6. Run the four-tile pilot.
   *Done 2026-10-23: all four tiles exported and identical to live (`docs/findings.md`).*
7. Validate against the interactive implementation, including tile seams.
   *Done 2026-10-24: 0 differences across seams and against the app (`docs/findings.md`).*
8. Benchmark performance; investigate memory limits (expectation sensors x length x `shardSize`).
   *Done 2026-10-26: no batch memory failures up to L8+L9+S2 6 years; 2-3 tasks at a time; about 150 EECU-s
   per tile at the pilot settings (`docs/findings.md`).*
8a. Detection-year band: 2024 and 2025 season runs of the pilot, the 10-band stack, validated against the app.
   *Done 2026-10-26: 0 differences from the app's first-detected-season layer (`docs/findings.md`).*
8b. Export optimization: several tiles per task vs one (`experiments/regional_block_benchmark.py`).
   *Done 2026-10-26: 2 x 2-tile tasks gave 2.1x the throughput and 31% less EECU per tile; outputs identical
   (`docs/findings.md`). The user decides whether to adopt them.*
8c. Region 6 extent: National Forest boundaries x ecoregions; tile list.
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
  smaller tiles don't help; in batch, `Export.image` `shardSize` is the lever to test. (Step 8: not needed;
  every combination tested completed at the default.) A 6-year L8+S2
  expectation completed as a batch export at North Cascades while interactive requests failed.
- **"Description length exceeds maximum"** is a Code Editor map-layer limit; batch exports and displaying stored
  assets avoid it.
- **Bin time is the bin's end date** (`binEvidenceByDayStep` stamps `system:time_start` with the bin end). The
  product spec must say so.
- **Existing export path to start from:** `outputs.export_study_area`, `run_metadata`, `load_precomputed`,
  `wait_for` (Apostle 280 km^2 in 19 min, North Cascades 2,022 km^2 in 40 min, testsite 26 km^2 in 1.4 min,
  each one task).

## Layout

Step 3 added `spec.py`, `run_config.py`, `tiling.py` and `regional_runs/` (run files). Step 4 added
`provenance.py` and `backends/gee.py` (with a CLI: `python -m bulcd_early_detection.regional.backends.gee RUN.yaml
[--tiles ID ...] [--dry-run] [--wait]`); `jobs.py`, `cli.py` and the viewer are to come.
`config.apply_advanced()` (moved out of the app's `build()`) builds every tile's BULCDConfig exactly as the
interactive app does.

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

## Product spec v1

Defined in `src/bulcd_early_detection/regional/spec.py`, the source of truth (band descriptions, property
list). In short:

| Band | Type | Values |
|---|---|---|
| `condition` | uint8 | 0 decrease, 1 unchanged, 2 increase, 3 not analyzed (the apps' codes) |
| `p_decrease`, `p_unchanged`, `p_increase` | uint16 | final probability x 10,000 |
| `first_detection_doy`, `last_detection_doy` | uint16 | day of year (bin end date), 0 = none or not analyzed |
| `episode_count` | uint8 | detection episodes (2026-10-13 definition), 0 = none |
| `n_obs_monitoring`, `n_obs_expectation` | uint16 | bins with at least one valid observation, per period |

- **Masked = nodata** in every band (water or outside the region): masked in a GEE asset, 255 (uint8) or
  65535 (uint16) in a file.
- **Timing rule:** confirmed by default (only a season that ends as decrease counts), as in the apps;
  recorded per run (`advanced.timing_rule`).
- **condition** is classified from the float probabilities before scaling, so it is exact. Reclassifying from
  the stored probabilities can differ only within 0.00005 of a threshold.
- **Image properties:** product version, run id, tile id, monitoring year, season, timing rule and date
  definition, bin days, grid, the whole run config and the BULCDConfig as JSON, as-of date, export date,
  provenance (both repos' commits, bulcd and ee versions).


## Next run: seven EPA Level III ecoregions (agreed 2026-11-04)

Runs **on islay**. Planned on the laptop (2026-11-04) when it had neither the pipeline branch nor islay access;
it then described the pipeline as "`32b11bf` plus uncommitted edits". In fact islay had committed steps 3–8b
through `95c462f` (pushed 2026-11-04), and the pipeline is now on `integrate/2026-11-consolidation` together
with the laptop's work. The pilot assets' `provenance_json` records the commit each was exported from.

**Regions.** `EPA/Ecoregions/2013/L3`, field `us_l3code`. The parts in Oregon and Washington (R6), *assumed*,
not yet confirmed with the user (Coast Range and Klamath extend into California, Northern Rockies into Idaho).
Areas from `TIGER/2018/States` intersections, 2026-11-04:

| `us_l3code` | Ecoregion | km² in OR/WA |
|---|---|---|
| 1 | Coast Range | 40,825 |
| 4 | Cascades | 44,856 |
| 9 | Eastern Cascades Slopes and Foothills | 35,528 |
| 11 | Blue Mountains | 63,943 |
| 15 | Northern Rockies | 21,357 |
| 77 | North Cascades | 30,302 |
| 78 | Klamath Mountains/California High North Coast Range | 15,552 |

Excluded by the user: Columbia Plateau (10), Northern Basin and Range (80), Puget Lowland (2), Willamette Valley
(3), Snake River Plain (12). Total ~252,000 km², ~2,700 tiles of 333 x 333 px.

**Settings: the pilot's (`r6-pilot-coast-range-*` `run_json`/`config_json`), with two changes from the user:**
1. **Expectation sensors L8 + L9** (pilot: L8 only). Expectation still 2018-2023; L9 contributes 2022-2023.
2. **Season widened to the full year / year to date** (pilot: Jun 1-Sep 30). Same day-of-year window for the
   expectation and monitoring, as in BULC-D. Use DOY 1-362 as the 2026-10-28 full-year analysis did
   (`meeting_2026-10-28/scripts/expectation_compare_fullyear.py`): 2024 and 2025 cover the calendar year,
   2026 runs to the latest imagery; record the as-of date on each tile.

Unchanged: NBR; monitoring L8 + L9; seasons 2024, 2025, 2026 (each a separate run against the same
expectation) plus the detection-year stack (floor 2024); Landsat scene filter `CLOUD_COVER` < 70; bulcd's
standard QA_PIXEL cloud mask; 4-day bins; fit order 1; sensitivity 1.0; thresholds 0.65 decrease / 0.75
increase; dampening 0.7; posterior leveler 0.9; production transition matrix; timing rule confirmed; no
forest mask, water masked; EPSG:5070, 30 m, the pilot's grid origin and 333-px tiles; product spec v1
(uint8/uint16, probabilities x 10,000, masked = no data).

**Order: Coast Range first.** Check results and the real cost, report to the user, then the other six.

**Cost estimate (to be confirmed by Coast Range).** Full year costs more than Jun-Sep: 510 EECU-s per
tile-season for the full-year 2018-2023 expectation (`meeting_2026-10-28/data/bench_fullyear.json`, config
A, L8-only expectation) against 135-235 for Jun-Sep. With L9 added, assume ~550-650 per tile-season, about
1,700-2,000 EECU-s per tile for 3 seasons + stack: **Coast Range ~220-270 EECU-hours, all seven
~1,300-1,600.** Check the project's EECU quota and concurrent-task limit before submitting. Storage ~460 KB
per tile product, ~5 GB for all seven.

**Risk: snow is not masked.** bulcd's Landsat mask passes the snow flag (QA bit 5, legacy behavior); with a
full-year expectation, snow is the main seasonal false-detection risk (`meeting_2026-10-28/README.md`
full-year supplement; Pine Mountain, `docs/findings.md` 2026-10-13). 2026's spring was almost snow-free, so
2026 can't reveal it. Coast Range is mostly low; Cascades, North Cascades, Blue Mountains and Northern Rockies
are where it matters. Decide after Coast Range whether those need a snow mask (a bulcd change) or a shorter
season.

**Open (from step 8b, not decided in this plan):** whether to export in 2 × 2-tile blocks. Step 8b measured
31% less EECU per tile and about 2x the throughput against single tiles (`docs/findings.md`, 2026-10-26
"Export optimization"); the cost estimate above assumes single-tile tasks at full-year settings.

## Future development: post-detection disturbance trajectories (idea, 2026-11-09; not started)

Requested by the user for later; nothing is implemented.

**Goal.** After BULC-D first detects a decrease, follow each pixel's spectral trajectory to tell apart
continued decline, recovery, stabilization and secondary disturbances.

**Why the current products can't do it.** Each season run compares the year against the same 2018-2023
expectation from the same starting odds, so P(decrease) is a persistent "departed from the pre-2024 condition"
state, not a new-event signal: a patch detected in 2024 is detected again in 2025 and 2026 (Coast Range: 69% of
2026 detections were also detected in an earlier season; repeat detections cross early, median DOY 101 vs 141
for first-time ones). detection_year keeps only the earliest season, so a second disturbance on an already
detected pixel is invisible.

**Key challenge.** Distinguishing a new disturbance from the continued effects of an earlier one, especially:
- insect and disease mortality: a slow, multi-year decline that keeps crossing the threshold;
- partial harvest (thinning) followed by fire, or mortality followed by salvage: a second, real event on a
  pixel that is already "decrease".

**Directions to evaluate (none chosen).** A rolling expectation (each season against the preceding years, the
2026-10-28 meeting's config B26) so P(decrease) measures change since the recent past; per-pixel time series
of the index after detection (slope, magnitude, return toward the expectation); second-crossing or
deeper-departure rules on the existing per-bin probabilities; comparison with LCMS change classes (slow loss,
fast loss, gain) as an external reference.

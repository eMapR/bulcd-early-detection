# Project State

Last updated: 2026-09-20

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
  monitoring/interface code exists yet — only integration scaffolding
  and Milestone 1's replay experiments (`experiments/`).

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

## Active problem

None — between milestones.

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

## Next steps

- Fire's second, smaller, unexplained detached detection patch (east of
  the lake) — not investigated.
- Harvest's road-correlated speckle pattern — worth a closer look before
  trusting spatial detections near linear features.
- `recency_factor` sweep against the production matrix hasn't been run
  yet.
- Interface/monitoring-system design remains undiscussed — needs
  explicit scoping with the user before implementation starts.

# BULC-D Early Detection

Early-detection/monitoring interface for land-cover, land-use, and
vegetation change generally (harvest, insect/disease, fire, beaver-related
change, clearing/development, recovery, etc.) — BULC-D detects spectral
change; cause attribution is a separate concern. Forest disturbance is
one specific use case/example, not the whole scope. Not yet built — this
repo currently contains only integration scaffolding around its core
dependency.

## Architecture

- This repo will hold the monitoring/interface layer only. It never
  contains detection logic.
- The Bayesian detection algorithm lives entirely in the separate
  **`eMapR/BULC-D_rebuild`** repo (sibling directory `../BULC-D_rebuild`
  on this machine), installed as the `bulcd` package. Treat it as an
  external dependency: import it, don't read through it, unless a task
  specifically requires understanding its internals.
  - Public API this project calls into: `bulcd.engine.run_bulcd`,
    `bulcd.bulc.run_bulc`, `bulcd.inputs.organize_inputs`,
    `bulcd.config.schema.BULCDConfig`.
  - BULC-D_rebuild's own docs (`../BULC-D_rebuild/CLAUDE.md`,
    `docs/decisions/`, `docs/findings.md`) are the source of truth for
    the algorithm. Don't duplicate them here — read them directly, and
    only the section relevant to the task at hand.
- Package layout: `src/bulcd_early_detection/` (src-layout, empty so
  far), `tests/`, `docs/`.

## Commands

```sh
pip install -e .              # this project only; leaves bulcd's install alone
pip install -e ../BULC-D_rebuild  # bulcd, editable, for co-development (do this too)
pip install -e ".[dev]"       # pytest
pytest                        # run tests (currently: dependency smoke test only)
```

## Constraints

- Never copy or modify BULC-D_rebuild's algorithm code into this repo.
- Don't add `bulcd` to this project's default `dependencies` in
  `pyproject.toml` — it's in the `engine` extra instead, because pip
  re-resolves direct git URLs on every install and would otherwise
  clobber a local editable `bulcd` checkout. See README "Relationship
  to BULC-D_rebuild" for the full reasoning.

## Where to find things

- `docs/PROJECT_STATE.md` — concise current status, active work, next
  steps. Read this before starting any task.
- `docs/findings.md` — running record of durable technical/experimental
  findings and their explanations (the "why"). Read this before
  re-deriving something that may already be known.
- `experiments/` — replay experiment scripts and their per-run outputs/
  findings notes (`experiments/output/`, `experiments/*_findings.md`).
- `README.md` — install instructions and the BULC-D_rebuild relationship.
- `tools/build_demo_notebooks.py` — generates all three demo notebooks
  (`notebooks/*.ipynb`) from one template. Edit it, not the notebooks
  (re-running overwrites hand edits), then re-execute the notebooks.
- `../BULC-D_rebuild/CLAUDE.md` — the detection engine's own docs.

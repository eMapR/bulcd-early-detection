# BULC-D Early Detection

An early-detection/monitoring interface for land-cover, land-use, and
vegetation change, built on top of the
[BULC-D](https://github.com/eMapR/BULC-D_rebuild) Bayesian
change-detection engine. BULC-D detects spectral change generally;
possible applications include harvest, insect/disease impacts, fire,
beaver-related landscape change, clearing/development, and vegetation
recovery — cause attribution is handled separately from detection.
Forest disturbance (e.g. wildfire) is one specific use case, not the
whole scope.

## Prototype notebook

`notebooks/early_detection_demo.ipynb` maps one season's change
(decrease / unchanged / increase) plus confidence, first-detection date,
and Sentinel-2 context imagery. It defaults to Apostle Islands National
Lakeshore (a precomputed Earth Engine asset). Set `USE_CUSTOM_AOI = True`
and an Earth Engine FeatureCollection asset ID to run live on your own
area.

```sh
pip install -e ".[notebook]"      # into the same env as bulcd
jupyter lab notebooks/early_detection_demo.ipynb
```

Reusable pieces live in `src/bulcd_early_detection/`: `config.py`
(simple controls -> full `BULCDConfig`), `outputs.py` (study area,
outcome layers, export/load), and `render.py` (static maps).

## Relationship to BULC-D_rebuild

This repo does **not** contain the detection algorithm. The Bayesian
BULC-D core lives in the separate
[`eMapR/BULC-D_rebuild`](https://github.com/eMapR/BULC-D_rebuild) repo
and is consumed here as an ordinary Python dependency (the `bulcd`
package, declared in `pyproject.toml`) - never copied or modified in
this repo.

`bulcd` is *not* in this project's default `dependencies` - pip
re-resolves a direct git dependency on every install, which would
otherwise silently clobber a local editable checkout every time you
run `pip install -e .`. Instead:

- **Co-developing the engine (the common case):** clone
  `BULC-D_rebuild` as a sibling directory and install it yourself,
  same as before:

  ```sh
  git clone git@github.com:eMapR/BULC-D_rebuild.git ../BULC-D_rebuild
  pip install -e ../BULC-D_rebuild
  pip install -e .
  ```

  `pip install -e .` alone never touches `bulcd`, so this local,
  editable link is safe to install in either order and stays intact.

- **From-scratch environment (CI, a new machine, no local
  `BULC-D_rebuild` checkout):** use the `engine` extra to pull `bulcd`
  straight from GitHub instead (`main` branch, over SSH - you'll need
  SSH access to that repo):

  ```sh
  pip install -e ".[engine]"
  ```

`tests/test_bulcd_dependency.py` is a smoke test that just confirms the
`bulcd` package (and the specific entry points this project expects to
call into, like `bulcd.engine.run_bulcd`) is importable.

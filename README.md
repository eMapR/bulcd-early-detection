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

`notebooks/early_detection_demo.ipynb` is a walkthrough of BULC-D with
Apostle Islands National Lakeshore (2026) as the example:

1. What BULC-D is (baseline, observations, Bayesian updating, outcomes).
2. Its important parameters, in plain terms, with the full config available.
3. The Apostle Islands result (precomputed asset): change map, area totals,
   confidence, first-detection timing, Sentinel-2 imagery, and a Devils
   Island close-up.
4. Parameter effects: one setting changed per map, all at the same
   Devils Island extent.
5. Try your own area: draw a polygon (ipyleaflet; saved as
   `notebooks/aois/<name>.geojson`) or use an Earth Engine
   FeatureCollection asset. Runs live.

Running it takes about 2 minutes. Drawing needs JupyterLab 4, Notebook 7
or VS Code.

`notebooks/north_cascades_demo.ipynb` is the same walkthrough for North
Cascades National Park (WDPA boundary, excluding Ross Lake and Lake
Chelan NRAs; precomputed asset), with a 23 km² comparison box in the
north unit for the parameter-effects section. Same default settings.

`notebooks/testsite_demo.ipynb` is the same walkthrough for a study area
supplied as an Earth Engine FeatureCollection
(`projects/bulcd-python-rebuild/assets/testsite`, one 26 km² polygon in
western Oregon; precomputed asset). It adds a side-by-side 2024 | 2025 |
2026 true-color Sentinel-2 comparison next to the change map, and uses the
whole site for the parameter-effects section. Same default settings.

```sh
pip install -e ".[notebook]"      # into the same env as bulcd
jupyter lab notebooks/early_detection_demo.ipynb
```

Reusable pieces live in `src/bulcd_early_detection/`: `config.py`
(simple controls -> full `BULCDConfig`), `outputs.py` (study area,
outcome layers, export/load), `render.py` (static maps), `drawing.py`
(drawn AOIs), `compare.py` (parameter comparison), and `report.py`
(notebook map/table helpers and the one-pixel teaching figure).

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

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

## Demonstration notebooks

Three notebooks show the same workflow on different landscapes. Each follows
the same five parts: what BULC-D / Early Detection is; setup and important
parameters; case-study results; understanding parameter behavior (one
setting at a time); and trying it on your own area.

| Notebook | Study area | Highlights |
|---|---|---|
| `notebooks/early_detection_demo.ipynb` | Apostle Islands National Lakeshore (WI) | Devils Island close-up |
| `notebooks/north_cascades_demo.ipynb` | North Cascades National Park (WA) | Large mountain park; clear single-date imagery around a mid-season change |
| `notebooks/testsite_demo.ipynb` | An Earth Engine FeatureCollection (26 km², western OR) | Small site; single clear dates for true color |

All three produce the same product suite:
- 2026 condition relative to expectation;
- first-detected season (independent 2024 / 2025 / 2026 runs against a fixed 2018–2023
  expectation) with the within-season date;
- a temporal NBR composite;
- annual true color;
- a pixel-history chart (observations vs. expectation, probability of decrease, first
  threshold crossing, periods above threshold), with the pixel marked on the maps;
- one-at-a-time parameter sensitivity maps and response curves.

**Interactive prototype:** `notebooks/early_detection_interactive.ipynb`. Draw or pick an area,
set expectation and monitoring periods, run, and click pixels to inspect them. It's a
functional prototype and specification for a future Early Detection interface; it runs live
in Earth Engine.

**Key terms.** A *decrease* in the 2026 condition map means the landscape is
below its expected condition **during 2026**. It doesn't by itself mean the
disturbance happened in 2026. *First detected season* is the first monitoring
season that BULC-D **finished** classified as decrease (a crossing it later
retracted doesn't count), dated by the first threshold crossing within that
season: detection timing, not a verified disturbance date.

```sh
pip install -e ".[notebook]"      # into the same env as bulcd
jupyter lab notebooks/early_detection_demo.ipynb
```

Main results are precomputed Earth Engine assets, so each notebook runs in
about 3–5 minutes. Drawing an area needs JupyterLab 4, Notebook 7 or VS Code.

**Maintaining the notebooks:** all three are generated from one template,
`tools/build_demo_notebooks.py`, so their structure and terminology stay in
sync. Edit the template, not the `.ipynb` files: re-running the script
overwrites hand edits. Then re-execute each notebook
(`jupyter nbconvert --to notebook --execute --inplace <name>.ipynb`
from `notebooks/`).

## Core BULC-D vs. Early Detection additions

The Bayesian method itself is BULC-D's, unchanged. Early Detection adds a
monitoring workflow, products and diagnostics around it.

- **Core BULC-D** (the legacy Google Earth Engine method, reimplemented in Python
  in `BULC-D_rebuild`):
  - seasonal expectation from baseline years;
  - departures as z-scores, and the evidence table (transition matrix);
  - Bayesian updating with levelers;
  - per-pixel probabilities of decrease / unchanged / increase;
  - the first-change (first threshold crossing) rule.
- **Early Detection additions** (this repo, around the unchanged method):
  - plain-language settings over the full configuration;
  - precomputed study-area runs and area summaries;
  - "condition relative to expectation" and "first detected" framing;
  - a first-detected-season product from independent annual runs against a
    fixed baseline, with the within-season date;
  - reference imagery: same-date multi-year panels, and a temporal NBR composite;
  - pixel-history charts;
  - one-at-a-time parameter sensitivity maps and charts;
  - drawn-area and FeatureCollection study areas.

## Toward an interactive interface

The notebooks are the current demonstration and reference workflow. The
longer-term goal is an interactive interface:

choose area → configure monitoring → run/view results → inspect detections → click a pixel to see its history.

Because intended users may not be able to install local software, Google
Earth Engine is the current likely deployment environment. That's the
current direction, not a final architecture decision.

Reusable pieces live in `src/bulcd_early_detection/`:

| Module | Purpose |
|---|---|
| `config.py` | Simple controls → full `BULCDConfig` |
| `outputs.py` | Study areas, products, exports, summaries, NBR composites |
| `render.py` | Maps |
| `report.py` | Notebook map and table helpers |
| `compare.py` | Sensitivity maps and response charts |
| `pixel.py` | Pixel history, usable from any (lon, lat) |
| `drawing.py` | Drawn areas |
| `app.py` | The interactive prototype (ipywidgets + ipyleaflet) |

## Runtime environment (Miniforge, e.g. on Windows)

`environment.yml` is a minimal **user** environment for the Python/Jupyter
workflow (the `bulcd` engine plus these notebooks and the interactive app):
conda-forge only, no test or notebook-generator tools. In a **Miniforge
Prompt**, with `BULC-D_rebuild` and `bulcd-early-detection` side by side in
one folder (outside OneDrive):

```bat
cd C:\path\to\bulcd-early-detection
conda env create -f environment.yml
conda activate bulcd
pip install --no-deps --no-build-isolation -e ..\BULC-D_rebuild -e .
earthengine authenticate
jupyter lab notebooks\early_detection_interactive.ipynb
```

(`mamba env create -f environment.yml` is equivalent; recent Miniforge
includes both.) The `pip` line downloads nothing: it links the two local
folders into the environment, so keep them where they are.

The notebooks call `ee.Initialize(project="bulcd-python-rebuild")`. Use a
Google Cloud project registered for Earth Engine that your account can use:
either be added to that project, or change the project name in the first
code cell.

**Behind an agency network (TLS inspection, proxies).**
- *Certificate errors* (`CondaSSLError`, `CERTIFICATE_VERIFY_FAILED`) usually
  mean HTTPS is inspected and re-signed with an agency root certificate that
  conda and Python don't trust. Get that root certificate (`.pem`) from IT.
  - Build a combined bundle: the environment's `certifi` bundle with the
    agency certificate appended. A bundle holding only the agency
    certificate breaks sites that aren't inspected.
  - Point conda at the bundle: `conda config --set ssl_verify C:\path\bundle.pem`.
  - Point Python and Earth Engine at it inside the environment:
    `conda env config vars set SSL_CERT_FILE=C:\path\bundle.pem REQUESTS_CA_BUNDLE=C:\path\bundle.pem HTTPLIB2_CA_CERTS=C:\path\bundle.pem -n bulcd`.
    Then reactivate. The Earth Engine client uses `httplib2`, which ignores
    the Windows certificate store and needs `HTTPLIB2_CA_CERTS`.
  - Don't turn verification off (`ssl_verify false`).
- *Proxy*: if one is required, set `HTTPS_PROXY`/`HTTP_PROXY` (and
  `proxy_servers` in `.condarc` for conda).
- *Sites that must be reachable*:
  - `conda.anaconda.org`: conda-forge, during setup only.
  - `accounts.google.com` and `oauth2.googleapis.com`: sign-in.
  - `earthengine.googleapis.com`: computation and map tiles.
  - The interactive map's basemap tile servers, if those are blocked, the
    basemap is blank but the Earth Engine layers still draw.
- *Sign-in*: `earthengine authenticate` opens a browser and returns to a
  `localhost` address. If that is blocked, run it in a notebook as
  `ee.Authenticate(auth_mode="notebook")` and paste the code it gives you.
  An agency-managed Google account may also need Earth Engine enabled by
  its administrator.

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

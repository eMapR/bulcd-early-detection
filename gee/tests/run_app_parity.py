"""GEE app <-> Python app parity for Milestone 1 (the fixed reference case).

Runs gee/app.js under Node (tests/app_extract.js, stub `ui`), clicks each
reference pixel, and compares with the Python app's own code on the same case:

- config.js REFERENCE_CASE.bulcd is BULC-D_rebuild's legacy_reference() config
  (gee/tests/cases.py), so the engine underneath is the one held to JS <-> Python
  parity there (gee/tests/run_parity.py);
- inspector rows (dates, observed/expected NBR, z-score, supported class,
  P(decrease/unchanged/increase)) == pixel.pixel_history() at pixels 1-3, and
  the probability chart plots exactly those values at those dates;
- outputs.js classification == outputs._outcome_from_result() over a 30 m box.

Run from the bulcd env: cd gee/tests && python run_app_parity.py   (~10 min)
Node and bulcd.js come from ../../BULC-D_rebuild/gee (BULCD_GEE overrides).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import ee

HERE = Path(__file__).parent
BULCD_GEE = Path(os.environ.get("BULCD_GEE", HERE.parents[2] / "BULC-D_rebuild" / "gee"))
NODE = os.environ.get("BULCD_NODE", "/Users/clarype/miniconda3/envs/bulcd-gee/bin/node")
TOL = 1e-6
BOX = [-123.5725, 44.8300, -123.5400, 44.8500]
NUMERIC = ("observed", "expected", "zscore", "decrease", "unchanged", "increase")

sys.path.insert(0, str(BULCD_GEE / "tests"))
from cases import legacy_reference  # noqa: E402


def python_side(pixels):
    import dataclasses

    from bulcd.engine import run_bulcd
    from bulcd_early_detection import outputs, pixel

    cfg = legacy_reference()
    rows = {label: pixel.pixel_history(cfg, lon, lat) for label, (lon, lat) in pixels.items()}
    outcome = outputs._outcome_from_result(run_bulcd(cfg), cfg, 0.5).select("outcome")
    box = ee.ImageCollection([outcome.set("system:time_start", 0)]).getRegion(
        ee.Geometry.Rectangle(BOX), 30, "EPSG:32610").getInfo()
    return dataclasses.asdict(cfg), rows, box


def subset_mismatches(js, py, where="config"):
    """Every key bulcd.js sees must equal the Python config's value."""
    if isinstance(js, dict):
        if not isinstance(py, dict):
            return [f"{where}: {js!r} vs {py!r}"]
        return [m for k, v in js.items()
                for m in (subset_mismatches(v, py[k], f"{where}.{k}") if k in py else [f"{where}.{k}: not in Python"])]
    if isinstance(js, list):
        if not isinstance(py, list) or len(js) != len(py):
            return [f"{where}: {js!r} vs {py!r}"]
        return [m for i, (a, b) in enumerate(zip(js, py)) for m in subset_mismatches(a, b, f"{where}[{i}]")]
    if isinstance(js, (int, float)) and isinstance(py, (int, float)) and not isinstance(js, bool):
        return [] if abs(js - py) <= TOL else [f"{where}: {js} vs {py}"]
    return [] if js == py else [f"{where}: {js!r} vs {py!r}"]


def num_close(a, b):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= TOL)


def main():
    ee.Initialize(project="bulcd-python-rebuild")
    with tempfile.TemporaryDirectory() as tmp:
        js_out = Path(tmp) / "js.json"
        proc = subprocess.Popen([NODE, str(HERE / "app_extract.js"), str(js_out)], cwd=HERE,
                                env={**os.environ, "BULCD_GEE": str(BULCD_GEE)})
        # Pixel coordinates come from config.js via a tiny Node read, so both sides use the same numbers.
        ref = json.loads(subprocess.check_output(
            [NODE, "-e", "console.log(JSON.stringify(require('../config.js').REFERENCE_CASE.reference_pixels))"],
            cwd=HERE))
        pixels = {p["label"]: (p["lon"], p["lat"]) for p in ref}
        py_cfg, py_rows, py_box = python_side(pixels)
        if proc.wait() != 0:
            sys.exit("app_extract.js failed")
        js = json.loads(js_out.read_text())

    failures = subset_mismatches(js["config"], py_cfg)
    print(f"config.js == legacy_reference(): {'yes' if not failures else 'NO'}")

    for label, rows in py_rows.items():
        j = js["pixels"][label]
        bad = []
        if len(j["rows"]) != len(rows):
            bad.append(f"{len(j['rows'])} JS rows vs {len(rows)} Python rows")
        for jr, pr in zip(j["rows"], rows):
            if jr["date"] != str(pr["date"]) or jr["supports"] != pr["supports"] or \
                    not all(num_close(jr[k], pr[k]) for k in NUMERIC):
                bad.append(f"{jr['date']}: JS {jr} vs Python {pr}")
        expected_chart = [[r[c] for c in ("decrease", "unchanged", "increase")] + [0.5] for r in j["rows"]]
        if j["prob_table"] != expected_chart or j["fit_table_rows"] != len(j["rows"]):
            bad.append("chart tables do not hold the inspector rows")
        n_obs = sum(r["zscore"] is not None for r in rows)
        print(f"{label}: {len(rows)} rows ({n_obs} observations), final "
              f"{'/'.join(f'{rows[-1][c]:.3f}' for c in ('decrease', 'unchanged', 'increase'))} - "
              f"{'match' if not bad else f'{len(bad)} MISMATCHES'}")
        for note in j["notes"]:
            print(f"    {note}")
        failures += [f"{label}: {b}" for b in bad[:5]]

    def keyed(region):
        h = region[0]
        i, x, y = h.index("outcome"), h.index("longitude"), h.index("latitude")
        return {(round(r[x], 7), round(r[y], 7)): r[i] for r in region[1:]}

    jb, pb = keyed(js["outcome_box"]), keyed(py_box)
    diff = [k for k in set(jb) | set(pb) if jb.get(k) != pb.get(k)]
    counts = {v: sum(1 for x in pb.values() if x == v) for v in sorted({x for x in pb.values() if x is not None})}
    print(f"classification box: {len(pb)} pixels, classes {counts}, {len(diff)} differ")
    failures += [f"outcome at {k}: JS {jb.get(k)} vs Python {pb.get(k)}" for k in diff[:5]]
    print(f"UI: map layers {js['ui']['map_layers']}")

    if failures:
        print("\nAPP PARITY FAILED")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("\nAPP PARITY PASSED")


if __name__ == "__main__":
    main()

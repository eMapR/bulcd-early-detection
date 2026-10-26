"""Batch-export benchmark (docs/regional_plan.md, step 8): time, EECU and
memory failures of one regional tile across expectation sensors x expectation
length x shardSize. Everything else is the pilot run's.

    python experiments/regional_benchmark.py submit [--tile r0056c0034]
    python experiments/regional_benchmark.py collect

submit: starts one export per variant (all at once, so the timestamps also
show how many tasks the project runs concurrently) into
projects/bulcd-python-rebuild/assets/regional_bench/<variant run_id>/<tile>,
and records the task IDs in experiments/output/regional_benchmark/tasks.json.

collect: task states, queue and run times, EECU-seconds, errors ->
results.json; and, for completed tasks, whether outputs that should be
identical are: the baseline vs the pilot's own tile (rerun determinism), and
every shardSize variant vs the same settings at the default shardSize.
"""

import argparse
import dataclasses
import datetime
import json
import sys
from pathlib import Path

import ee

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bulcd_early_detection.regional import spec  # noqa: E402
from bulcd_early_detection.regional.backends import gee  # noqa: E402
from bulcd_early_detection.regional.run_config import RegionalRun  # noqa: E402

PILOT = ROOT / "regional_runs" / "pilot_coast_range_2026.yaml"
ASSET_ROOT = "projects/bulcd-python-rebuild/assets/regional_bench"
OUT = ROOT / "experiments" / "output" / "regional_benchmark"

# name: (expectation sensors, first year, last year, shardSize or None = EE's default 256)
VARIANTS = {
    "l8-6y": (("L8",), 2018, 2023, None),          # the pilot's settings
    "l8-6y-s64": (("L8",), 2018, 2023, 64),
    "l8-8y": (("L8",), 2016, 2023, None),
    "l8-10y": (("L8",), 2014, 2023, None),
    "l8s2-2y": (("L8", "S2"), 2022, 2023, None),
    "l8s2-4y": (("L8", "S2"), 2020, 2023, None),
    "l8s2-6y": (("L8", "S2"), 2018, 2023, None),
    "l8s2-6y-s128": (("L8", "S2"), 2018, 2023, 128),
    "l8s2-6y-s64": (("L8", "S2"), 2018, 2023, 64),
    "l8l9s2-6y": (("L8", "L9", "S2"), 2018, 2023, None),
    "l8l9s2-6y-s64": (("L8", "L9", "S2"), 2018, 2023, 64),
}


def variant_run(pilot: RegionalRun, name: str) -> RegionalRun:
    sensors, first, last, _ = VARIANTS[name]
    controls = dataclasses.replace(pilot.controls, expectation_sensors=sensors, baseline_first_year=first,
                                   baseline_last_year=last)
    return dataclasses.replace(pilot, run_id=f"bench-{name}", controls=controls,
                               description=f"Step 8 benchmark variant {name} of {pilot.run_id}")


def submit(tile_id: str):
    pilot = RegionalRun.load(PILOT)
    tile = next(t for t in pilot.tiles if t.id == tile_id)
    gee.outputs.ensure_folder(ASSET_ROOT)
    tasks = {}
    for name, (*_, shard) in VARIANTS.items():
        run = variant_run(pilot, name)
        gee.ensure_collection(run, ASSET_ROOT)
        task = gee.export_tile(run, tile, ASSET_ROOT, shard_size=shard)
        tasks[name] = {"task_id": task.id, "asset": f"{gee.collection_id(run, ASSET_ROOT)}/{tile.id}",
                       "shard_size": shard, "warnings": run.warnings()}
        print("started", name, task.id)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "tasks.json").write_text(json.dumps({"tile": tile_id, "submitted": datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds"), "variants": tasks}, indent=1))


def _identical(a: str, b: str) -> dict:
    """Pixels whose value or mask differs, per band, over asset a's footprint."""
    A, B = ee.Image(a), ee.Image(b)
    proj = A.select("condition").projection()
    diff = ee.Image.cat([A.select(n).unmask(-1).neq(B.select(n).unmask(-1)).rename(n) for n in spec.BAND_NAMES])
    return diff.reduceRegion(ee.Reducer.sum(), A.geometry(), crs=proj, maxPixels=1e9)


def collect():
    meta = json.loads((OUT / "tasks.json").read_text())
    ids = {v["task_id"]: name for name, v in meta["variants"].items()}
    status = {ids[t["id"]]: t for t in ee.data.getTaskList() if t["id"] in ids}
    rows = {}
    for name, v in meta["variants"].items():
        t = status.get(name, {})
        ms = lambda k: t.get(k)
        created, started, updated = ms("creation_timestamp_ms"), ms("start_timestamp_ms"), ms("update_timestamp_ms")
        rows[name] = {
            "sensors": VARIANTS[name][0], "years": VARIANTS[name][2] - VARIANTS[name][1] + 1,
            "shard_size": v["shard_size"] or 256, "state": t.get("state"),
            "queued_s": (started - created) / 1000 if started and created else None,
            "running_s": (updated - started) / 1000 if started and updated and t.get("state") in (
                "COMPLETED", "FAILED") else None,
            "start_utc": started and datetime.datetime.fromtimestamp(started / 1000, datetime.timezone.utc)
                         .isoformat(timespec="seconds"),
            "end_utc": updated and datetime.datetime.fromtimestamp(updated / 1000, datetime.timezone.utc)
                       .isoformat(timespec="seconds"),
            "eecu_s": t.get("batch_eecu_usage_seconds"), "error": t.get("error_message"),
            "asset": v["asset"],
        }
    done = {n for n, r in rows.items() if r["state"] == "COMPLETED"}
    pilot = RegionalRun.load(PILOT)
    checks = {}
    if "l8-6y" in done:
        checks["l8-6y vs pilot tile"] = _identical(
            rows["l8-6y"]["asset"], f"{gee.collection_id(pilot)}/{meta['tile']}")
    for name in done:
        base = name.rsplit("-s", 1)[0] if VARIANTS[name][3] else None
        if base and base in done:
            checks[f"{name} vs {base}"] = _identical(rows[name]["asset"], rows[base]["asset"])
    result = {"tile": meta["tile"], "submitted": meta["submitted"], "variants": rows,
              "identical_checks": ee.Dictionary(checks).getInfo() if checks else {}}
    (OUT / "results.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("submit", "collect"))
    p.add_argument("--tile", default="r0056c0034")
    a = p.parse_args()
    ee.Initialize(project="bulcd-python-rebuild")
    submit(a.tile) if a.mode == "submit" else collect()


if __name__ == "__main__":
    sys.exit(main())

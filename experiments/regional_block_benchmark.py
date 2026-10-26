"""Export optimization benchmark: several tiles per export task vs one tile
per task (docs/regional_plan.md). Same grid, same tiles' pixels, same
algorithm and settings (the pilot's); only how many tiles one task computes
changes. A block task runs BULC-D once on the block's AOI and writes one asset
covering exactly its tiles' pixels (tiling is exact per pixel:
docs/findings.md 2026-10-24).

    python experiments/regional_block_benchmark.py run        # all phases, one after another
    python experiments/regional_block_benchmark.py collect

Area: the 4 x 4 tiles r0055-r0058 x c0033-c0036 (the pilot is its center 2 x 2).
Phases, each submitted only after the previous one finished, so they don't
compete for the project's task slots:
  block4  1 task  of 16 tiles (1332 x 1332 px)
  block2  4 tasks of 4 tiles  (666 x 666 px)
  single  16 tasks of 1 tile  (333 x 333 px)
Assets: projects/bulcd-python-rebuild/assets/regional_bench/bench-blocks-<phase>/.

collect: per task and per phase (makespan from submission to the last task's
end, EECU, tiles per hour), and output equivalence: every block asset vs the
single-tile assets on each of its tiles (all bands, masks included), and the
pilot's four single tiles vs the pilot's own tiles (2026-10-22/23 exports).
Writes experiments/output/regional_benchmark/blocks.json.
"""

import argparse
import dataclasses
import datetime
import json
import sys
import time
from pathlib import Path

import ee

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bulcd_early_detection.regional import spec  # noqa: E402
from bulcd_early_detection.regional.backends import gee  # noqa: E402
from bulcd_early_detection.regional.run_config import Region, RegionalRun  # noqa: E402
from bulcd_early_detection.regional.tiling import lonlat_ring  # noqa: E402

PILOT = ROOT / "regional_runs" / "pilot_coast_range_2026.yaml"
ASSET_ROOT = "projects/bulcd-python-rebuild/assets/regional_bench"
OUT = ROOT / "experiments" / "output" / "regional_benchmark"
STATE = OUT / "blocks_tasks.json"
ROWS, COLS = range(55, 59), range(33, 37)
PHASES = {"block4": 4, "block2": 2, "single": 1}   # tiles per block side


def area_run(phase: str) -> RegionalRun:
    pilot = RegionalRun.load(PILOT)
    tiles = [pilot.grid.tile(r, c) for r in ROWS for c in COLS]
    bounds = (min(t.bounds[0] for t in tiles), min(t.bounds[1] for t in tiles),
              max(t.bounds[2] for t in tiles), max(t.bounds[3] for t in tiles))
    return dataclasses.replace(pilot, run_id=f"bench-blocks-{phase}", region=Region("4 x 4 around the pilot", bounds),
                               description=f"Export optimization benchmark, phase {phase}")


def blocks(run: RegionalRun, side: int) -> dict[str, list]:
    """{block id: its tiles} - side x side tiles each, on the tile grid."""
    out = {}
    for r0 in ROWS[::side]:
        for c0 in COLS[::side]:
            tiles = [run.grid.tile(r, c) for r in range(r0, r0 + side) for c in range(c0, c0 + side)]
            out[tiles[0].id if side == 1 else f"{tiles[0].id}_{side}x{side}"] = tiles
    return out


def block_bounds(tiles) -> tuple[float, float, float, float]:
    return (min(t.bounds[0] for t in tiles), min(t.bounds[1] for t in tiles),
            max(t.bounds[2] for t in tiles), max(t.bounds[3] for t in tiles))


def export_block(run: RegionalRun, block_id: str, tiles):
    """One task: BULC-D on the block's AOI, the block's pixels, export_tile()'s parameters."""
    x0, y0, x1, y1 = bounds = block_bounds(tiles)
    s = run.grid.scale
    config = run.bulcd_config(aoi_coordinates=lonlat_ring(run.grid, bounds))
    props = gee.tile_properties(run, tiles[0], config) | {
        "tile_id": block_id, "tile_ids": ",".join(t.id for t in tiles),
        "grid_json": json.dumps({"crs": run.grid.crs, "transform": [s, 0, x0, 0, -s, y1],
                                 "dimensions": f"{round((x1 - x0) / s)}x{round((y1 - y0) / s)}"})}
    task = ee.batch.Export.image.toAsset(
        image=gee.product_image(run, config).set(props),
        description=f"{run.run_id}_{block_id}",
        assetId=f"{gee.collection_id(run, ASSET_ROOT)}/{block_id}",
        crs=run.grid.crs,
        crsTransform=[s, 0, x0, 0, -s, y1],
        dimensions=f"{round((x1 - x0) / s)}x{round((y1 - y0) / s)}",
        pyramidingPolicy={".default": "sample"},
        maxPixels=1e10,
    )
    task.start()
    return task


def run_phases():
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    for phase, side in PHASES.items():
        if phase in state:
            continue
        run = area_run(phase)
        gee.ensure_collection(run, ASSET_ROOT)
        submitted = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        tasks = {b: export_block(run, b, tiles).id for b, tiles in blocks(run, side).items()}
        print(phase, "submitted", len(tasks), flush=True)
        while True:
            states = {t["id"]: t["state"] for t in ee.data.getTaskList() if t["id"] in tasks.values()}
            if len(states) == len(tasks) and all(s in ("COMPLETED", "FAILED", "CANCELLED") for s in states.values()):
                break
            time.sleep(60)
        print(phase, "done", states, flush=True)
        state[phase] = {"submitted": submitted, "tasks": tasks}
        OUT.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=1))


def _ts(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)


def collect():
    state = json.loads(STATE.read_text())
    status = {t["id"]: t for t in ee.data.getTaskList()}
    report = {"phases": {}, "equivalence": {}}
    for phase, s in state.items():
        rows = {}
        for b, tid in s["tasks"].items():
            t = status[tid]
            rows[b] = {"state": t["state"], "queued_s": (t["start_timestamp_ms"] - t["creation_timestamp_ms"]) / 1000,
                       "running_s": (t["update_timestamp_ms"] - t["start_timestamp_ms"]) / 1000,
                       "eecu_s": t.get("batch_eecu_usage_seconds"), "error": t.get("error_message")}
        ends = [_ts(status[tid]["update_timestamp_ms"]) for tid in s["tasks"].values()]
        makespan = (max(ends) - datetime.datetime.fromisoformat(s["submitted"])).total_seconds()
        n_tiles = PHASES[phase] ** 2 * len(rows)
        eecu = sum(r["eecu_s"] or 0 for r in rows.values())
        report["phases"][phase] = {
            "tasks": len(rows), "tiles": n_tiles, "makespan_s": makespan, "tiles_per_hour": n_tiles / makespan * 3600,
            "eecu_s": eecu, "eecu_s_per_tile": eecu / n_tiles,
            "running_s_sum": sum(r["running_s"] for r in rows.values()), "tasks_detail": rows}

    # Equivalence on every tile: each block phase's asset vs the single-tile asset.
    single = area_run("single")
    checks = {}
    for phase in ("block4", "block2"):
        run = area_run(phase)
        for b, tiles in blocks(run, PHASES[phase]).items():
            block = ee.Image(f"{gee.collection_id(run, ASSET_ROOT)}/{b}")
            for t in tiles:
                checks[f"{phase} {b} : {t.id}"] = _differ(block, ee.Image(f"{gee.collection_id(single, ASSET_ROOT)}/{t.id}"),
                                                          single, t)
    pilot = RegionalRun.load(PILOT)
    for t in pilot.tiles:
        checks[f"single {t.id} : pilot"] = _differ(ee.Image(f"{gee.collection_id(single, ASSET_ROOT)}/{t.id}"),
                                                   ee.Image(f"{gee.collection_id(pilot)}/{t.id}"), pilot, t)
    result = ee.Dictionary(checks).getInfo()
    report["equivalence"] = {k: {b: n for b, n in v.items() if n} or "identical" for k, v in result.items()}
    report["all_identical"] = all(v == "identical" for v in report["equivalence"].values())
    out = OUT / "blocks.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({p: {k: v for k, v in r.items() if k != "tasks_detail"} for p, r in report["phases"].items()},
                     indent=1))
    print("all identical:", report["all_identical"], f"({len(checks)} comparisons) ->", out)


def _differ(a: ee.Image, b: ee.Image, run: RegionalRun, tile) -> ee.Dictionary:
    """Pixels whose value or mask differs, per band, on the tile's pixels."""
    diff = ee.Image.cat([a.select(n).unmask(-1).neq(b.select(n).unmask(-1)).rename(n) for n in spec.BAND_NAMES])
    return diff.reduceRegion(ee.Reducer.sum().unweighted(),
                             ee.Geometry.Rectangle(list(tile.bounds), run.grid.crs, False),
                             crs=run.grid.crs, crsTransform=run.grid.transform, maxPixels=1e9)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("run", "collect"))
    a = p.parse_args()
    ee.Initialize(project="bulcd-python-rebuild")
    run_phases() if a.mode == "run" else collect()


if __name__ == "__main__":
    sys.exit(main())

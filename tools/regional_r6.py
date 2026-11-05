"""R6 seven-ecoregion regional processing (docs/regional_plan.md, "Next run").

    python tools/regional_r6.py plan                  # tiles per ecoregion -> run files (needs the study-area assets)
    python tools/regional_r6.py submit ECO [ECO ...]  # the three season runs' blocks
    python tools/regional_r6.py drive                 # loop: submit, stack, retry, report (run under nohup)
    python tools/regional_r6.py status

Run files: regional_runs/r6_ecoregions/<eco>_<year>.yaml (the pilot's settings
with the 2026-11-04 changes: L8 + L9 expectation, full year; plus the LCMS
forest mask, the ecoregion, its tiles and 2 x 2 blocks). Task records:
regional_runs/r6_ecoregions/tasks.json (every submitted task, its unit and
state). Log: regional_runs/r6_ecoregions/drive.log.

Tiles: every 333-px tile on the run grid holding at least one forest pixel
(FOREST_ASSET = 1) of the ecoregion; blocks: the aligned 2 x 2 blocks
containing them (tiling.Grid.blocks).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

import ee

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bulcd_early_detection.regional.backends import gee  # noqa: E402
from bulcd_early_detection.regional.backends import study_area as sa  # noqa: E402
from bulcd_early_detection.regional.run_config import (AdvancedSettings, Region, RegionalRun,  # noqa: E402
                                                       app_default_controls)
from bulcd_early_detection.regional.tiling import Grid  # noqa: E402

OUT = ROOT / "regional_runs" / "r6_ecoregions"
TASKS = OUT / "tasks.json"
LOG = OUT / "drive.log"
YEARS = (2024, 2025, 2026)
ORDER = [1, 11, 77, 9, 4, 15, 78]   # Coast Range first, then the user's order
BLOCK = 2
MAX_ACTIVE = 2000                   # queued + running tasks we allow ourselves (EE's queue limit is 3000)
MAX_ATTEMPTS = 3
QUOTA_STOP = 0.85                   # stop submitting above this fraction of the asset-size quota
FIRST_OK = 8                        # Coast Range season tasks that must complete (none failed) before the others start


def name(code: int) -> str:
    return sa.ECOREGIONS[code][0]


def run_path(code: int, year: int) -> Path:
    return OUT / f"{name(code)}_{year}.yaml"


def make_run(code: int, year: int, tiles: list[str], bounds) -> RegionalRun:
    """The pilot's settings (regional_runs/pilot_coast_range_2026.yaml) with the
    plan's changes: expectation L8 + L9, full year (DOY 1-362 in 2025/2026, 1-363
    in leap 2024: one MM-DD for every season, as the stack requires), LCMS forest
    mask, the ecoregion, 2 x 2 blocks."""
    controls = app_default_controls(monitoring_year=year, season_start="01-01", season_end="12-28",
                                    baseline_first_year=2018, baseline_last_year=2023, decision_threshold=0.65,
                                    increase_threshold=0.75, sensitivity=1.0, fit_order=1,
                                    expectation_sensors=("L8", "L9"))
    advanced = AdvancedSettings(monitoring_sensors=("L8", "L9"), dampening=0.7, posterior_leveler=0.9,
                                mask_forest=True, mask_water=True, forest_mask_asset=sa.FOREST_ASSET,
                                timing_rule="confirmed")
    return RegionalRun(
        run_id=f"r6-{name(code)}-{year}",
        description=(f"R6 seven-ecoregion run: {sa.ECOREGIONS[code][1]} (us_l3code {code}) in OR/WA, season {year}. "
                     "Pilot settings + L8/L9 expectation + full year + LCMS 2023 forest mask (docs/regional_plan.md)."),
        region=Region(name=f"{sa.ECOREGIONS[code][1]}, Oregon + Washington", bounds=bounds, ecoregion=code,
                      tiles=tiles),
        controls=controls, advanced=advanced, grid=Grid(), block_tiles=BLOCK)


def log(msg: str) -> None:
    line = f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- plan
def plan_tiles(code: int, grid: Grid) -> list[str]:
    region = sa.ecoregion_features().filter(ee.Filter.eq("code", code)).geometry().intersection(
        sa.states_geometry(), ee.ErrorMargin(30))
    (x0, y0), _, (x1, y1), _ = region.bounds(30, grid.crs).coordinates().getInfo()[0][:4]
    candidates = grid.tiles(grid.snap((x0, y0, x1, y1)))
    forest = ee.Image(sa.FOREST_ASSET).eq(1).updateMask(sa.region_mask(code)).unmask(0).rename("forest")
    found = []
    for i in range(0, len(candidates), 200):
        chunk = candidates[i:i + 200]
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(list(t.bounds), grid.crs, False), {"id": t.id})
                                   for t in chunk])
        sums = forest.reduceRegions(fc, ee.Reducer.sum().unweighted(), crs=grid.crs, crsTransform=grid.transform)
        found += [f["properties"]["id"] for f in sums.getInfo()["features"] if f["properties"].get("sum", 0) > 0]
    return found


def plan(codes) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    grid = Grid()
    summary = json.loads((OUT / "plan.json").read_text()) if (OUT / "plan.json").exists() else {}
    for code in codes:
        tiles = plan_tiles(code, grid)
        blocks = grid.blocks([t for t in grid.tiles(_bbox(grid, tiles)) if t.id in set(tiles)], BLOCK)
        bounds = (min(b.bounds[0] for b in blocks), min(b.bounds[1] for b in blocks),
                  max(b.bounds[2] for b in blocks), max(b.bounds[3] for b in blocks))
        for year in YEARS:
            run = make_run(code, year, tiles, bounds)
            header = (f"# {run.description}\n# Generated by tools/regional_r6.py plan ({datetime.date.today()}); "
                      f"{len(tiles)} tiles with LCMS forest, {len(run.units)} 2 x 2 blocks.\n")
            run_path(code, year).write_text(header + run.to_yaml())
            RegionalRun.load(run_path(code, year))   # round-trip check
        summary[name(code)] = {"us_l3code": code, "tiles": len(tiles), "blocks": len(blocks),
                               "tiles_in_blocks": len(blocks) * BLOCK ** 2}
        log(f"plan {name(code)}: {len(tiles)} tiles, {len(blocks)} blocks")
    (OUT / "plan.json").write_text(json.dumps(summary, indent=1))


def _bbox(grid: Grid, tile_ids: list[str]):
    rc = [(int(t[1:5]), int(t[6:10])) for t in tile_ids]
    a, b = grid.tile(min(r for r, _ in rc), min(c for _, c in rc)), grid.tile(max(r for r, _ in rc), max(c for _, c in rc))
    return (a.bounds[0], b.bounds[1], b.bounds[2], a.bounds[3])


# ---------------------------------------------------------------- tasks
def load_tasks() -> dict:
    return json.loads(TASKS.read_text()) if TASKS.exists() else {}


def save_tasks(tasks: dict) -> None:
    tmp = TASKS.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, indent=1, sort_keys=True))
    tmp.replace(TASKS)


def key(run_id: str, unit: str, kind: str) -> str:
    return f"{kind}:{run_id}/{unit}"


def submit_seasons(code: int, tasks: dict, budget: int) -> int:
    """Submits the ecoregion's season blocks not yet submitted (or failed, < MAX_ATTEMPTS)."""
    n = 0
    runs = [RegionalRun.load(run_path(code, y)) for y in YEARS]
    for r in runs:
        gee.ensure_collection(r)
    for unit in runs[0].units:      # block-major: a block's three seasons together, so stacks can follow
        for r in runs:
            k = key(r.run_id, unit.id, "season")
            rec = tasks.get(k)
            if rec and (rec["state"] != "FAILED" or rec["attempts"] >= MAX_ATTEMPTS):
                continue
            if rec and _asset_exists(f"{gee.collection_id(r)}/{unit.id}"):
                rec["state"] = "COMPLETED"
                continue
            if n >= budget:
                return n
            task = gee.export_tile(r, unit)
            tasks[k] = {"task_id": task.id, "state": "SUBMITTED", "attempts": (rec or {}).get("attempts", 0) + 1,
                        "submitted": _now(), "ecoregion": code}
            n += 1
            if n % 25 == 0:
                save_tasks(tasks)
    save_tasks(tasks)
    return n


def submit_stacks(code: int, tasks: dict, budget: int) -> int:
    """Submits the stack of every block whose three season tasks completed."""
    n = 0
    runs = [RegionalRun.load(run_path(code, y)) for y in YEARS]
    final, earlier = runs[-1], runs[:-1]
    created = False
    for unit in final.units:
        if not all(tasks.get(key(r.run_id, unit.id, "season"), {}).get("state") == "COMPLETED" for r in runs):
            continue
        k = key(final.run_id, unit.id, "stack")
        rec = tasks.get(k)
        if rec and (rec["state"] != "FAILED" or rec["attempts"] >= MAX_ATTEMPTS):
            continue
        if n >= budget:
            break
        if not created:
            path = gee.stack_collection_id(final)
            if not _asset_exists(path):
                ee.data.createAsset({"type": "IMAGE_COLLECTION"}, path)
            created = True
        task = gee.export_stack_tile(final, earlier, unit)
        tasks[k] = {"task_id": task.id, "state": "SUBMITTED", "attempts": (rec or {}).get("attempts", 0) + 1,
                    "submitted": _now(), "ecoregion": code}
        n += 1
    save_tasks(tasks)
    return n


def refresh(tasks: dict) -> dict:
    """Updates task states from Earth Engine; returns the EE task list by id."""
    by_id = {t["id"]: t for t in ee.data.getTaskList()}
    for k, rec in tasks.items():
        t = by_id.get(rec["task_id"])
        if t is None or rec["state"] in ("COMPLETED",) and "eecu_s" in rec:
            continue
        state = t["state"]
        rec["state"] = {"READY": "SUBMITTED", "RUNNING": "RUNNING"}.get(state, state)
        if state in ("COMPLETED", "FAILED", "CANCELLED"):
            rec["eecu_s"] = t.get("batch_eecu_usage_seconds")
            rec["ended"] = t.get("update_timestamp_ms")
            if state == "FAILED":
                rec["error"] = t.get("error_message")
            if state == "CANCELLED":
                rec["state"] = "FAILED"
                rec["error"] = "cancelled"
    save_tasks(tasks)
    return by_id


def quota() -> dict:
    q = ee.data.getAssetRootQuota(f"projects/{sa.PROJECT}/assets/")
    return {"bytes": int(q["asset_size"]["usage"]), "bytes_limit": int(q["asset_size"]["limit"]),
            "assets": int(q["asset_count"]["usage"]), "assets_limit": int(q["asset_count"]["limit"])}


def summary(tasks: dict) -> dict:
    out = {}
    for k, rec in tasks.items():
        kind, rest = k.split(":", 1)
        s = out.setdefault(f"{name(rec['ecoregion'])} {kind}", {})
        s[rec["state"]] = s.get(rec["state"], 0) + 1
    for k, rec in tasks.items():
        s = out[f"{name(rec['ecoregion'])} {k.split(':')[0]}"]
        s["eecu_h"] = round(s.get("eecu_h", 0) + (rec.get("eecu_s") or 0) / 3600, 2)
    return out


def errors(tasks: dict) -> list[str]:
    return [f"{k} (attempt {r['attempts']}): {r.get('error')}" for k, r in tasks.items() if r["state"] == "FAILED"]


def coast_ok(tasks: dict) -> bool:
    season = [r for k, r in tasks.items() if r["ecoregion"] == 1 and k.startswith("season:")]
    done = sum(r["state"] == "COMPLETED" for r in season)
    hard_fail = [r for r in season if r["state"] == "FAILED"]
    return done >= FIRST_OK and not hard_fail


def drive(interval: int) -> None:
    log("drive: start")
    while True:
        tasks = load_tasks()
        by_id = refresh(tasks)
        active = sum(t["state"] in ("READY", "RUNNING") for t in by_id.values())
        q = quota()
        budget = MAX_ACTIVE - active
        if q["bytes"] > QUOTA_STOP * q["bytes_limit"] or q["assets"] > QUOTA_STOP * q["assets_limit"]:
            log(f"STORAGE: asset usage {q} above {QUOTA_STOP:.0%} of quota; not submitting. Nothing deleted.")
            budget = 0
        allowed = [1] + (ORDER[1:] if coast_ok(tasks) else [])
        for code in allowed:
            if budget <= 0:
                break
            if not run_path(code, YEARS[0]).exists():
                continue
            n = submit_seasons(code, tasks, budget)
            budget -= n
            m = submit_stacks(code, tasks, budget)
            budget -= m
            if n or m:
                log(f"submitted {name(code)}: {n} season, {m} stack tasks")
        s = summary(tasks)
        log(f"status active={active} quota={q['bytes'] / 1e9:.2f}/{q['bytes_limit'] / 1e9:.0f} GB "
            f"{q['assets']}/{q['assets_limit']} assets; {json.dumps(s)}")
        for e in errors(tasks):
            log(f"ERROR {e}")
        expected = sum(len(RegionalRun.load(run_path(c, YEARS[0])).units) * (len(YEARS) + 1)
                       for c in ORDER if run_path(c, YEARS[0]).exists())
        done = sum(r["state"] == "COMPLETED" or (r["state"] == "FAILED" and r["attempts"] >= MAX_ATTEMPTS)
                   for r in tasks.values())
        if expected and done >= expected and len(tasks) >= expected:
            log("drive: every task finished")
            return
        time.sleep(interval)


def _asset_exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException:
        return False


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("plan", "submit", "drive", "status"))
    p.add_argument("codes", nargs="*", help="ecoregion names or us_l3codes (default: all, in order)")
    p.add_argument("--interval", type=int, default=600)
    a = p.parse_args()
    ee.Initialize(project=sa.PROJECT)
    by_name = {v[0]: k for k, v in sa.ECOREGIONS.items()}
    codes = [int(c) if c.isdigit() else by_name[c] for c in a.codes] or ORDER
    if a.mode == "plan":
        plan(codes)
    elif a.mode == "submit":
        tasks = load_tasks()
        for c in codes:
            log(f"submitted {name(c)}: {submit_seasons(c, tasks, MAX_ACTIVE)} season tasks")
    elif a.mode == "drive":
        drive(a.interval)
    else:
        tasks = load_tasks()
        refresh(tasks)
        print(json.dumps({"quota": quota(), "tasks": summary(tasks), "errors": errors(tasks)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

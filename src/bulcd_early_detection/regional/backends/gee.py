"""Earth Engine backend for regional runs: one BULC-D run per tile, turned into
one image to the product spec (spec.py), exported as an asset into the run's
ImageCollection on the run's grid.

    python -m bulcd_early_detection.regional.backends.gee RUN.yaml [--tiles ID ...] [--dry-run] [--wait]
    python -m bulcd_early_detection.regional.backends.gee RUN.yaml --stack-with EARLIER_SEASON.yaml ... [--tiles ...]

Every band derives from the same run_bulcd() result, through the same
functions the apps' layers use (outputs.py), so a tile reproduces the apps'
condition, first-detected-season, last-detection and episode layers for its
monitoring year. The observation counts come from organize_inputs()'s binned
collections, which Earth Engine evaluates without the harmonic fit.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys

import ee
from bulcd.config.schema import BULCDConfig
from bulcd.inputs import organize_inputs
from bulcd.engine import run_bulcd

from ... import outputs
from .. import spec
from ..provenance import provenance
from ..run_config import RegionalRun
from ..tiling import Tile, lonlat_ring

DEFAULT_ASSET_ROOT = "projects/bulcd-python-rebuild/assets/regional"


def tile_region(run: RegionalRun, tile: Tile) -> tuple[float, float, float, float]:
    """The run's pixels in `tile` (grid CRS bounds)."""
    return tile.clip(run.region.bounds)


def tile_config(run: RegionalRun, tile: Tile) -> BULCDConfig:
    """The tile's BULCDConfig: the run's settings, with a lon/lat AOI ring that
    covers the tile's pixels (buffered one pixel; the export takes exactly the
    tile's pixels)."""
    return run.bulcd_config(aoi_coordinates=lonlat_ring(run.grid, tile_region(run, tile)))


def product_image(run: RegionalRun, config: BULCDConfig, result=None) -> ee.Image:
    """The spec's bands (spec.BANDS) from one run_bulcd() result."""
    result = result if result is not None else run_bulcd(config)
    c, year = run.controls, run.controls.monitoring_year
    t = c.thresholds
    confirmed = run.advanced.timing_rule == "confirmed"

    final = outputs._outcome_from_result(result, config, t["decrease"], t["increase"])
    condition = final.select("outcome")            # masked on water / outside the AOI
    timing = outputs.combine_season_timing(
        {year: outputs.detection_timing_from_result(result, config, t["decrease"], t["increase"])}, confirmed)
    episodes = outputs.combine_episode_metrics(
        {year: outputs.detection_episode_from_result(result, config, t["decrease"], t["increase"], confirmed)})
    organized = organize_inputs(config)
    band = config.reduction.band

    land = condition.mask()
    filled = lambda img: img.unmask(spec.NONE).updateMask(land)
    probability = lambda name: final.select(name).multiply(spec.PROBABILITY_SCALE).round()
    count = lambda collection: collection.select(band).count().unmask(0).updateMask(land)
    image = ee.Image.cat(
        condition.toUint8(),
        probability("decrease").toUint16(), probability("unchanged").toUint16(), probability("increase").toUint16(),
        filled(timing.select("first_decrease_doy")).toUint16(),
        filled(episodes.select("last_decrease_doy")).toUint16(),
        filled(episodes.select("decrease_episodes")).toUint8(),
        count(organized.target_collection).toUint16(),
        count(organized.expectation_collection).toUint16(),
    ).rename(list(spec.BAND_NAMES))
    if run.region.ecoregion is not None:
        # Outside the ecoregion (in OR/WA) = masked, as outside the region (spec: masked = no data).
        from .study_area import region_mask
        image = image.updateMask(region_mask(run.region.ecoregion))
    return image


def tile_transform(run: RegionalRun, tile: Tile) -> tuple[list[float], str]:
    """(crsTransform, dimensions) covering exactly the tile's pixels in the run."""
    x0, y0, x1, y1 = tile_region(run, tile)
    s = run.grid.scale
    return [s, 0, x0, 0, -s, y1], f"{round((x1 - x0) / s)}x{round((y1 - y0) / s)}"


def tile_properties(run: RegionalRun, tile: Tile, config: BULCDConfig, now: datetime.datetime | None = None) -> dict:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    c = run.controls
    transform, dimensions = tile_transform(run, tile)
    props = {
        "product_version": spec.PRODUCT_VERSION,
        "run_id": run.run_id,
        "tile_id": tile.id,
        "monitoring_year": c.monitoring_year,
        "season_start": c.season_start,
        "season_end": c.season_end,
        "timing_rule": run.advanced.timing_rule,
        "timing_date": spec.TIMING_DATE,
        "bin_days": config.evidence.day_step_size,
        "grid_json": json.dumps({"crs": run.grid.crs, "transform": transform, "dimensions": dimensions}),
        "run_json": json.dumps(run.to_dict(), sort_keys=True),
        "config_json": json.dumps(outputs._config_dict(config), sort_keys=True, default=str),
        "as_of_date": min(c.monitoring_end, now.date()).isoformat(),
        "export_date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "provenance_json": json.dumps(provenance(), sort_keys=True),
    }
    assert set(props) == set(spec.PROPERTIES), set(props) ^ set(spec.PROPERTIES)
    if hasattr(tile, "tiles"):   # a block: its tiles (tile_id is the block's ID)
        props["tile_ids"] = ",".join(t.id for t in tile.tiles)
    if run.region.ecoregion is not None:
        props["ecoregion"] = run.region.ecoregion
    return props


def collection_id(run: RegionalRun, asset_root: str = DEFAULT_ASSET_ROOT) -> str:
    return f"{asset_root}/{run.run_id}"


def ensure_collection(run: RegionalRun, asset_root: str = DEFAULT_ASSET_ROOT) -> str:
    outputs.ensure_folder(asset_root)
    path = collection_id(run, asset_root)
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createAsset({"type": "IMAGE_COLLECTION"}, path)
    return path


def export_tile(run: RegionalRun, tile: Tile, asset_root: str = DEFAULT_ASSET_ROOT, start: bool = True,
                shard_size: int | None = None):
    """Builds the tile's image and its Export.image.toAsset task (started
    unless `start` is False). One BULC-D run. `shard_size`: Earth Engine's
    shardSize (pixels per side of each computation shard; its default 256)."""
    config = tile_config(run, tile)
    image = product_image(run, config).set(tile_properties(run, tile, config))
    transform, dimensions = tile_transform(run, tile)
    extra = {} if shard_size is None else {"shardSize": shard_size}
    task = ee.batch.Export.image.toAsset(
        image=image,
        description=f"{run.run_id}_{tile.id}",
        assetId=f"{collection_id(run, asset_root)}/{tile.id}",
        crs=run.grid.crs,
        crsTransform=transform,
        dimensions=dimensions,
        # Categorical bands: pyramids keep a sample, never an average.
        pyramidingPolicy={".default": "sample"},
        maxPixels=1e10,
        **extra,
    )
    if start:
        task.start()
    return task


def submit(run: RegionalRun, tile_ids: list[str] | None = None, asset_root: str = DEFAULT_ASSET_ROOT) -> list:
    """Starts one export per unit (tile or block: all the run's, or `tile_ids`)."""
    tiles = run.units
    if tile_ids:
        unknown = set(tile_ids) - {t.id for t in tiles}
        if unknown:
            raise ValueError(f"not tiles of this run: {sorted(unknown)}")
        tiles = [t for t in tiles if t.id in tile_ids]
    ensure_collection(run, asset_root)
    return [export_tile(run, t, asset_root) for t in tiles]


# ---------------------------------------------------------------- the stack (spec.STACK_BANDS)
def season_years(run: RegionalRun, season_runs: list[RegionalRun]) -> list[int]:
    """The seasons a stack combines (sorted, ending with run's monitoring year).
    Every season run must be `run` with only monitoring_year (and run_id,
    description) changed, and earlier."""
    def settings(r):
        d = r.to_dict()
        d.pop("run_id"), d.pop("description"), d["controls"].pop("monitoring_year")
        return d
    years = [r.controls.monitoring_year for r in season_runs]
    for r in season_runs:
        if settings(r) != settings(run):
            raise ValueError(f"{r.run_id}: settings differ from {run.run_id} beyond monitoring_year")
    if len(set(years)) != len(years) or max(years, default=0) >= run.controls.monitoring_year:
        raise ValueError(f"season years must be distinct and before {run.controls.monitoring_year}: {years}")
    return sorted(years) + [run.controls.monitoring_year]


def detection_year_image(seasons: dict[int, ee.Image]) -> ee.Image:
    """detection_year from season tiles ({year: tile image}): the earliest
    season whose first_detection_doy is set (it is set only where a detection
    counts under the run's timing_rule), else spec.NONE. Masked as the latest
    season."""
    years = sorted(seasons)
    year = ee.Image(spec.NONE)
    for y in reversed(years):   # earliest written last, so it wins
        year = year.where(seasons[y].select("first_detection_doy").unmask(spec.NONE).gt(spec.NONE), y)
    return year.updateMask(seasons[years[-1]].select("condition").mask()).toUint16().rename("detection_year")


def stack_collection_id(run: RegionalRun, asset_root: str = DEFAULT_ASSET_ROOT) -> str:
    return f"{collection_id(run, asset_root)}-stack"


def stack_image(run: RegionalRun, season_runs: list[RegionalRun], tile: Tile,
                asset_root: str = DEFAULT_ASSET_ROOT) -> ee.Image:
    """The tile's stack from stored season tiles: `run`'s tile (bands and
    properties unchanged) + detection_year. No BULC-D run."""
    years = season_years(run, season_runs)
    by_year = {r.controls.monitoring_year: r for r in [*season_runs, run]}
    assets = {y: f"{collection_id(by_year[y], asset_root)}/{tile.id}" for y in years}
    seasons = {y: ee.Image(a) for y, a in assets.items()}
    image = seasons[years[-1]].addBands(detection_year_image(seasons))   # keeps the season tile's properties
    return image.set({
        "stack_version": spec.STACK_VERSION,
        "detection_years": ",".join(map(str, years)),
        "detection_year_floor": years[0],
        "season_assets_json": json.dumps({str(y): a for y, a in assets.items()}, sort_keys=True),
    })


def export_stack_tile(run: RegionalRun, season_runs: list[RegionalRun], tile: Tile,
                      asset_root: str = DEFAULT_ASSET_ROOT, start: bool = True):
    """Exports the tile's stack on the tile's pixels, as export_tile()."""
    for r in [*season_runs, run]:
        ee.data.getAsset(f"{collection_id(r, asset_root)}/{tile.id}")   # raises if a season tile is missing
    transform, dimensions = tile_transform(run, tile)
    task = ee.batch.Export.image.toAsset(
        image=stack_image(run, season_runs, tile, asset_root),
        description=f"{run.run_id}-stack_{tile.id}",
        assetId=f"{stack_collection_id(run, asset_root)}/{tile.id}",
        crs=run.grid.crs,
        crsTransform=transform,
        dimensions=dimensions,
        pyramidingPolicy={".default": "sample"},
        maxPixels=1e10,
    )
    if start:
        task.start()
    return task


def export_detection_year_tile(run: RegionalRun, season_runs: list[RegionalRun], tile: Tile, collection: str,
                               asset_root: str = DEFAULT_ASSET_ROOT, start: bool = True):
    """Exports detection_year alone (one band, detection_year_image(): the same
    values as the stack's band) into `collection`, on the tile's pixels. The
    image keeps the latest season tile's properties (run, grid, settings,
    provenance) plus the stack's detection-year properties. No BULC-D run."""
    years = season_years(run, season_runs)
    by_year = {r.controls.monitoring_year: r for r in [*season_runs, run]}
    assets = {y: f"{collection_id(by_year[y], asset_root)}/{tile.id}" for y in years}
    for a in assets.values():
        ee.data.getAsset(a)   # raises if a season tile is missing
    seasons = {y: ee.Image(a) for y, a in assets.items()}
    image = ee.Image(detection_year_image(seasons).copyProperties(seasons[years[-1]])).set({
        "stack_version": spec.STACK_VERSION,
        "detection_years": ",".join(map(str, years)),
        "detection_year_floor": years[0],
        "season_assets_json": json.dumps({str(y): a for y, a in assets.items()}, sort_keys=True),
    })
    transform, dimensions = tile_transform(run, tile)
    task = ee.batch.Export.image.toAsset(
        image=image,
        description=f"{collection.split('/')[-1]}_{tile.id}",
        assetId=f"{collection}/{tile.id}",
        crs=run.grid.crs,
        crsTransform=transform,
        dimensions=dimensions,
        pyramidingPolicy={".default": "sample"},
        maxPixels=1e10,
    )
    if start:
        task.start()
    return task


def submit_stack(run: RegionalRun, season_runs: list[RegionalRun], tile_ids: list[str] | None = None,
                 asset_root: str = DEFAULT_ASSET_ROOT) -> list:
    tiles = [t for t in run.units if not tile_ids or t.id in tile_ids]
    path = stack_collection_id(run, asset_root)
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createAsset({"type": "IMAGE_COLLECTION"}, path)
    return [export_stack_tile(run, season_runs, t, asset_root) for t in tiles]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("run", help="run file (YAML)")
    p.add_argument("--tiles", nargs="*", help="tile IDs (default: every tile)")
    p.add_argument("--asset-root", default=DEFAULT_ASSET_ROOT)
    p.add_argument("--project", default="bulcd-python-rebuild")
    p.add_argument("--dry-run", action="store_true", help="print the tiles and warnings; start nothing")
    p.add_argument("--wait", action="store_true", help="wait for the tasks to finish")
    p.add_argument("--stack-with", nargs="+", metavar="SEASON_RUN",
                   help="export the stack instead (from stored season tiles: RUN's + these earlier seasons')")
    a = p.parse_args(argv)
    run = RegionalRun.load(a.run)
    if a.stack_with:
        season_runs = [RegionalRun.load(f) for f in a.stack_with]
        print(f"{run.run_id} stack: seasons {season_years(run, season_runs)} -> {stack_collection_id(run, a.asset_root)}")
        if a.dry_run:
            return 0
        ee.Initialize(project=a.project)
        tasks = submit_stack(run, season_runs, a.tiles, a.asset_root)
        for task in tasks:
            print("started", task.status()["description"], task.id)
        if a.wait:
            states = outputs.wait_for(tasks)
            print(json.dumps(states, indent=1))
            return 0 if all(s == "COMPLETED" for s in states.values()) else 1
        return 0
    for w in run.warnings():
        print("Warning:", w)
    tiles = [t for t in run.units if not a.tiles or t.id in a.tiles]
    print(f"{run.run_id}: {len(tiles)} of {len(run.units)} export units ({len(run.tiles)} tiles) -> {collection_id(run, a.asset_root)}")
    for t in tiles:
        print(" ", t.id, tile_transform(run, t))
    if a.dry_run:
        return 0
    ee.Initialize(project=a.project)
    tasks = submit(run, a.tiles, a.asset_root)
    for task in tasks:
        print("started", task.status()["description"], task.id)
    if a.wait:
        states = outputs.wait_for(tasks)
        print(json.dumps(states, indent=1))
        return 0 if all(s == "COMPLETED" for s in states.values()) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

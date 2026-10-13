"""Study area, monitoring outputs, and precomputed-result storage.

Turns one `bulcd.engine.run_bulcd()` result into the monitoring layers the
notebook shows - one outcome class per pixel, plus confidence and
first-detection timing - and exports/loads them as Earth Engine assets
so presentation doesn't depend on a live run finishing.

Interpretation only: every probability comes from bulcd unchanged. The
masks reuse bulcd.engine.study_area_mask() rather than re-deriving them.
"""

from __future__ import annotations

import dataclasses
import json
import time
import warnings
from dataclasses import dataclass

import ee
from bulcd.config.schema import BULCDConfig
from bulcd.engine import run_bulcd, study_area_mask

from .config import class_thresholds

WDPA_POLYGONS = "WCMC/WDPA/current/polygons"
PARK_NAME = "Apostle Islands National Lakeshore"
SCALE = 30

# Values of the "outcome" band. Water is masked (no value).
DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED = 0, 1, 2, 3
OUTCOME_LABELS = {
    DECREASE: "Decrease (below expected)",
    UNCHANGED: "Unchanged (within expected)",
    INCREASE: "Increase (above expected)",
    NOT_ANALYZED: "Land not analyzed (non-forest mask)",
}
OUTPUT_BANDS = ["outcome", "confidence", "first_detection_doy", "decrease", "unchanged", "increase"]


def park_geometry(name: str = PARK_NAME, designation: str | None = None) -> ee.Geometry:
    """Park boundary from the World Database on Protected Areas. Exact
    name match (a substring match for "Apostle" also picks up Australia's
    "Twelve Apostles"); `designation` (WDPA DESIG_ENG) narrows further."""
    fc = ee.FeatureCollection(WDPA_POLYGONS).filter(ee.Filter.eq("NAME", name))
    if designation:
        fc = fc.filter(ee.Filter.eq("DESIG_ENG", designation))
    return fc.geometry()


def utm_crs(geometry: ee.Geometry) -> str:
    """UTM zone at the geometry's centroid. Area stats and exports use an
    equal-distance projected grid rather than the config's EPSG:4326."""
    lon, lat = geometry.centroid(100).coordinates().getInfo()
    zone = int((lon + 180) // 6) + 1
    return f"EPSG:{(32600 if lat >= 0 else 32700) + zone}"


@dataclass
class StudyArea:
    """A monitoring study area: `geometry` is the exact boundary (outputs
    are clipped to it, areas summed over it); `aoi` holds the
    build_config() keyword (aoi_coordinates or aoi_asset) bulcd runs on."""

    name: str
    geometry: ee.Geometry
    aoi: dict


def wdpa_park(key: str, name: str, designation: str | None = None) -> StudyArea:
    """A park's WDPA boundary. bulcd runs over its bounding box
    (aoi_coordinates takes one ring, and park boundaries are often
    multipolygons); outputs are then clipped back to the boundary."""
    park = park_geometry(name, designation)
    ring = park.bounds(1).coordinates().get(0).getInfo()
    return StudyArea(key, park, {"aoi_coordinates": ring})


def apostle_islands() -> StudyArea:
    return wdpa_park("apostle_islands", PARK_NAME)


def north_cascades() -> StudyArea:
    """North Cascades National Park only - WDPA lists Ross Lake and Lake
    Chelan National Recreation Areas separately, so they're excluded."""
    return wdpa_park("north_cascades", "North Cascades", "National Park")


def from_asset(asset_id: str) -> StudyArea:
    """Any FeatureCollection asset - bulcd reads it directly (aoi_asset)
    and uses the union of its features."""
    return StudyArea(asset_id.rstrip("/").split("/")[-1], ee.FeatureCollection(asset_id).geometry(), {"aoi_asset": asset_id})


# AOI size guidance for live runs. Milestone 1's spatial validation
# (~78 km^2 buffers) is the largest area actually run live so far.
TESTED_LIVE_KM2 = 100
LARGE_AOI_KM2 = 1000


def aoi_size_report(area: StudyArea) -> dict:
    """Area of the boundary and of its bounding box, plus a verdict:
    "ok" (<= TESTED_LIVE_KM2), "slow" (may be slow or time out live),
    or "large" (> LARGE_AOI_KM2 - use a batch export instead)."""
    bounds = area.geometry.bounds(1)
    stats = ee.Dictionary(
        {
            "area_km2": area.geometry.area(10).divide(1e6),
            "bbox_km2": bounds.area(10).divide(1e6),
            "bbox": bounds.coordinates().get(0),
        }
    ).getInfo()
    ring = stats.pop("bbox")
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    stats["bbox_degrees"] = [min(xs), min(ys), max(xs), max(ys)]
    km2 = stats["area_km2"]
    stats["verdict"] = "ok" if km2 <= TESTED_LIVE_KM2 else "slow" if km2 <= LARGE_AOI_KM2 else "large"
    return stats


def _first_crossing_doy(probability_stack: ee.ImageCollection, band: str, threshold: float) -> ee.Image:
    """Day of year of the first Event where `band`'s probability exceeds
    `threshold` - bulcd.interpret.first_change_year()'s "firstChange"
    rule (a single crossing counts), at day rather than year resolution.
    Events are bulcd's day_step_size bins, so this is bin-start precision."""

    def event_doy(img):
        doy = ee.Date(img.get("system:time_start")).getRelative("day", "year").add(1)
        return ee.Image.constant(doy).toInt16().rename("doy").updateMask(img.select(band).gt(threshold))

    return ee.ImageCollection(probability_stack.map(event_doy)).min()


def outcome_image(config: BULCDConfig, threshold: float, increase_threshold: float | None = None) -> ee.Image:
    """Runs BULC-D once and derives the monitoring layers (bands in
    OUTPUT_BANDS order, all float):

    - outcome: DECREASE where P(decrease) exceeds `threshold`, INCREASE
      where P(increase) exceeds `increase_threshold` (default: `threshold`;
      both >= 0.5, so at most one can), else UNCHANGED - the original BULC-D
      GUI's .gt() rule (its defaults: 0.65 decrease, 0.75 increase);
      NOT_ANALYZED on land excluded by the non-forest mask; masked on water.
    - confidence: final probability of the mapped outcome class.
    - first_detection_doy: first date the mapped change class crossed its
      threshold (masked for unchanged pixels).
    - decrease/unchanged/increase: bulcd's final_probabilities.
    """
    return _outcome_from_result(run_bulcd(config), config, threshold, increase_threshold)


def _outcome_from_result(result, config: BULCDConfig, threshold: float,
                         increase_threshold: float | None = None) -> ee.Image:
    t = class_thresholds(threshold, increase_threshold)
    final = result.final_probabilities
    dec, unc, inc = (final.select(b) for b in ("decrease", "unchanged", "increase"))

    analyzed = study_area_mask(config)
    analyzed = ee.Image.constant(1) if analyzed is None else analyzed
    water_only = dataclasses.replace(
        config, study_area=dataclasses.replace(config.study_area, mask_water=True, mask_non_forest=False)
    )
    land = study_area_mask(water_only)

    changed = (
        ee.Image.constant(UNCHANGED).where(dec.gt(t["decrease"]), DECREASE).where(inc.gt(t["increase"]), INCREASE)
    ).updateMask(analyzed).updateMask(dec.mask())
    outcome = (
        ee.Image.constant(NOT_ANALYZED).where(changed.mask(), changed).updateMask(land).rename("outcome")
    )

    confidence = unc.where(changed.eq(DECREASE), dec).where(changed.eq(INCREASE), inc).rename("confidence")

    first_dec = _first_crossing_doy(result.probability_stack, "decrease", t["decrease"])
    first_inc = _first_crossing_doy(result.probability_stack, "increase", t["increase"])
    first = (
        first_dec.updateMask(changed.eq(DECREASE))
        .unmask(first_inc.updateMask(changed.eq(INCREASE)))
        .updateMask(changed.neq(UNCHANGED))
        .rename("first_detection_doy")
    )

    return ee.Image.cat(
        outcome.toFloat(), confidence.toFloat(), first.toFloat(), dec.toFloat(), unc.toFloat(), inc.toFloat()
    )


def run_metadata(controls, config: BULCDConfig) -> dict:
    """Asset properties identifying what produced a precomputed result."""
    return {
        "controls_json": json.dumps(dataclasses.asdict(controls), sort_keys=True),
        "config_json": json.dumps(_config_dict(config), sort_keys=True, default=str),
    }


def _config_dict(config: BULCDConfig) -> dict:
    d = dataclasses.asdict(config)
    # The AOI is identified by the asset itself; compare everything else.
    d["study_area"].pop("aoi_coordinates", None)
    return d


def ensure_folder(folder: str) -> None:
    try:
        ee.data.getAsset(folder)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, folder)


def export_study_area(controls, build, area: StudyArea, folder: str, run_name: str,
                      config: BULCDConfig | None = None, image_fn=None) -> list:
    """Starts one Export.image.toAsset task for `area`; returns [task].

    `build(controls, **aoi) -> BULCDConfig` - normally config.build_config,
    or a wrapper applying advanced overrides. Output is clipped to the
    boundary. The whole Apostle Islands park (~280 km^2) exports as one
    task in ~20 minutes, so no tiling. Returns a list so load_precomputed()
    can mosaic several pieces if a larger area ever needs them.
    """
    ensure_folder(folder)
    config = config or build(controls, **area.aoi)
    image_fn = image_fn or outcome_image
    image = (
        image_fn(config, controls.decision_threshold)
        .clip(area.geometry)
        .set({"run_name": run_name, "tile": "all", **run_metadata(controls, config)})
    )
    task = ee.batch.Export.image.toAsset(
        image=image,
        description=f"{run_name}_all",
        assetId=f"{folder}/{run_name}_all",
        region=area.geometry,
        scale=SCALE,
        crs=utm_crs(area.geometry),
        maxPixels=1e10,
    )
    task.start()
    return [task]


def wait_for(tasks: list, poll_seconds: int = 30) -> dict[str, str]:
    """Blocks until every task finishes; returns {description: state}."""
    while True:
        statuses = {t.status()["description"]: t.status() for t in tasks}
        pending = [d for d, s in statuses.items() if s["state"] in ("READY", "RUNNING")]
        if not pending:
            return {d: s["state"] + (f" ({s.get('error_message')})" if s.get("error_message") else "") for d, s in statuses.items()}
        print(f"{len(pending)} of {len(tasks)} export task(s) still running ...")
        time.sleep(poll_seconds)


# Precomputed runs exported before BULC-D_rebuild decision 0011 (2026-10-08: no Sentinel-2
# scene-cloud filter by default; legacy fracDOY harmonic time axis). They reflect the old
# behavior; loading one warns. Regenerate as _v2 before citing them as current results.
PRE_PARITY_RUN_SUFFIX = "_v1"


def load_precomputed(folder: str, run_name: str, bands: list[str] = OUTPUT_BANDS) -> tuple[ee.Image, list[dict]]:
    """Mosaic of a run's exported tiles, plus each tile's metadata."""
    if run_name.endswith(PRE_PARITY_RUN_SUFFIX):
        warnings.warn(f"{run_name!r} is a pre-parity (v1) result: computed before BULC-D_rebuild decision 0011 "
                      "(S2 scene filter, years-since-1970 time axis). Not the current BULC-D behavior.", stacklevel=2)
    assets = [a["name"] for a in ee.data.listAssets({"parent": folder})["assets"] if a["name"].split("/")[-1].startswith(f"{run_name}_")]
    if not assets:
        raise FileNotFoundError(f"no precomputed tiles for {run_name!r} in {folder}")
    collection = ee.ImageCollection([ee.Image(a) for a in assets])
    props = collection.toList(len(assets)).map(lambda i: ee.Image(i).toDictionary(["tile", "controls_json", "config_json"])).getInfo()
    return collection.mosaic().select(bands), props


def area_summary(outcome: ee.Image, region: ee.Geometry, crs: str | None = None) -> dict[str, float]:
    """km^2 per outcome class inside `region` (water excluded)."""
    area = ee.Image.pixelArea().divide(1e6).addBands(outcome.select("outcome").toInt())
    groups = area.reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="outcome"),
        geometry=region,
        scale=SCALE,
        crs=crs or utm_crs(region),
        maxPixels=1e10,
        tileScale=4,
    ).get("groups").getInfo()
    by_class = {int(g["outcome"]): g["sum"] for g in groups}
    return {OUTCOME_LABELS[k]: by_class.get(k, 0.0) for k in OUTCOME_LABELS}


def early_detection_share(outcome: ee.Image, region: ee.Geometry, first_doy: int, days: int = 14, crs: str | None = None) -> dict[str, float]:
    """Changed area (km^2), and the share of it first detected within
    `days` of the season start - a high share means most mapped change
    was already present when the season's observations began, rather than
    happening during the season."""
    changed = outcome.select("outcome").eq(DECREASE).Or(outcome.select("outcome").eq(INCREASE))
    early = changed.And(outcome.select("first_detection_doy").lt(first_doy + days))
    area = ee.Image.pixelArea().divide(1e6)
    sums = (
        area.updateMask(changed).rename("changed")
        .addBands(area.updateMask(early).rename("early"))
        .reduceRegion(ee.Reducer.sum(), region, SCALE, crs=crs or utm_crs(region), maxPixels=1e10, tileScale=4)
        .getInfo()
    )
    total = sums.get("changed") or 0.0
    return {"changed_km2": total, "early_km2": sums.get("early") or 0.0, "early_share": (sums.get("early") or 0.0) / total if total else 0.0}


def reclassify(outputs_image: ee.Image, threshold: float, increase_threshold: float | None = None) -> ee.Image:
    """Re-applies the decision rule at other thresholds (>= 0.5; increase
    defaults to `threshold`) to existing outputs - no new BULC-D run, since
    the thresholds only act on the final probabilities. Masked areas are
    unchanged."""
    t = class_thresholds(threshold, increase_threshold)
    outcome = outputs_image.select("outcome")
    analyzed = outcome.lte(INCREASE)
    new = (
        outcome.where(analyzed, UNCHANGED)
        .where(analyzed.And(outputs_image.select("decrease").gt(t["decrease"])), DECREASE)
        .where(analyzed.And(outputs_image.select("increase").gt(t["increase"])), INCREASE)
    )
    return outputs_image.addBands(new.rename("outcome"), overwrite=True)


# ---------------------------------------------------------------- detection timing
TIMING_BANDS = ["first_decrease_year", "first_decrease_doy", "outcome"]
# Added by detection_timing_image(episodes=True); see decrease_episode_bands().
EPISODE_BANDS = ["last_decrease_year", "last_decrease_doy", "decrease_episodes"]


def _date_code(img: ee.Image) -> ee.Number:
    """year * 1000 + 1-based day of year of a bin's (end) date."""
    date = ee.Date(img.get("system:time_start"))
    return date.get("year").multiply(1000).add(date.getRelative("day", "year").add(1))


def decrease_episode_bands(probability_stack: ee.ImageCollection, threshold: float) -> ee.Image:
    """Detection episodes in one run: an episode starts at a bin where
    P(decrease) > `threshold` (strictly, as the first-detected date) after a
    bin at or below it, and ends at the next bin at or below it. The run
    starts below the threshold (starting odds 0.1 decrease; thresholds >= 0.5),
    so the first episode starts at the first crossing. Bins without a valid
    observation carry the previous probability unchanged (bulcd), so they
    never start or end an episode. No smoothing or minimum duration.

    Bands: decrease_episodes (count), last_decrease_year/doy (start of the
    most recent episode, bin END date as bulcd timestamps bins); all 0 where
    there was no episode. Each bin is compared with the previous one along a
    per-pixel array, in time order. gee/outputs.js decreaseEpisodeBands()
    is the same computation; pixel.detection_episodes() is its row form."""
    stack = probability_stack.sort("system:time_start").map(
        lambda img: img.select("decrease").gt(threshold).toInt32().rename("above")
        .addBands(ee.Image.constant(_date_code(img)).toInt32().rename("code")))
    arr = stack.toArray()                                    # [bins, (above, code)]
    above = arr.arraySlice(1, 0, 1)
    before = ee.Image(ee.Array([[0]])).arrayCat(above.arraySlice(0, 0, -1), 0)  # bin before; below at the start
    starts = above.gt(before)
    count = starts.arrayReduce(ee.Reducer.sum(), [0]).arrayGet([0, 0])
    last = arr.arraySlice(1, 1, 2).multiply(starts).arrayReduce(ee.Reducer.max(), [0]).arrayGet([0, 0])
    return ee.Image.cat(last.divide(1000).floor().rename("last_decrease_year"),
                        last.mod(1000).rename("last_decrease_doy"),
                        count.rename("decrease_episodes")).toFloat()


def detection_timing_image(config: BULCDConfig, threshold: float, increase_threshold: float | None = None,
                           episodes: bool = False) -> ee.Image:
    """For a (typically multi-year) monitoring run: the year and day of year
    of the FIRST observation bin where P(decrease) exceeded `threshold` (the
    decrease threshold) (bin END date, as bulcd timestamps bins), masked
    where it never did or the pixel isn't analyzed; plus `outcome`, the state
    at the end of the run (same codes as outcome_image, with
    `increase_threshold`). One BULC-D run feeds both.

    episodes=True appends EPISODE_BANDS from the same run
    (decrease_episode_bands(); masked like the first-detected bands). The
    first three bands are the same either way."""
    result = run_bulcd(config)
    outcome = _outcome_from_result(result, config, threshold, increase_threshold).select("outcome")

    def code(img):
        date = ee.Date(img.get("system:time_start"))
        value = date.get("year").multiply(1000).add(date.getRelative("day", "year").add(1))
        return ee.Image.constant(value).toInt32().rename("code").updateMask(img.select("decrease").gt(threshold))

    first = ee.ImageCollection(result.probability_stack.map(code)).min().updateMask(outcome.lte(INCREASE))
    year = first.divide(1000).floor().rename("first_decrease_year")
    doy = first.mod(1000).rename("first_decrease_doy")
    out = ee.Image.cat(year.toFloat(), doy.toFloat(), outcome.toFloat())
    if episodes:
        out = out.addBands(decrease_episode_bands(result.probability_stack, threshold).updateMask(first.mask()))
    return out


def decrease_year_summary(timing: ee.Image, region: ee.Geometry, years: list[int], crs: str | None = None) -> dict:
    """km^2 of analyzed land by first-detection year, plus "none" (analyzed,
    never crossed the threshold)."""
    analyzed = timing.select("outcome").lte(INCREASE)
    year = timing.select("first_decrease_year").unmask(0)
    area = ee.Image.pixelArea().divide(1e6)
    bands = [area.updateMask(analyzed.And(year.eq(y))).rename(str(y)) for y in years]
    bands.append(area.updateMask(analyzed.And(year.eq(0))).rename("none"))
    sums = ee.Image.cat(bands).reduceRegion(
        ee.Reducer.sum(), region, SCALE, crs=crs or utm_crs(region), maxPixels=1e10, tileScale=4
    ).getInfo()
    return {k: (sums.get(k) or 0.0) for k in [*map(str, years), "none"]}


def episode_summary(metrics: ee.Image, region: ee.Geometry, crs: str | None = None) -> dict:
    """km^2 of the selected seasons' detected decrease by number of detection
    episodes (combine_episode_metrics()): "1", "2", "3+"."""
    n = metrics.select("decrease_episodes").unmask(0)
    area = ee.Image.pixelArea().divide(1e6)
    bands = [area.updateMask(n.eq(1)).rename("e1"), area.updateMask(n.eq(2)).rename("e2"),
             area.updateMask(n.gte(3)).rename("e3")]   # band names can't contain "+"
    sums = ee.Image.cat(bands).reduceRegion(
        ee.Reducer.sum(), region, SCALE, crs=crs or utm_crs(region), maxPixels=1e10, tileScale=4
    ).getInfo()
    return {k: (sums.get(b) or 0.0) for k, b in (("1", "e1"), ("2", "e2"), ("3+", "e3"))}


# ---------------------------------------------------------------- temporal NBR composite
def _clear_s2(region: ee.Geometry, year: int, window: tuple[str, str], cs_threshold: float = 0.6) -> ee.ImageCollection:
    """Sentinel-2 SR for one year's MM-DD window, Cloud Score+-masked."""
    csp = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(f"{year}-{window[0]}", f"{year}-{window[1]}")
        .linkCollection(csp, ["cs_cdf"])
        .map(lambda i: i.updateMask(i.select("cs_cdf").gte(cs_threshold)))
    )


def annual_true_color(region: ee.Geometry, year: int, window: tuple[str, str] = ("08-01", "09-15")) -> ee.Image:
    """Sentinel-2 red/green/blue for one year: median of clear (Cloud Score+)
    observations in the MM-DD window. For areas too large for one clear
    date; same processing every year."""
    return _clear_s2(region, year, window).select(["B4", "B3", "B2"]).median()


def annual_nbr(region: ee.Geometry, year: int, window: tuple[str, str] = ("07-01", "09-15"),
               crs: str | None = None, cs_threshold: float = 0.6, reproject: bool = True) -> ee.Image:
    """Sentinel-2 NBR (B8, B12) for one year: median of Cloud Score+-masked
    observations in the MM-DD `window`, on a fixed 30 m UTM grid. Same
    processing every year, so years are directly comparable. Reference
    imagery only - independent of BULC-D's evidence pipeline."""
    col = _clear_s2(region, year, window, cs_threshold)
    nbr = col.map(lambda i: i.normalizedDifference(["B8", "B12"])).median().rename(f"nbr_{year}")
    # A fixed 30 m grid for analysis; skip for display over large areas, where
    # forcing 30 m everywhere is very expensive (the map is drawn coarser anyway).
    return nbr.reproject(crs=crs or utm_crs(region), scale=SCALE) if reproject else nbr


def nbr_stretch(nbr_images: list[ee.Image], region: ee.Geometry, low: int = 2, high: int = 98,
                scale: int = SCALE) -> tuple[float, float]:
    """ONE stretch for all years: the lowest `low` and highest `high`
    percentile across the years' NBR inside `region`."""
    stats = ee.Image.cat(nbr_images).reduceRegion(
        ee.Reducer.percentile([low, high]), region, scale, maxPixels=1e10, bestEffort=True, tileScale=4
    ).getInfo()
    lows = [v for k, v in stats.items() if k.endswith(f"_p{low}") and v is not None]
    highs = [v for k, v in stats.items() if k.endswith(f"_p{high}") and v is not None]
    return min(lows), max(highs)


def combine_season_timing(seasons: dict[int, ee.Image], confirmed: bool = True) -> ee.Image:
    """First monitoring season in which P(decrease) crossed the threshold,
    from INDEPENDENT single-season runs (each detection_timing_image(),
    each starting from even odds against the same baseline): year = the
    earliest season that crossed, doy = that season's first-crossing day.
    `outcome` comes from the latest season (masks are identical across
    seasons). Same bands as detection_timing_image(), so the same maps and
    summaries apply. Avoids the lock-in of one continuous multi-year run
    (docs/findings.md, 2026-09-29).

    confirmed=True (default, the user-facing "first detected" definition since
    2026-09-30): a season counts only if it ENDS as decrease; the date kept is
    still that season's first threshold crossing. confirmed=False: raw first
    crossing - any crossing counts, even one BULC-D later retracts (kept for
    diagnostics; see docs/findings.md). Both derive from the same runs."""
    years = sorted(seasons)
    year = ee.Image(0).toFloat()
    doy = ee.Image(0).toFloat()
    for y in reversed(years):  # earliest season written last, so it wins
        crossed = seasons[y].select("first_decrease_year").mask().And(seasons[y].select("first_decrease_year").unmask(0).gt(0))
        if confirmed:
            crossed = crossed.And(seasons[y].select("outcome").eq(DECREASE))
        year = year.where(crossed, y)
        doy = doy.where(crossed, seasons[y].select("first_decrease_doy").unmask(0))
    outcome = seasons[years[-1]].select("outcome")
    found = year.gt(0)
    return ee.Image.cat(
        year.updateMask(found).updateMask(outcome.mask()).rename("first_decrease_year"),
        doy.updateMask(found).updateMask(outcome.mask()).rename("first_decrease_doy"),
        outcome,
    )


def combine_episode_metrics(seasons: dict[int, ee.Image], confirmed: bool = True) -> ee.Image:
    """Last detection and detection episodes for the season
    combine_season_timing() (same `confirmed`) selects - the earliest season
    that crossed, and with confirmed=True also ended as decrease - taken from
    that season's own run (detection_timing_image(..., episodes=True)).
    Within one season only: each season is a separate run from the same
    starting odds, so a change still present the next season would cross
    again there just because of that reset.

    Bands EPISODE_BANDS, masked where combine_season_timing() finds no
    season. With confirmed=True the selected season ends as decrease, so its
    last episode is still open at season end: last detection = the start of
    the detection that held to the end of the season."""
    years = sorted(seasons)
    chosen = {b: ee.Image(0).toFloat() for b in EPISODE_BANDS}
    for y in reversed(years):  # earliest season written last, so it wins (as combine_season_timing)
        crossed = seasons[y].select("first_decrease_year").mask().And(seasons[y].select("first_decrease_year").unmask(0).gt(0))
        if confirmed:
            crossed = crossed.And(seasons[y].select("outcome").eq(DECREASE))
        for b in EPISODE_BANDS:
            chosen[b] = chosen[b].where(crossed, seasons[y].select(b).unmask(0))
    found = chosen["decrease_episodes"].gt(0)
    mask = seasons[years[-1]].select("outcome").mask()
    return ee.Image.cat([chosen[b].updateMask(found).updateMask(mask).rename(b) for b in EPISODE_BANDS])

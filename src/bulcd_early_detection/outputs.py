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
from dataclasses import dataclass

import ee
from bulcd.config.schema import BULCDConfig
from bulcd.engine import run_bulcd, study_area_mask

WDPA_POLYGONS = "WCMC/WDPA/current/polygons"
PARK_NAME = "Apostle Islands National Lakeshore"
# UTM 15N - the park spans ~91.05W-90.39W. Area stats and exports use an
# equal-distance projected grid rather than the config's EPSG:4326.
PROJECTED_CRS = "EPSG:32615"
SCALE = 30

# Values of the "outcome" band. Water is masked (no value).
DECREASE, UNCHANGED, INCREASE, NOT_ANALYZED = 0, 1, 2, 3
OUTCOME_LABELS = {
    DECREASE: "Decrease / disturbance",
    UNCHANGED: "Unchanged",
    INCREASE: "Increase / growth",
    NOT_ANALYZED: "Land not analyzed (non-forest mask)",
}
OUTPUT_BANDS = ["outcome", "confidence", "first_detection_doy", "decrease", "unchanged", "increase"]


def park_geometry(name: str = PARK_NAME) -> ee.Geometry:
    """Park boundary from the World Database on Protected Areas. Exact
    name match - a substring match also picks up Australia's "Twelve
    Apostles" marine park."""
    return ee.FeatureCollection(WDPA_POLYGONS).filter(ee.Filter.eq("NAME", name)).geometry()


@dataclass
class StudyArea:
    """A monitoring study area: `geometry` is the exact boundary (outputs
    are clipped to it, areas summed over it); `aoi` holds the
    build_config() keyword (aoi_coordinates or aoi_asset) bulcd runs on."""

    name: str
    geometry: ee.Geometry
    aoi: dict


def apostle_islands() -> StudyArea:
    """The park's WDPA boundary. bulcd runs over its bounding box (the
    boundary is a 22-part multipolygon, and aoi_coordinates takes one
    ring); outputs are then clipped back to the boundary."""
    park = park_geometry()
    ring = park.bounds(1).coordinates().get(0).getInfo()
    return StudyArea("apostle_islands", park, {"aoi_coordinates": ring})


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


def outcome_image(config: BULCDConfig, threshold: float) -> ee.Image:
    """Runs BULC-D once and derives the monitoring layers (bands in
    OUTPUT_BANDS order, all float):

    - outcome: DECREASE/INCREASE where that class's final probability
      exceeds `threshold` (>= 0.5, so at most one can), else UNCHANGED;
      NOT_ANALYZED on land excluded by the non-forest mask; masked on water.
    - confidence: final probability of the mapped outcome class.
    - first_detection_doy: first date the mapped change class crossed
      `threshold` (masked for unchanged pixels).
    - decrease/unchanged/increase: bulcd's final_probabilities.
    """
    result = run_bulcd(config)
    final = result.final_probabilities
    dec, unc, inc = (final.select(b) for b in ("decrease", "unchanged", "increase"))

    analyzed = study_area_mask(config)
    analyzed = ee.Image.constant(1) if analyzed is None else analyzed
    water_only = dataclasses.replace(
        config, study_area=dataclasses.replace(config.study_area, mask_water=True, mask_non_forest=False)
    )
    land = study_area_mask(water_only)

    changed = (
        ee.Image.constant(UNCHANGED).where(dec.gt(threshold), DECREASE).where(inc.gt(threshold), INCREASE)
    ).updateMask(analyzed).updateMask(dec.mask())
    outcome = (
        ee.Image.constant(NOT_ANALYZED).where(changed.mask(), changed).updateMask(land).rename("outcome")
    )

    confidence = unc.where(changed.eq(DECREASE), dec).where(changed.eq(INCREASE), inc).rename("confidence")

    first_dec = _first_crossing_doy(result.probability_stack, "decrease", threshold)
    first_inc = _first_crossing_doy(result.probability_stack, "increase", threshold)
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


def export_study_area(controls, build, area: StudyArea, folder: str, run_name: str) -> list:
    """Starts one Export.image.toAsset task for `area`; returns [task].

    `build(controls, **aoi) -> BULCDConfig` - normally config.build_config,
    or a wrapper applying advanced overrides. Output is clipped to the
    boundary. The whole Apostle Islands park (~280 km^2) exports as one
    task in ~20 minutes, so no tiling. Returns a list so load_precomputed()
    can mosaic several pieces if a larger area ever needs them.
    """
    ensure_folder(folder)
    config = build(controls, **area.aoi)
    image = (
        outcome_image(config, controls.decision_threshold)
        .clip(area.geometry)
        .set({"run_name": run_name, "tile": "all", **run_metadata(controls, config)})
    )
    task = ee.batch.Export.image.toAsset(
        image=image,
        description=f"{run_name}_all",
        assetId=f"{folder}/{run_name}_all",
        region=area.geometry,
        scale=SCALE,
        crs=PROJECTED_CRS,
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


def load_precomputed(folder: str, run_name: str) -> tuple[ee.Image, list[dict]]:
    """Mosaic of a run's exported tiles, plus each tile's metadata."""
    assets = [a["name"] for a in ee.data.listAssets({"parent": folder})["assets"] if a["name"].split("/")[-1].startswith(f"{run_name}_")]
    if not assets:
        raise FileNotFoundError(f"no precomputed tiles for {run_name!r} in {folder}")
    collection = ee.ImageCollection([ee.Image(a) for a in assets])
    props = collection.toList(len(assets)).map(lambda i: ee.Image(i).toDictionary(["tile", "controls_json", "config_json"])).getInfo()
    return collection.mosaic().select(OUTPUT_BANDS), props


def area_summary(outcome: ee.Image, region: ee.Geometry) -> dict[str, float]:
    """km^2 per outcome class inside `region` (water excluded)."""
    area = ee.Image.pixelArea().divide(1e6).addBands(outcome.select("outcome").toInt())
    groups = area.reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="outcome"),
        geometry=region,
        scale=SCALE,
        crs=PROJECTED_CRS,
        maxPixels=1e10,
        tileScale=4,
    ).get("groups").getInfo()
    by_class = {int(g["outcome"]): g["sum"] for g in groups}
    return {OUTCOME_LABELS[k]: by_class.get(k, 0.0) for k in OUTCOME_LABELS}


def early_detection_share(outcome: ee.Image, region: ee.Geometry, first_doy: int, days: int = 14) -> dict[str, float]:
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
        .reduceRegion(ee.Reducer.sum(), region, SCALE, crs=PROJECTED_CRS, maxPixels=1e10, tileScale=4)
        .getInfo()
    )
    total = sums.get("changed") or 0.0
    return {"changed_km2": total, "early_km2": sums.get("early") or 0.0, "early_share": (sums.get("early") or 0.0) / total if total else 0.0}

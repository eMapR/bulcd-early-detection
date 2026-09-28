"""Spatial validation: full-AOI production-matrix run over an ~5km buffer
around each test point, to visually sanity-check whether BULC-D's
decrease signal is spatially concentrated on the known disturbance
footprint, or appearing broadly/randomly across the surrounding
landscape. NOT a false-positive-rate calculation - other real
disturbances may exist inside the buffer with no reference data to
confirm either way (see docs/findings.md).

Uses BULC-D_rebuild's public API only (bulcd.engine.run_bulcd,
bulcd.interpret.first_change_year), the real production transition
matrix (see replay_production_matrix.py's provenance note and
docs/findings.md), recency_factor=1.0, and every other parameter exactly
as approved for each site's point-based replay - only the AOI changes,
from the point-sized box to a real ~5km ee.Geometry.buffer(). No
BULC-D_rebuild code is modified, and nothing is tuned based on what's
seen here.

Produces PNG thumbnails (ee.Image.getThumbURL(), downloaded via an
authenticated request - same idiom as ../BULC-D_rebuild's own
scripts/debug_disturbance_map.py) per site, each with the original test
point marked as a yellow ring:
  - reference: post-disturbance false-color (SWIR2/NIR/Red) Sentinel-2
    composite, independent of BULC-D's own pipeline, for visual context.
  - decrease_probability: final_probabilities' "decrease" band, 0-1.
  - mask_gt_0.5: decrease_probability > 0.5, binary.
  - first_detection_year: bulcd.interpret.first_change_year() - year
    granularity only (target periods are single-year), so this is
    coarse; included because it's what the public API offers.

Usage:
    conda run -n bulcd python experiments/spatial_validation.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import ee
import google.auth.transport.requests

ee.Initialize(project="bulcd-python-rebuild")

from bulcd.engine import run_bulcd
from bulcd.interpret import first_change_year

import replay_fire_2026 as fire
import replay_harvest_2025 as harvest
from replay_production_matrix import PRODUCTION_TRANSITION_MATRIX

BUFFER_METERS = 5000
THUMB_DIMENSIONS = 640
OUTPUT_DIR = Path(__file__).parent / "output" / "spatial"

SITES = [
    {
        "name": "harvest_2025",
        "module": harvest,
        # After observed completion (2025-08-19), before the target
        # period's own nominal end - "sees the disturbance after it
        # occurred," per instruction.
        "reference_start": "2025-08-19",
        "reference_end": "2025-10-01",
        "target_year": 2025,
    },
    {
        "name": "fire_2026",
        "module": fire,
        "reference_start": "2026-07-22",
        "reference_end": "2026-09-19",
        "target_year": 2026,
    },
]

_BACKGROUND = ee.Image.constant([0.12, 0.12, 0.12]).visualize(min=0, max=1)


def _download(image: ee.Image, region: ee.Geometry, token: str, attempts: int = 3) -> bytes:
    url = image.getThumbURL({"region": region, "dimensions": THUMB_DIMENSIONS, "format": "png"})
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(req).read()
        except (ConnectionResetError, TimeoutError) as exc:
            if attempt == attempts - 1:
                raise
            print(f"  download retry ({exc}) ...")


def _reference_composite(region: ee.Geometry, start: str, end: str) -> ee.Image:
    """Simple post-disturbance false-color (SWIR2/NIR/Red) Sentinel-2
    median composite - independent of BULC-D's own evidence pipeline,
    purely for visual context. Bare/burned ground reads bright
    orange-brown against green vegetation in this band combination.

    S2_SR_HARMONIZED bands are raw DN, 0-10000 scale (not reflectance
    0-1) - dividing by 3000 here first (a mistake carried over from a
    true-color-composite habit) saturated the NIR band solid green.
    Fixed: keep raw DN and let the caller's .visualize(min=0, max=4000)
    do the stretch, a standard S2 false-color range.
    """
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40))
        .median()
        .select(["B12", "B8", "B4"])
    )


def _with_marker(vis_image: ee.Image, point: ee.Geometry) -> ee.Image:
    """Blends `vis_image` onto a neutral gray background (so masked
    pixels are visibly gray, not transparent/black) and paints the
    original test point as a yellow ring on top."""
    marker_fc = ee.FeatureCollection([ee.Feature(point.buffer(150))])
    outline = ee.Image().byte().paint(marker_fc, 1, 3).visualize(palette=["ffff00"])
    return _BACKGROUND.blend(vis_image).blend(outline)


def process_site(site: dict, token: str) -> dict:
    module = site["module"]
    point = ee.Geometry.Point([module.LON, module.LAT])
    buffer_geom = point.buffer(BUFFER_METERS)
    aoi_coordinates = buffer_geom.getInfo()["coordinates"][0]

    config = module.build_config(
        recency_factor=1.0,
        transition_matrix=PRODUCTION_TRANSITION_MATRIX,
        aoi_coordinates=aoi_coordinates,
    )
    result = run_bulcd(config)
    year_image = first_change_year(result.probability_stack, class_name="decrease", threshold=0.5)

    decrease = result.final_probabilities.select("decrease")
    mask = decrease.gt(0.5).selfMask()

    reference = _reference_composite(buffer_geom, site["reference_start"], site["reference_end"])
    layers = {
        "reference": reference.visualize(min=0, max=4000),
        "decrease_probability": decrease.visualize(
            min=0, max=1, palette=["000033", "0000ff", "00ffff", "ffff00", "ff0000"]
        ),
        "mask_gt_0.5": mask.visualize(min=1, max=1, palette=["ff0000"]),
        "first_detection_year": year_image.visualize(
            min=site["target_year"], max=site["target_year"], palette=["ff0000"]
        ),
    }

    site_dir = OUTPUT_DIR / site["name"]
    site_dir.mkdir(parents=True, exist_ok=True)
    for label, img in layers.items():
        data = _download(_with_marker(img, point), buffer_geom, token)
        path = site_dir / f"{label}.png"
        path.write_bytes(data)
        print(f"  wrote {path} ({len(data)} bytes)")

    fraction_gt_half = mask.unmask(0).reduceRegion(
        reducer=ee.Reducer.mean(), geometry=buffer_geom, scale=30, maxPixels=1e9, bestEffort=True
    ).getInfo()
    buffer_area_km2 = buffer_geom.area(1).getInfo() / 1e6
    fraction = fraction_gt_half.get("decrease", 0.0)
    stats = {
        "fraction_of_buffer_gt_0.5": fraction,
        "approx_area_km2_gt_0.5": fraction * buffer_area_km2,
        "buffer_area_km2": buffer_area_km2,
    }
    print(f"  buffer stats: {stats}")
    return stats


def main() -> None:
    creds = ee.data.get_persistent_credentials()
    creds.refresh(google.auth.transport.requests.Request())
    for site in SITES:
        print(f"=== {site['name']} ===")
        process_site(site, creds.token)


if __name__ == "__main__":
    main()

"""Draw a study area on an interactive map, and save/reload it as GeoJSON.

Drawn areas are saved as small local GeoJSON files (not Earth Engine
assets), so the exact same geometry can be reloaded by name for repeated
runs - e.g. comparing parameter settings - without redrawing.

Drawing needs a live notebook frontend (JupyterLab 4, Notebook 7, VS
Code); loading a saved area doesn't.
"""

from __future__ import annotations

import json
from pathlib import Path

import ee
import ipyleaflet

from .outputs import StudyArea

AOI_DIR = Path("aois")


def aoi_path(name: str, directory: Path = AOI_DIR) -> Path:
    return Path(directory) / f"{name}.geojson"


def save_polygon(name: str, ring: list[list[float]], directory: Path = AOI_DIR) -> Path:
    """Saves one polygon ring ([[lon, lat], ...]) as a GeoJSON Feature."""
    path = aoi_path(name, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    feature = {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    path.write_text(json.dumps(feature, indent=1) + "\n")
    return path


def load_polygon(name: str, directory: Path = AOI_DIR) -> list[list[float]]:
    path = aoi_path(name, directory)
    if not path.exists():
        raise FileNotFoundError(
            f"No saved area {name!r} ({path}). Draw a polygon on the map and run the save cell first."
        )
    return _ring(json.loads(path.read_text()))


def study_area(name: str, directory: Path = AOI_DIR) -> StudyArea:
    """A saved drawn area as a StudyArea; bulcd runs on the polygon itself
    (a single ring, so it goes straight into aoi_coordinates)."""
    ring = load_polygon(name, directory)
    return StudyArea(name, ee.Geometry.Polygon([ring]), {"aoi_coordinates": ring})


def _ring(geo_json: dict) -> list[list[float]]:
    geometry = geo_json.get("geometry", geo_json)
    if geometry.get("type") != "Polygon":
        raise ValueError(f"expected a Polygon, got {geometry.get('type')}")
    return [[float(x), float(y)] for x, y in geometry["coordinates"][0]]


def ee_tile_layer(vis_image: ee.Image, name: str, opacity: float = 1.0) -> ipyleaflet.TileLayer:
    """An already-visualized ee.Image as a map layer (standard getMapId tiles)."""
    url = vis_image.getMapId()["tile_fetcher"].url_format
    return ipyleaflet.TileLayer(url=url, name=name, opacity=opacity, attribution="Google Earth Engine")


class AOIDrawer:
    """Interactive map with a polygon/rectangle drawing tool. The most
    recently drawn shape is kept in `.ring`; `save(name)` writes it out."""

    def __init__(self, center=(46.95, -90.72), zoom=11, overlays=(), existing: list[list[float]] | None = None):
        self.ring: list[list[float]] | None = None
        self.map = ipyleaflet.Map(
            center=center, zoom=zoom, basemap=ipyleaflet.basemaps.Esri.WorldImagery, scroll_wheel_zoom=True
        )
        self.map.layout.height = "550px"
        for layer in overlays:
            self.map.add(layer)
        if existing:
            self.map.add(
                ipyleaflet.GeoJSON(
                    data={"type": "Polygon", "coordinates": [existing]},
                    style={"color": "#ffd400", "weight": 2, "fillOpacity": 0.05},
                    name="saved area",
                )
            )
            lons, lats = [p[0] for p in existing], [p[1] for p in existing]
            self.map.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
        shape = {"shapeOptions": {"color": "#00e5ff", "weight": 2, "fillOpacity": 0.05}}
        self.control = ipyleaflet.DrawControl(
            polygon=shape, rectangle=shape, polyline={}, circle={}, circlemarker={}, marker={}
        )
        self.control.on_draw(self._on_draw)
        self.map.add(self.control)
        self.map.add(ipyleaflet.LayersControl(position="topright"))

    def _on_draw(self, _control, action, geo_json):
        if action in ("created", "edited"):
            self.ring = _ring(geo_json)

    def save(self, name: str, directory: Path = AOI_DIR) -> Path | None:
        """Saves the last drawn shape as `name`. If nothing was drawn this
        session, leaves any existing saved file untouched and returns None."""
        if self.ring is None:
            return None
        return save_polygon(name, self.ring, directory)

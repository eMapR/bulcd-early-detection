"""Fixed tile grid for regional runs (no Earth Engine).

The pixel grid is NLCD's CONUS 30 m grid in EPSG:5070: verified 2026-10-22
that NLCD 2021, Annual NLCD and LCMS 2025-11 (CONUS) all sample their own
pixel centers on it, and that Earth Engine's EPSG:5070 equals their Albers
WKT to 0.1 mm (docs/findings.md, 2026-10-22). Tiles are fixed blocks of that
grid, numbered from its origin, so a tile ID means the same pixels in every
run and region.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# NLCD's CONUS grid: upper-left corner of its pixel (0, 0), EPSG:5070 meters.
NLCD_ORIGIN = (-2493045.0, 3310005.0)


@dataclass(frozen=True)
class Grid:
    crs: str = "EPSG:5070"
    scale: int = 30                       # pixel size, meters
    origin: tuple[float, float] = NLCD_ORIGIN
    # Tile edge in pixels. 10 km is not a whole number of 30 m pixels;
    # 333 pixels = 9.99 km is the closest.
    tile_px: int = 333

    @property
    def tile_m(self) -> float:
        return self.tile_px * self.scale

    @property
    def transform(self) -> list[float]:
        """Affine pixel transform (GEE crsTransform / GDAL order)."""
        return [self.scale, 0, self.origin[0], 0, -self.scale, self.origin[1]]

    def tile_index(self, x: float, y: float) -> tuple[int, int]:
        """(row, col) of the tile containing grid coordinates (x, y)."""
        return (math.floor((self.origin[1] - y) / self.tile_m), math.floor((x - self.origin[0]) / self.tile_m))

    def tile(self, row: int, col: int) -> Tile:
        x0 = self.origin[0] + col * self.tile_m
        y1 = self.origin[1] - row * self.tile_m
        return Tile(row, col, (x0, y1 - self.tile_m, x0 + self.tile_m, y1))

    def snap(self, bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """Bounds expanded outward to whole pixels."""
        ox, oy, s = self.origin[0], self.origin[1], self.scale
        return (ox + math.floor((bounds[0] - ox) / s) * s, oy - math.ceil((oy - bounds[1]) / s) * s,
                ox + math.ceil((bounds[2] - ox) / s) * s, oy - math.floor((oy - bounds[3]) / s) * s)

    def tiles(self, bounds: tuple[float, float, float, float]) -> list[Tile]:
        """Every tile that intersects `bounds` (xmin, ymin, xmax, ymax), row-major."""
        r0, c0 = self.tile_index(bounds[0], bounds[3])
        # The max edges are exclusive: a region ending exactly on a tile edge doesn't touch the next tile.
        r1, c1 = self.tile_index(bounds[2] - 1e-6, bounds[1] + 1e-6)
        return [self.tile(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)]

    def blocks(self, tiles: list[Tile], side: int) -> list[Block]:
        """The side x side-tile blocks, aligned on the grid (rows and columns
        multiples of `side`), that contain any of `tiles`; each block holds all
        its side x side tiles. Row-major."""
        keys = sorted({(t.row // side * side, t.col // side * side) for t in tiles})
        out = []
        for r0, c0 in keys:
            members = tuple(self.tile(r, c) for r in range(r0, r0 + side) for c in range(c0, c0 + side))
            out.append(Block(f"{members[0].id}_{side}x{side}", members))
        return out

    def to_dict(self) -> dict:
        return {"crs": self.crs, "scale": self.scale, "origin": list(self.origin), "tile_px": self.tile_px}

    @classmethod
    def from_dict(cls, d: dict) -> Grid:
        return cls(crs=d["crs"], scale=d["scale"], origin=tuple(d["origin"]), tile_px=d["tile_px"])


@dataclass(frozen=True)
class Tile:
    row: int
    col: int
    bounds: tuple[float, float, float, float]   # xmin, ymin, xmax, ymax in the grid CRS

    @property
    def id(self) -> str:
        return f"r{self.row:04d}c{self.col:04d}"

    def clip(self, bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        """The part of `bounds` inside this tile (a region's pixels in it)."""
        b = self.bounds
        return (max(b[0], bounds[0]), max(b[1], bounds[1]), min(b[2], bounds[2]), min(b[3], bounds[3]))


@dataclass(frozen=True)
class Block:
    """Several tiles exported by one task (as one BULC-D run and one asset).
    Tiling is exact per pixel (docs/findings.md 2026-10-24), so a block's
    pixels equal its tiles' (2026-10-26 block benchmark)."""
    id: str
    tiles: tuple[Tile, ...]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        b = [t.bounds for t in self.tiles]
        return (min(x[0] for x in b), min(x[1] for x in b), max(x[2] for x in b), max(x[3] for x in b))

    def clip(self, bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        b = self.bounds
        return (max(b[0], bounds[0]), max(b[1], bounds[1]), min(b[2], bounds[2]), min(b[3], bounds[3]))


def _transformer(crs: str, to_lonlat: bool):
    from pyproj import Transformer
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True) if to_lonlat else \
        Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def to_grid_xy(grid: Grid, lon: float, lat: float) -> tuple[float, float]:
    return _transformer(grid.crs, to_lonlat=False).transform(lon, lat)


def lonlat_ring(grid: Grid, bounds: tuple[float, float, float, float], buffer_px: int = 1,
                points_per_edge: int = 10) -> list[list[float]]:
    """Closed lon/lat ring around `bounds`, for bulcd's StudyAreaConfig.aoi_coordinates.
    Grid-CRS edges are not straight in lon/lat, so the ring is densified and
    buffered (`buffer_px` pixels) to cover every pixel of `bounds`; the backend
    exports exactly `bounds` on the grid, so the buffer never reaches the output."""
    b = buffer_px * grid.scale
    x0, y0, x1, y1 = bounds[0] - b, bounds[1] - b, bounds[2] + b, bounds[3] + b
    n = points_per_edge
    edge = lambda ax, ay, bx, by: [(ax + (bx - ax) * i / n, ay + (by - ay) * i / n) for i in range(n)]
    xy = edge(x0, y0, x1, y0) + edge(x1, y0, x1, y1) + edge(x1, y1, x0, y1) + edge(x0, y1, x0, y0)
    t = _transformer(grid.crs, to_lonlat=True)
    ring = [list(t.transform(x, y)) for x, y in xy]
    return ring + [ring[0]]


def tiles_around(grid: Grid, lon: float, lat: float, n: int = 2) -> tuple[float, float, float, float]:
    """Bounds of an n x n block of tiles centered on the tile corner nearest
    (lon, lat), for an even n (the pilot: 2 x 2, so the tile seams cross at
    the site)."""
    if n % 2:
        raise ValueError("n must be even")
    x, y = to_grid_xy(grid, lon, lat)
    col = round((x - grid.origin[0]) / grid.tile_m)
    row = round((grid.origin[1] - y) / grid.tile_m)
    h = n // 2
    return (grid.tile(row + h - 1, col - h).bounds[0], grid.tile(row + h - 1, col - h).bounds[1],
            grid.tile(row - h, col + h - 1).bounds[2], grid.tile(row - h, col + h - 1).bounds[3])

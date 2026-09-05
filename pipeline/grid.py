"""Regular lat/lon lattice over NCR and nearest-point assignment."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pipeline import config


@dataclass(frozen=True)
class GridPoint:
    grid_id: str
    lat: float
    lon: float


def make_grid(
    lat_min: float = config.LAT_MIN,
    lat_max: float = config.LAT_MAX,
    lon_min: float = config.LON_MIN,
    lon_max: float = config.LON_MAX,
    step: float = config.GRID_STEP,
) -> list[GridPoint]:
    n_rows = int(round((lat_max - lat_min) / step)) + 1
    n_cols = int(round((lon_max - lon_min) / step)) + 1
    points: list[GridPoint] = []
    for r in range(n_rows):
        for c in range(n_cols):
            points.append(
                GridPoint(
                    grid_id=f"g{r:02d}{c:02d}",
                    lat=round(lat_min + r * step, 4),
                    lon=round(lon_min + c * step, 4),
                )
            )
    return points


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_grid_id(lat: float, lon: float, grid: list[GridPoint]) -> str:
    best = min(grid, key=lambda p: haversine_km(lat, lon, p.lat, p.lon))
    return best.grid_id

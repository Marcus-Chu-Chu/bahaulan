from pipeline import config
from pipeline.grid import GridPoint, haversine_km, make_grid, nearest_grid_id


def test_grid_has_60_points_with_unique_ids():
    grid = make_grid()
    assert len(grid) == 60
    assert len({p.grid_id for p in grid}) == 60
    assert grid[0] == GridPoint("g0000", config.LAT_MIN, config.LON_MIN)
    assert grid[-1].grid_id == "g0905"
    assert abs(grid[-1].lat - config.LAT_MAX) < 1e-9
    assert abs(grid[-1].lon - config.LON_MAX) < 1e-9


def test_nearest_grid_id_snaps_to_closest_point():
    grid = make_grid()
    assert nearest_grid_id(14.35, 120.90, grid) == "g0000"
    assert nearest_grid_id(14.36, 120.92, grid) == "g0000"
    assert nearest_grid_id(14.38, 120.94, grid) == "g0101"


def test_haversine_manila_to_quezon_city():
    # Manila City Hall to Quezon Memorial Circle is roughly 9 km.
    d = haversine_km(14.5896, 120.9815, 14.6510, 121.0493)
    assert 8.5 < d < 10.5

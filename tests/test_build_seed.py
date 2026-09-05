import pandas as pd
from shapely.geometry import Polygon

from pipeline.build_seed import SEED_COLUMNS, active_grid_ids, build_seed, normalize_city


def test_normalize_city():
    assert normalize_city("City of Caloocan") == "Caloocan"
    assert normalize_city("Quezon City") == "Quezon City"
    assert normalize_city("Pateros") == "Pateros"


def test_build_seed_writes_expected_columns(tmp_path):
    poly = Polygon([(120.99, 14.59), (121.01, 14.59), (121.01, 14.61), (120.99, 14.61)])
    master = pd.DataFrame(
        {
            "pcode": ["PH1"],
            "name": ["Barangay 1"],
            "city": ["City of Manila"],
            "population": [1000],
            "score": [42.5],
            "rank_ncr": [7],
            "pct_area_mh_25": [0.25],
            "est_pop_exposed_25": [250],
        }
    )
    base = pd.DataFrame({"pcode": ["PH1"], "geometry": [poly.wkb]})
    mp, bp, out = tmp_path / "m.parquet", tmp_path / "b.parquet", tmp_path / "seed.csv"
    master.to_parquet(mp)
    base.to_parquet(bp)
    df = build_seed(mp, bp, out)
    assert list(df.columns) == SEED_COLUMNS
    assert df.loc[0, "city"] == "Manila"
    assert abs(df.loc[0, "lat"] - 14.60) < 1e-6
    assert abs(df.loc[0, "lon"] - 121.00) < 1e-6
    assert df.loc[0, "grid_id"] == "g0502"
    assert active_grid_ids(out) == ["g0502"]

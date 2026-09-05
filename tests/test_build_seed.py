import json

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS, Transformer
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


def test_build_seed_reprojects_from_declared_crs(tmp_path):
    # Known WGS84 point, reprojected into EPSG:32651 (UTM 51N) metres so the
    # test exercises build_seed's reprojection branch rather than the
    # no-"geo"-metadata identity branch that the other test covers.
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    cx, cy = to_utm.transform(121.00, 14.60)
    poly = Polygon(
        [
            (cx - 50, cy - 50),
            (cx + 50, cy - 50),
            (cx + 50, cy + 50),
            (cx - 50, cy + 50),
        ]
    )
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

    # Mirror real GeoParquet: file-level "geo" schema metadata declaring the
    # geometry column's CRS as a PROJJSON dict, as `_geometry_crs` expects.
    geo_meta = {
        "version": "1.0.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "crs": CRS.from_epsg(32651).to_json_dict(),
            }
        },
    }
    table = pa.Table.from_pandas(base, preserve_index=False)
    existing_meta = table.schema.metadata or {}
    new_meta = {**existing_meta, b"geo": json.dumps(geo_meta).encode("utf-8")}
    table = table.replace_schema_metadata(new_meta)
    pq.write_table(table, bp)

    df = build_seed(mp, bp, out)
    assert abs(df.loc[0, "lat"] - 14.60) < 1e-4
    assert abs(df.loc[0, "lon"] - 121.00) < 1e-4
    assert df.loc[0, "grid_id"] == "g0502"

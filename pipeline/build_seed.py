"""One-off: build dbt/seeds/dim_barangay.csv from BahaMap's processed tables.

Usage:
    python -m pipeline.build_seed --bahamap-dir ../bahamap/data/processed
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

from pipeline import config
from pipeline.grid import make_grid, nearest_grid_id

SEED_COLUMNS = [
    "pcode",
    "name",
    "city",
    "population",
    "score",
    "rank_ncr",
    "pct_area_mh_25",
    "est_pop_exposed_25",
    "lat",
    "lon",
    "grid_id",
]


def normalize_city(city: str) -> str:
    return re.sub(r"^City of ", "", city).strip()


def _geometry_crs(base_path: Path) -> dict | None:
    """GeoParquet stores the geometry column's CRS (PROJJSON) in file-level metadata.

    Returns None when no "geo" metadata is present (e.g. a plain DataFrame written
    with pandas), in which case geometry is assumed to already be WGS84 lon/lat.
    """
    import pyarrow.parquet as pq

    schema_meta = pq.ParquetFile(base_path).schema_arrow.metadata or {}
    raw = schema_meta.get(b"geo")
    if raw is None:
        return None
    geo = json.loads(raw)
    primary = geo.get("primary_column", "geometry")
    return geo.get("columns", {}).get(primary, {}).get("crs")


def _centroids(base: pd.DataFrame, crs: dict | None) -> pd.DataFrame:
    from shapely import wkb  # dev-only dependency

    geoms = base["geometry"].map(wkb.loads)
    xs = [g.centroid.x for g in geoms]
    ys = [g.centroid.y for g in geoms]
    if crs is None:
        lons, lats = xs, ys
    else:
        from pyproj import CRS, Transformer  # dev-only dependency

        transformer = Transformer.from_crs(CRS.from_user_input(crs), "EPSG:4326", always_xy=True)
        lons, lats = transformer.transform(xs, ys)
    return pd.DataFrame({"pcode": base["pcode"].values, "lat": lats, "lon": lons})


def build_seed(master_path: Path, base_path: Path, out_path: Path) -> pd.DataFrame:
    master = pd.read_parquet(master_path)
    base = pd.read_parquet(base_path, columns=["pcode", "geometry"])
    cent = _centroids(base, _geometry_crs(base_path))
    df = master.merge(cent, on="pcode", how="inner")
    grid = make_grid()
    df["grid_id"] = [nearest_grid_id(la, lo, grid) for la, lo in zip(df["lat"], df["lon"], strict=True)]
    df["city"] = df["city"].map(normalize_city)
    df["lat"] = df["lat"].round(6)
    df["lon"] = df["lon"].round(6)
    df["score"] = df["score"].astype(float).round(4)
    df["pct_area_mh_25"] = df["pct_area_mh_25"].astype(float).round(6)
    df = df[SEED_COLUMNS].sort_values("pcode").reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return df


def active_grid_ids(seed_path: Path = config.SEED_PATH) -> list[str]:
    ids = pd.read_csv(seed_path, usecols=["grid_id"])["grid_id"].unique().tolist()
    return sorted(ids)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bahamap-dir", required=True, type=Path)
    ap.add_argument("--out", default=config.SEED_PATH, type=Path)
    args = ap.parse_args()
    df = build_seed(
        args.bahamap_dir / "barangay_master.parquet",
        args.bahamap_dir / "barangay_base.parquet",
        args.out,
    )
    print(f"wrote {len(df)} rows, {df['grid_id'].nunique()} active grid points -> {args.out}")


if __name__ == "__main__":
    main()

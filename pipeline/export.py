"""Write dashboard extracts from the marts."""

from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from pipeline import config
from pipeline.quality import GateResult

DASHBOARD_COLUMNS = [
    "date",
    "source",
    "pcode",
    "name",
    "city",
    "population",
    "score",
    "pct_area_mh_25",
    "est_pop_exposed_25",
    "grid_id",
    "rain_mm",
    "rain_prob_max",
    "rain_hours",
    "rain_3d_mm",
    "rain_7d_mm",
    "wet_exposure",
    "max_hourly_mm",
    "warning_level",
    "run_date",
    "lat",
    "lon",
]

SOURCES = [
    "Open-Meteo forecast API (https://open-meteo.com), CC BY 4.0",
    "Open-Meteo flood API, GloFAS river discharge (Copernicus Emergency Management Service)",
    "Open-Meteo historical weather API, ERA5 reanalysis (Copernicus Climate Change Service)",
    "BahaMap barangay exposure table (NOAH hazard maps x PSGC boundaries x 2020 census)",
]
NOTE = "Rainfall and discharge are model outputs (forecasts and reanalysis), not PAGASA gauge observations."


def _dates_to_iso(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            if ((out[c].dt.normalize() == out[c]) | out[c].isna()).all():
                out[c] = out[c].dt.strftime("%Y-%m-%d")
            else:
                out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S")
        elif out[c].dtype == object and len(out) and isinstance(out[c].iloc[0], date):
            out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
    return out


def _hyper_type(s: pd.Series) -> tuple[object, pd.Series]:
    """Decide the Hyper SqlType for a column and return (SqlType, converted series).

    Null-safe: a datetime column with some NaT values is still classified as
    DATE (not TIMESTAMP) if every non-null value falls on midnight. An object
    (or nullable ``boolean`` extension) column whose non-null values are all
    Python ``bool`` is classified as BOOL rather than TEXT.
    """
    from tableauhyperapi import SqlType

    if pd.api.types.is_datetime64_any_dtype(s):
        if ((s.dt.normalize() == s) | s.isna()).all():
            return SqlType.date(), s.dt.date
        return SqlType.timestamp(), s.dt.to_pydatetime()
    if pd.api.types.is_bool_dtype(s):
        return SqlType.bool(), s
    if pd.api.types.is_integer_dtype(s):
        return SqlType.big_int(), s
    if pd.api.types.is_float_dtype(s):
        return SqlType.double(), s

    non_null = s[s.notna()]
    if (s.dtype == object or str(s.dtype) == "boolean") and len(non_null) and non_null.map(
        lambda v: isinstance(v, bool)
    ).all():
        return SqlType.bool(), s
    if len(non_null) and isinstance(non_null.iloc[0], date):
        return SqlType.date(), s
    return SqlType.text(), s.astype("string")


def write_hyper(df: pd.DataFrame, path: Path, table_name: str = "dashboard") -> None:
    from tableauhyperapi import (
        Connection,
        CreateMode,
        HyperProcess,
        Inserter,
        TableDefinition,
        TableName,
        Telemetry,
    )

    cols = []
    frame = df.copy()
    for c in frame.columns:
        sql_type, converted = _hyper_type(frame[c])
        frame[c] = converted
        cols.append(TableDefinition.Column(c, sql_type))
    frame = frame.astype(object).where(frame.notna(), None)
    table = TableDefinition(TableName(table_name), cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    with HyperProcess(
        telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
        parameters={"log_dir": str(path.parent)},
    ) as hp:
        with Connection(hp.endpoint, str(path), CreateMode.CREATE_AND_REPLACE) as con:
            con.catalog.create_table(table)
            with Inserter(con, table) as ins:
                ins.add_rows(frame.itertuples(index=False, name=None))
                ins.execute()


def _df(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()


def export_all(
    con: duckdb.DuckDBPyConnection,
    run_date: date,
    gates: list[GateResult],
    export_dir: Path = config.EXPORT_DIR,
) -> dict:
    """Write every export file, then publish them atomically.

    Everything is written into a temporary sibling directory first; only once all writes
    have succeeded are the files moved into ``export_dir``. That way a failure partway
    through (a bad query, a Hyper API error, disk full) never leaves ``export_dir`` holding
    a stale mix of some-new/some-old files -- readers either see the complete previous
    export or the complete new one, never a partial one.
    """
    tmp_dir = export_dir.parent / (export_dir.name + ".tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        dash = _df(con, "select * from mart_dashboard order by date, pcode")[DASHBOARD_COLUMNS]
        _dates_to_iso(dash).to_csv(tmp_dir / "dashboard.csv", index=False)
        dash.to_parquet(tmp_dir / "dashboard.parquet", index=False)
        write_hyper(dash, tmp_dir / "dashboard.hyper")

        _dates_to_iso(_df(con, "select * from fct_warnings_hourly order by grid_id, ts")).to_csv(
            tmp_dir / "warnings.csv", index=False
        )
        _dates_to_iso(_df(con, "select * from fct_river_grid_daily order by grid_id, date")).to_csv(
            tmp_dir / "river.csv", index=False
        )
        _dates_to_iso(_df(con, "select * from mart_monthly_normal order by year, month")).to_csv(
            tmp_dir / "monthly_normal.csv", index=False
        )

        latest_obs = con.execute(
            "select max(date) from mart_dashboard where source = 'observed'"
        ).fetchone()[0]
        through = con.execute("select max(date) from mart_dashboard").fetchone()[0]
        grids = con.execute("select count(distinct grid_id) from mart_dashboard").fetchone()[0]
        meta = {
            "run_date": run_date.isoformat(),
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "dashboard_rows": int(len(dash)),
            "latest_observed_date": str(latest_obs)[:10] if latest_obs else None,
            "forecast_through": str(through)[:10] if through else None,
            "active_grid_points": int(grids),
            "gates": {g.name: "pass" if g.passed else "fail" for g in gates},
            "sources": SOURCES,
            "note": NOTE,
        }
        (tmp_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        written = [
            "dashboard.csv",
            "dashboard.parquet",
            "dashboard.hyper",
            "warnings.csv",
            "river.csv",
            "monthly_normal.csv",
            "metadata.json",
        ]

        export_dir.mkdir(parents=True, exist_ok=True)
        for name in written:
            os.replace(tmp_dir / name, export_dir / name)
        hyper_log = tmp_dir / "hyperd.log"
        if hyper_log.exists():
            os.replace(hyper_log, export_dir / "hyperd.log")
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
    return {"dashboard_rows": int(len(dash)), "files": sorted(written)}

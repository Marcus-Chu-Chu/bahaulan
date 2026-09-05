"""Write dashboard extracts from the marts."""

from __future__ import annotations

import json
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
            if (out[c].dt.normalize() == out[c]).all():
                out[c] = out[c].dt.strftime("%Y-%m-%d")
            else:
                out[c] = out[c].dt.strftime("%Y-%m-%dT%H:%M:%S")
        elif out[c].dtype == object and len(out) and isinstance(out[c].iloc[0], date):
            out[c] = out[c].map(lambda d: d.isoformat() if d is not None else None)
    return out


def write_hyper(df: pd.DataFrame, path: Path, table_name: str = "dashboard") -> None:
    from tableauhyperapi import (
        Connection,
        CreateMode,
        HyperProcess,
        Inserter,
        SqlType,
        TableDefinition,
        TableName,
        Telemetry,
    )

    cols = []
    frame = df.copy()
    for c in frame.columns:
        s = frame[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            if (s.dt.normalize() == s).all():
                frame[c] = s.dt.date
                cols.append(TableDefinition.Column(c, SqlType.date()))
            else:
                frame[c] = s.dt.to_pydatetime()
                cols.append(TableDefinition.Column(c, SqlType.timestamp()))
        elif pd.api.types.is_bool_dtype(s):
            cols.append(TableDefinition.Column(c, SqlType.bool()))
        elif pd.api.types.is_integer_dtype(s):
            cols.append(TableDefinition.Column(c, SqlType.big_int()))
        elif pd.api.types.is_float_dtype(s):
            cols.append(TableDefinition.Column(c, SqlType.double()))
        elif len(s) and isinstance(s.dropna().iloc[0] if s.notna().any() else None, date):
            cols.append(TableDefinition.Column(c, SqlType.date()))
        else:
            frame[c] = s.astype("string")
            cols.append(TableDefinition.Column(c, SqlType.text()))
    frame = frame.astype(object).where(frame.notna(), None)
    table = TableDefinition(TableName(table_name), cols)
    path.parent.mkdir(parents=True, exist_ok=True)
    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
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
    export_dir.mkdir(parents=True, exist_ok=True)
    dash = _df(con, "select * from mart_dashboard order by date, pcode")[DASHBOARD_COLUMNS]
    _dates_to_iso(dash).to_csv(export_dir / "dashboard.csv", index=False)
    dash.to_parquet(export_dir / "dashboard.parquet", index=False)
    write_hyper(dash, export_dir / "dashboard.hyper")

    _dates_to_iso(_df(con, "select * from fct_warnings_hourly order by grid_id, ts")).to_csv(
        export_dir / "warnings.csv", index=False
    )
    _dates_to_iso(_df(con, "select * from fct_river_grid_daily order by grid_id, date")).to_csv(
        export_dir / "river.csv", index=False
    )
    _dates_to_iso(_df(con, "select * from mart_monthly_normal order by year, month")).to_csv(
        export_dir / "monthly_normal.csv", index=False
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
    (export_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"dashboard_rows": int(len(dash)), "files": sorted(p.name for p in export_dir.iterdir())}

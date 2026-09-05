"""Flatten raw Open-Meteo snapshots and rebuild the DuckDB `raw` schema from all of them."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from pipeline import config

FORECAST_DAILY_COLS = [
    "run_date",
    "grid_id",
    "date",
    "precipitation_sum",
    "precipitation_probability_max",
    "precipitation_hours",
    "fetched_at",
]
FORECAST_HOURLY_COLS = ["run_date", "grid_id", "ts", "precipitation", "fetched_at"]
FLOOD_DAILY_COLS = [
    "run_date",
    "grid_id",
    "date",
    "river_discharge",
    "river_discharge_max",
    "fetched_at",
]
ARCHIVE_DAILY_COLS = ["grid_id", "date", "precipitation_sum", "precipitation_hours", "fetched_at"]

_FLOAT_COLS = {
    "precipitation_sum",
    "precipitation_probability_max",
    "precipitation_hours",
    "precipitation",
    "river_discharge",
    "river_discharge_max",
}
_DATE_COLS = {"run_date", "date"}
_TS_COLS = {"ts", "fetched_at"}


def _duck_type(col: str) -> str:
    if col in _FLOAT_COLS:
        return "DOUBLE"
    if col in _DATE_COLS:
        return "DATE"
    if col in _TS_COLS:
        return "TIMESTAMP"
    return "VARCHAR"


def _fetched_at(payload: dict) -> pd.Timestamp:
    return pd.Timestamp(payload["fetched_at"]).tz_convert(None)


def _daily_rows(payload: dict, fields: list[str], with_run_date: bool) -> list[dict]:
    rows = []
    fa = _fetched_at(payload)
    for pt in payload["points"]:
        daily = pt["response"]["daily"]
        for i, day in enumerate(daily["time"]):
            row = {"grid_id": pt["grid_id"], "date": day, "fetched_at": fa}
            if with_run_date:
                row["run_date"] = payload["run_date"]
            for f in fields:
                row[f] = daily[f][i]
            rows.append(row)
    return rows


def _typed(rows: list[dict], cols: list[str]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=cols)
    for c in cols:
        if c in _FLOAT_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float64")
        elif c in _DATE_COLS or c in _TS_COLS:
            # Keep as datetime64 (not .dt.date / python date objects): pandas
            # compares datetime64 to date-like strings elementwise, but a
            # column of plain datetime.date objects compares False against
            # every string. DuckDB storage type (DATE vs TIMESTAMP) is
            # enforced separately via CAST in _create, so the pandas dtype
            # here doesn't need to match the final column type.
            df[c] = pd.to_datetime(df[c])
        else:
            df[c] = df[c].astype("string")
    return df[cols]


def flatten_forecast(payload: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = _typed(
        _daily_rows(
            payload,
            ["precipitation_sum", "precipitation_probability_max", "precipitation_hours"],
            True,
        ),
        FORECAST_DAILY_COLS,
    )
    hrows = []
    fa = _fetched_at(payload)
    for pt in payload["points"]:
        hourly = pt["response"]["hourly"]
        for ts, mm in zip(hourly["time"], hourly["precipitation"], strict=True):
            hrows.append(
                {
                    "run_date": payload["run_date"],
                    "grid_id": pt["grid_id"],
                    "ts": ts,
                    "precipitation": mm,
                    "fetched_at": fa,
                }
            )
    return daily, _typed(hrows, FORECAST_HOURLY_COLS)


def flatten_flood(payload: dict) -> pd.DataFrame:
    return _typed(
        _daily_rows(payload, ["river_discharge", "river_discharge_max"], True), FLOOD_DAILY_COLS
    )


def flatten_archive(payload: dict) -> pd.DataFrame:
    return _typed(
        _daily_rows(payload, ["precipitation_sum", "precipitation_hours"], False),
        ARCHIVE_DAILY_COLS,
    )


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _concat(frames: list[pd.DataFrame], cols: list[str]) -> pd.DataFrame:
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else _typed([], cols)


def _create(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame, cols: list[str]) -> None:
    decl = ", ".join(f"{c} {_duck_type(c)}" for c in cols)
    con.execute(f"CREATE OR REPLACE TABLE raw.{name} ({decl})")
    if len(df):
        con.register("df_tmp", df)
        select_cols = ", ".join(f"CAST({c} AS {_duck_type(c)})" for c in cols)
        con.execute(f"INSERT INTO raw.{name} SELECT {select_cols} FROM df_tmp")
        con.unregister("df_tmp")


def load_all(raw_dir: Path = config.RAW_DIR, db_path: Path = config.DB_PATH) -> dict[str, int]:
    fd, fh, fl, ar = [], [], [], []
    for run_dir in sorted(p for p in raw_dir.iterdir() if p.is_dir() and p.name != "archive"):
        f_path, l_path = run_dir / "forecast.json", run_dir / "flood.json"
        if f_path.exists():
            d, h = flatten_forecast(_read(f_path))
            fd.append(d)
            fh.append(h)
        if l_path.exists():
            fl.append(flatten_flood(_read(l_path)))
    archive_dir = raw_dir / "archive"
    if archive_dir.exists():
        for a_path in sorted(archive_dir.glob("*.json")):
            ar.append(flatten_archive(_read(a_path)))

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        tables = {
            "forecast_daily": (_concat(fd, FORECAST_DAILY_COLS), FORECAST_DAILY_COLS),
            "forecast_hourly": (_concat(fh, FORECAST_HOURLY_COLS), FORECAST_HOURLY_COLS),
            "flood_daily": (_concat(fl, FLOOD_DAILY_COLS), FLOOD_DAILY_COLS),
            "archive_daily": (_concat(ar, ARCHIVE_DAILY_COLS), ARCHIVE_DAILY_COLS),
        }
        counts = {}
        for name, (df, cols) in tables.items():
            _create(con, name, df, cols)
            counts[name] = int(con.execute(f"SELECT count(*) FROM raw.{name}").fetchone()[0])
        return counts
    finally:
        con.close()

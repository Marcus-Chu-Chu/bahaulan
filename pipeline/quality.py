"""Pre-dbt data-quality gates on the raw schema. All must pass or the run stops."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import duckdb

from pipeline import config


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str


def _freshness(con: duckdb.DuckDBPyConnection, run_date: date) -> GateResult:
    max_date = con.execute(
        "select max(date) from raw.forecast_daily where run_date = ?", [run_date]
    ).fetchone()[0]
    need = run_date + timedelta(days=config.MIN_FORECAST_HORIZON_DAYS)
    ok = max_date is not None and max_date >= need
    return GateResult("freshness", ok, f"max forecast date {max_date}, need >= {need}")


def _coverage(con: duckdb.DuckDBPyConnection, run_date: date, active: list[str]) -> GateResult:
    missing = []
    for table in ("forecast_daily", "flood_daily"):
        have = {
            r[0]
            for r in con.execute(
                f"select distinct grid_id from raw.{table} where run_date = ?", [run_date]
            ).fetchall()
        }
        gap = sorted(set(active) - have)
        if gap:
            missing.append(f"{table} missing {gap}")
    return GateResult("coverage", not missing, "; ".join(missing) or f"{len(active)} grid points present")


def _null_share(con: duckdb.DuckDBPyConnection, run_date: date) -> GateResult:
    share = con.execute(
        "select coalesce(avg(case when precipitation_sum is null then 1.0 else 0.0 end), 1.0) "
        "from raw.forecast_daily where run_date = ?",
        [run_date],
    ).fetchone()[0]
    return GateResult("null_share", share <= config.MAX_NULL_SHARE, f"null share {share:.3f} (max {config.MAX_NULL_SHARE})")


def _ranges(con: duckdb.DuckDBPyConnection, run_date: date) -> GateResult:
    bad_rain = con.execute(
        "select count(*) from raw.forecast_daily where run_date = ? and (precipitation_sum < 0 or precipitation_sum > ?)",
        [run_date, config.MAX_DAILY_MM],
    ).fetchone()[0]
    bad_flow = con.execute(
        "select count(*) from raw.flood_daily where run_date = ? and (river_discharge < 0 or river_discharge_max < 0)",
        [run_date],
    ).fetchone()[0]
    ok = bad_rain == 0 and bad_flow == 0
    return GateResult("ranges", ok, f"{bad_rain} rain rows out of range, {bad_flow} discharge rows negative")


def run_gates(con: duckdb.DuckDBPyConnection, run_date: date, active_grid_ids: list[str]) -> list[GateResult]:
    return [
        _freshness(con, run_date),
        _coverage(con, run_date, active_grid_ids),
        _null_share(con, run_date),
        _ranges(con, run_date),
    ]


def all_passed(results: list[GateResult]) -> bool:
    return all(r.passed for r in results)


def format_gates(results: list[GateResult]) -> str:
    return ";".join(f"{r.name}={'pass' if r.passed else 'fail(' + r.detail + ')'}" for r in results)

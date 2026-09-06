"""The BahaUlan DAG: fetch -> load -> quality -> dbt build -> export -> summary.

The run log (``logs/runs.csv``) records one row per invocation with a ``status`` of:

- ``ok``: every stage completed and exports were written.
- ``fetch_failed``: Open-Meteo could not be reached after retries.
- ``gate_failed``: a pre-dbt data-quality gate failed (see ``pipeline.quality``).
- ``dbt_failed``: the dbt build (models or tests) failed.
- ``error``: any other unexpected exception; caught so a bug never leaves a run unlogged.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from pipeline import config
from pipeline.build_seed import active_grid_ids
from pipeline.dbt_runner import run_dbt
from pipeline.export import export_all
from pipeline.fetch import FetchError, fetch_archive_if_needed, fetch_daily
from pipeline.grid import GridPoint, make_grid
from pipeline.load import load_all
from pipeline.quality import all_passed, format_gates, run_gates

LOG_COLUMNS = [
    "run_date", "started_at_utc", "duration_s", "status", "forecast_rows", "flood_rows",
    "archive_rows", "dashboard_rows", "gates",
]


def manila_today() -> date:
    return datetime.now(ZoneInfo(config.TIMEZONE)).date()


def latest_snapshot_date(raw_dir: Path = config.RAW_DIR) -> date | None:
    dates = []
    for p in raw_dir.iterdir() if raw_dir.exists() else []:
        if p.is_dir():
            try:
                dates.append(date.fromisoformat(p.name))
            except ValueError:
                continue
    return max(dates) if dates else None


def active_points() -> list[GridPoint]:
    wanted = set(active_grid_ids())
    return [p for p in make_grid() if p.grid_id in wanted]


def append_log(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LOG_COLUMNS})


def _summary(row: dict, gates_detail: list[str]) -> str:
    lines = ["## BahaUlan run", "", "| field | value |", "|---|---|"]
    lines += [f"| {k} | {row.get(k, '')} |" for k in LOG_COLUMNS if k != "gates"]
    if gates_detail:
        lines += ["", "### Gates", ""] + [f"- {g}" for g in gates_detail]
    return "\n".join(lines) + "\n"


def _emit(row: dict, gates_detail: list[str]) -> None:
    text = _summary(row, gates_detail)
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with Path(step).open("a", encoding="utf-8") as fh:
            fh.write(text)
    env = os.environ.get("GITHUB_ENV")
    if env:
        with Path(env).open("a", encoding="utf-8") as fh:
            fh.write(f"RUN_DATE={row['run_date']}\n")
    print(text)


def run(
    run_date: date,
    offline: bool,
    raw_dir: Path = config.RAW_DIR,
    db_path: Path = config.DB_PATH,
    export_dir: Path = config.EXPORT_DIR,
    log_path: Path = config.LOG_PATH,
) -> int:
    t0 = time.time()
    row = {"run_date": run_date.isoformat(), "started_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    gates_detail: list[str] = []

    def finish(status: str) -> int:
        row["status"] = status
        row["duration_s"] = f"{time.time() - t0:.1f}"
        append_log(log_path, row)
        _emit(row, gates_detail)
        return 0 if status == "ok" else 1

    try:
        points = active_points()
        if not offline:
            try:
                fetch_daily(run_date, points, raw_dir=raw_dir)
                fetch_archive_if_needed(run_date, points, archive_dir=raw_dir / "archive")
            except FetchError as exc:
                row["gates"] = f"fetch_error({exc})"
                return finish("fetch_failed")

        counts = load_all(raw_dir=raw_dir, db_path=db_path)
        row.update(
            forecast_rows=counts["forecast_daily"],
            flood_rows=counts["flood_daily"],
            archive_rows=counts["archive_daily"],
        )

        con = duckdb.connect(str(db_path))
        try:
            gates = run_gates(con, run_date, [p.grid_id for p in points])
        finally:
            con.close()
        row["gates"] = format_gates(gates)
        gates_detail = [f"{g.name}: {'PASS' if g.passed else 'FAIL'} ({g.detail})" for g in gates]
        if not all_passed(gates):
            return finish("gate_failed")

        try:
            run_dbt(db_path)
        except RuntimeError as exc:
            row["gates"] += f";dbt=fail({exc})"
            return finish("dbt_failed")

        con = duckdb.connect(str(db_path), read_only=True)
        try:
            info = export_all(con, run_date, gates, export_dir=export_dir)
        finally:
            con.close()
        row["dashboard_rows"] = info["dashboard_rows"]
        return finish("ok")
    except Exception as exc:  # noqa: BLE001 -- the orchestrator's job is to record every failure, however it happens, as a log row rather than an unhandled traceback
        row["gates"] = f"error({type(exc).__name__}: {exc})"
        return finish("error")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the BahaUlan pipeline.")
    ap.add_argument("--date", type=date.fromisoformat, default=None, help="run date (Asia/Manila); default today")
    ap.add_argument("--offline", action="store_true", help="skip fetching; use snapshots on disk")
    args = ap.parse_args(argv)
    run_date = args.date
    if run_date is None:
        run_date = (latest_snapshot_date() or manila_today()) if args.offline else manila_today()
    return run(run_date, args.offline)


if __name__ == "__main__":
    sys.exit(main())

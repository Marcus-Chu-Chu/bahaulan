import copy
import json
import shutil
from datetime import datetime
from pathlib import Path

import duckdb
import pytest

from pipeline.load import flatten_archive, flatten_flood, flatten_forecast, load_all

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_flatten_forecast_daily_and_hourly():
    payload = json.loads((FIX / "2026-09-04" / "forecast.json").read_text())
    daily, hourly = flatten_forecast(payload)
    assert len(daily) == 4 and len(hourly) == 8
    assert list(daily.columns) == ["run_date", "grid_id", "date", "precipitation_sum", "precipitation_probability_max", "precipitation_hours", "fetched_at"]
    row = daily[(daily.grid_id == "g0502") & (daily.date == "2026-09-03")].iloc[0]
    assert row.precipitation_sum == 12.5
    assert daily.precipitation_sum.isna().sum() == 1
    assert hourly.precipitation.max() == 31.0


def test_flatten_forecast_rejects_misaligned_daily_arrays():
    payload = copy.deepcopy(json.loads((FIX / "2026-09-04" / "forecast.json").read_text()))
    payload["points"][0]["response"]["daily"]["precipitation_sum"].append(99.0)
    with pytest.raises(ValueError):
        flatten_forecast(payload)


def test_flatten_flood_and_archive():
    flood = flatten_flood(json.loads((FIX / "2026-09-04" / "flood.json").read_text()))
    assert len(flood) == 4 and flood.river_discharge_max.max() == 6.5
    arch = flatten_archive(json.loads((FIX / "archive" / "2026-08-25_2026-08-30.json").read_text()))
    assert len(arch) == 12 and list(arch.columns) == ["grid_id", "date", "precipitation_sum", "precipitation_hours", "fetched_at"]


def test_load_all_builds_raw_schema(tmp_path):
    db = tmp_path / "t.duckdb"
    counts = load_all(raw_dir=FIX, db_path=db)
    assert counts == {"forecast_daily": 4, "forecast_hourly": 8, "flood_daily": 4, "archive_daily": 12}
    con = duckdb.connect(str(db), read_only=True)
    types = dict(con.execute("select column_name, data_type from information_schema.columns where table_schema='raw' and table_name='forecast_daily'").fetchall())
    assert types["date"] == "DATE" and types["run_date"] == "DATE" and types["fetched_at"] == "TIMESTAMP"
    assert con.execute("select count(*) from raw.forecast_daily where precipitation_sum is null").fetchone()[0] == 1
    con.close()


def test_load_all_with_no_archive_creates_empty_table(tmp_path):
    raw = tmp_path / "raw"
    (raw / "2026-09-04").mkdir(parents=True)
    for name in ("forecast.json", "flood.json"):
        (raw / "2026-09-04" / name).write_text((FIX / "2026-09-04" / name).read_text())
    counts = load_all(raw_dir=raw, db_path=tmp_path / "e.duckdb")
    assert counts["archive_daily"] == 0


def test_load_all_missing_raw_dir_creates_empty_tables(tmp_path):
    counts = load_all(raw_dir=tmp_path / "does-not-exist", db_path=tmp_path / "m.duckdb")
    assert counts == {"forecast_daily": 0, "forecast_hourly": 0, "flood_daily": 0, "archive_daily": 0}
    con = duckdb.connect(str(tmp_path / "m.duckdb"), read_only=True)
    types = dict(
        con.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema='raw' and table_name='forecast_daily'"
        ).fetchall()
    )
    assert types == {
        "run_date": "DATE",
        "grid_id": "VARCHAR",
        "date": "DATE",
        "precipitation_sum": "DOUBLE",
        "precipitation_probability_max": "DOUBLE",
        "precipitation_hours": "DOUBLE",
        "fetched_at": "TIMESTAMP",
    }
    con.close()


def test_load_all_accumulates_runs_and_is_idempotent(tmp_path):
    raw = tmp_path / "raw"
    shutil.copytree(FIX, raw)
    second = raw / "2026-09-05"
    second.mkdir()
    for name in ("forecast.json", "flood.json"):
        text = (FIX / "2026-09-04" / name).read_text().replace(
            '"run_date":"2026-09-04"', '"run_date":"2026-09-05"'
        )
        (second / name).write_text(text)

    db = tmp_path / "acc.duckdb"
    expected = {"forecast_daily": 8, "forecast_hourly": 16, "flood_daily": 8, "archive_daily": 12}
    for _ in range(2):
        counts = load_all(raw_dir=raw, db_path=db)
        assert counts == expected

    con = duckdb.connect(str(db), read_only=True)
    fetched_at = con.execute("select fetched_at from raw.forecast_daily limit 1").fetchone()[0]
    assert fetched_at == datetime(2026, 9, 3, 22, 1)
    con.close()


def test_load_all_caps_hourly_and_flood_at_the_newest_run_dirs(tmp_path):
    from datetime import date, timedelta

    from pipeline import config

    raw = tmp_path / "raw"
    raw.mkdir()
    total = config.HOURLY_RUN_DIRS + 2
    for i in range(total):
        day = (date(2026, 9, 4) + timedelta(days=i)).isoformat()
        run_dir = raw / day
        run_dir.mkdir()
        for name in ("forecast.json", "flood.json"):
            text = (FIX / "2026-09-04" / name).read_text().replace(
                '"run_date":"2026-09-04"', f'"run_date":"{day}"'
            )
            (run_dir / name).write_text(text)

    counts = load_all(raw_dir=raw, db_path=tmp_path / "cap.duckdb")
    # Every run contributes daily rows; only the newest HOURLY_RUN_DIRS contribute hourly
    # and flood rows, which is all downstream reads.
    assert counts["forecast_daily"] == total * 4
    assert counts["forecast_hourly"] == config.HOURLY_RUN_DIRS * 8
    assert counts["flood_daily"] == config.HOURLY_RUN_DIRS * 4

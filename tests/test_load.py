import json
from pathlib import Path

import duckdb

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

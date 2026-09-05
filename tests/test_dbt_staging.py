import json
import shutil
from pathlib import Path

import duckdb
import pytest

from pipeline.dbt_runner import run_dbt
from pipeline.load import load_all

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_staging_builds_and_dedupes(tmp_path):
    db = tmp_path / "s.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    run_dbt(db, select="dim_barangay stg_forecast_daily stg_forecast_hourly stg_flood_daily stg_archive_daily")
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("select count(*) from dim_barangay").fetchone()[0] == 1710
    assert con.execute("select count(*) from stg_forecast_daily").fetchone()[0] == 4
    assert con.execute("select count(*) from stg_archive_daily").fetchone()[0] == 11  # one null dropped
    con.close()


def test_archive_latest_valid_snapshot_wins(tmp_path):
    raw_dir = tmp_path / "raw"
    shutil.copytree(FIX, raw_dir)

    # A later snapshot re-fetches the same date range: g0502/2026-08-25 comes back
    # null this time (should NOT hide the earlier valid 7.0), and g0502/2026-08-26
    # comes back with a distinct new value (the latest *valid* value should win).
    second = {
        "kind": "archive",
        "run_date": "2026-09-05",
        "fetched_at": "2026-09-04T10:00:00+00:00",
        "points": [
            {
                "grid_id": "g0502",
                "lat": 14.6,
                "lon": 121.0,
                "response": {
                    "daily": {
                        "time": ["2026-08-25", "2026-08-26"],
                        "precipitation_sum": [None, 99.0],
                        "precipitation_hours": [0, 9],
                    }
                },
            }
        ],
    }
    (raw_dir / "archive" / "2026-08-25_2026-08-30_b.json").write_text(json.dumps(second), encoding="utf-8")

    db = tmp_path / "s.duckdb"
    load_all(raw_dir=raw_dir, db_path=db)
    run_dbt(db, select="stg_archive_daily")

    con = duckdb.connect(str(db), read_only=True)
    row_25 = con.execute(
        "select precipitation_sum from stg_archive_daily where grid_id = 'g0502' and date = '2026-08-25'"
    ).fetchone()
    row_26 = con.execute(
        "select precipitation_sum from stg_archive_daily where grid_id = 'g0502' and date = '2026-08-26'"
    ).fetchone()
    con.close()

    assert row_25[0] == 7.0  # earlier valid value survives a later null
    assert row_26[0] == 99.0  # latest valid value wins over the earlier one


def test_run_dbt_reports_failing_nodes(tmp_path):
    db = tmp_path / "s.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    run_dbt(db, select="stg_forecast_daily")

    con = duckdb.connect(str(db))
    con.execute("update raw.forecast_daily set precipitation_sum = 999")
    con.close()

    with pytest.raises(RuntimeError, match="accepted_range"):
        run_dbt(db, select="stg_forecast_daily", command="test")

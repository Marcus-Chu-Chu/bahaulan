from pathlib import Path

import duckdb

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

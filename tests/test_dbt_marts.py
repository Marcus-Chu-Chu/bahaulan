from datetime import date
from pathlib import Path

import duckdb

from pipeline.dbt_runner import run_dbt
from pipeline.load import load_all

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_marts_build(tmp_path):
    db = tmp_path / "m.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    # Full build: fixture dashboard coverage test is expected to FAIL (only 2 grid points), so
    # build everything except that singular test.
    run_dbt(db, exclude="assert_dashboard_full_coverage")

    con = duckdb.connect(str(db), read_only=True)
    cols = [r[0] for r in con.execute("describe mart_dashboard").fetchall()]
    assert cols == [
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
    # g0502 on 2026-09-03: hourly max 31 -> red
    lvl = con.execute(
        "select warning_level from fct_rain_barangay_daily where grid_id='g0502' and date=date '2026-09-03' limit 1"
    ).fetchone()[0]
    assert lvl == "red"
    # observed beats forecast; forecast fills only missing dates
    src = dict(
        con.execute(
            "select date, source from int_rain_daily_unioned where grid_id='g0502' and date in (date '2026-08-30', date '2026-09-03')"
        ).fetchall()
    )
    assert src[date(2026, 8, 30)] == "observed" and src[date(2026, 9, 3)] == "forecast"
    assert con.execute("select count(*) from mart_monthly_normal").fetchone()[0] >= 1
    assert con.execute("select count(*) from fct_river_grid_daily").fetchone()[0] == 4
    con.close()

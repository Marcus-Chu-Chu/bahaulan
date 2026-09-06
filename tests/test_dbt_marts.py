from datetime import date
from pathlib import Path

import duckdb
import pytest

from pipeline.dbt_runner import run_dbt
from pipeline.load import load_all

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_marts_build(tmp_path):
    db = tmp_path / "m.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    # Full build: fixture dashboard coverage test is expected to FAIL (only 2 grid points), and
    # the fixture's archive (08-25..08-30) and forecast (09-03..09-04) snapshots leave a
    # calendar-date gap (08-31..09-02), so exclude both singular tests that would fail on it.
    run_dbt(db, exclude="assert_dashboard_full_coverage assert_dashboard_date_continuity")

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

    cols = [r[0] for r in con.execute("describe fct_warnings_hourly").fetchall()]
    assert cols == ["run_date", "grid_id", "ts", "date", "mm_per_hour", "warning_level"]

    cols = [r[0] for r in con.execute("describe fct_river_grid_daily").fetchall()]
    assert cols == [
        "run_date",
        "grid_id",
        "date",
        "source",
        "river_discharge",
        "river_discharge_max",
        "cities_served",
    ]

    cols = [r[0] for r in con.execute("describe mart_monthly_normal").fetchall()]
    assert cols == [
        "year",
        "month",
        "month_start",
        "total_mm",
        "normal_mm",
        "p10_mm",
        "p90_mm",
        "is_current_year",
        "days_covered",
        "is_complete",
    ]

    # g0502 rain_3d_mm on 2026-08-27 sums the 3-day window ending that date: 08-25, 08-26, 08-27
    rain_3d = con.execute(
        "select rain_3d_mm from int_rain_rolling where grid_id='g0502' and date=date '2026-08-27'"
    ).fetchone()[0]
    assert rain_3d == pytest.approx(7.0 + 17.2 + 40.9)

    con.close()

from datetime import date
from pathlib import Path

import duckdb
import pytest

from pipeline.load import load_all
from pipeline.quality import all_passed, format_gates, run_gates

FIX = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture
def con(tmp_path):
    db = tmp_path / "q.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def test_gates_on_fixture(con):
    res = run_gates(con, date(2026, 9, 4), ["g0502", "g0503"])
    by = {r.name: r for r in res}
    assert set(by) == {"freshness", "coverage", "null_share", "ranges"}
    assert not by["freshness"].passed
    assert by["coverage"].passed
    assert not by["null_share"].passed
    assert by["ranges"].passed
    assert not all_passed(res)
    assert "freshness=fail" in format_gates(res) and "coverage=pass" in format_gates(res)


def test_coverage_fails_when_grid_missing(con):
    res = run_gates(con, date(2026, 9, 4), ["g0502", "g0503", "g0000"])
    by = {r.name: r for r in res}
    assert not by["coverage"].passed and "g0000" in by["coverage"].detail


def test_ranges_fail_on_negative_discharge(con):
    con.execute("update raw.flood_daily set river_discharge = -1 where grid_id = 'g0502' and date = date '2026-09-03'")
    by = {r.name: r for r in run_gates(con, date(2026, 9, 4), ["g0502", "g0503"])}
    assert not by["ranges"].passed


def test_all_pass_on_good_data(con):
    con.execute("update raw.forecast_daily set precipitation_sum = 0 where precipitation_sum is null")
    con.execute("insert into raw.forecast_daily select run_date, grid_id, date '2026-09-10', 1.0, 1.0, 1.0, fetched_at from raw.forecast_daily where date = date '2026-09-04'")
    assert all_passed(run_gates(con, date(2026, 9, 4), ["g0502", "g0503"]))

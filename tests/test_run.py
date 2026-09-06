import csv
from datetime import date
from pathlib import Path

from pipeline import run as runmod

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_latest_snapshot_date():
    assert runmod.latest_snapshot_date(FIX) == date(2026, 9, 4)


def test_active_points_come_from_seed():
    pts = runmod.active_points()
    assert 30 <= len(pts) <= 60
    assert all(p.grid_id.startswith("g") for p in pts)


def test_offline_run_on_fixture_stops_at_gates(tmp_path):
    rc = runmod.run(
        run_date=date(2026, 9, 4), offline=True, raw_dir=FIX, db_path=tmp_path / "r.duckdb",
        export_dir=tmp_path / "exports", log_path=tmp_path / "runs.csv",
    )
    assert rc == 1  # fixture fails freshness/null gates by design
    rows = list(csv.DictReader((tmp_path / "runs.csv").open()))
    assert rows[0]["status"] == "gate_failed" and "freshness=fail" in rows[0]["gates"]
    assert not (tmp_path / "exports").exists()

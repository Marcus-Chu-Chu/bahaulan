import csv
from datetime import date
from pathlib import Path

from pipeline import run as runmod

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_latest_snapshot_date():
    assert runmod.latest_snapshot_date(FIX) == date(2026, 9, 4)


def test_active_points_come_from_seed():
    pts = runmod.active_points()
    assert len(pts) == 31
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


def test_run_logs_unexpected_error(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(runmod, "load_all", boom)
    rc = runmod.run(
        run_date=date(2026, 9, 4), offline=True, raw_dir=FIX, db_path=tmp_path / "r.duckdb",
        export_dir=tmp_path / "exports", log_path=tmp_path / "runs.csv",
    )
    assert rc == 1
    rows = list(csv.DictReader((tmp_path / "runs.csv").open()))
    assert rows[0]["status"] == "error"
    assert "boom" in rows[0]["gates"]


def test_emit_writes_github_files(tmp_path, monkeypatch):
    summary_path = tmp_path / "summary.md"
    env_path = tmp_path / "env.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("GITHUB_ENV", str(env_path))
    row = {"run_date": "2026-09-04", "started_at_utc": "x", "duration_s": "1.0", "status": "ok"}
    runmod._emit(row, ["freshness: PASS (x)"])
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "## BahaUlan run" in summary_text
    assert "freshness: PASS (x)" in summary_text
    env_text = env_path.read_text(encoding="utf-8")
    assert f"RUN_DATE={row['run_date']}" in env_text

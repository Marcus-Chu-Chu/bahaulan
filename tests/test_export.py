import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from pipeline.dbt_runner import run_dbt
from pipeline.export import DASHBOARD_COLUMNS, export_all, write_hyper
from pipeline.load import load_all
from pipeline.quality import GateResult

FIX = Path(__file__).parent / "fixtures" / "raw"


def test_write_hyper_roundtrip(tmp_path):
    from tableauhyperapi import Connection, HyperProcess, Telemetry

    df = pd.DataFrame(
        {"date": [date(2026, 9, 5)], "pcode": ["PH1"], "rain_mm": [1.5], "population": [10]}
    )
    out = tmp_path / "t.hyper"
    write_hyper(df, out, table_name="t")
    with (
        HyperProcess(
            telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            parameters={"log_dir": str(tmp_path)},
        ) as hp,
        Connection(hp.endpoint, str(out)) as c,
    ):
        assert c.execute_scalar_query('select count(*) from "t"') == 1


def test_write_hyper_types_and_nulls(tmp_path):
    from tableauhyperapi import Connection, HyperProcess, TableName, Telemetry

    df = pd.DataFrame(
        {
            "date": pd.to_datetime([date(2026, 9, 5), None]),
            "flag": pd.Series([True, None], dtype=object),
            "count": [1, 2],
            "amount": [1.5, float("nan")],
            "label": ["a", None],
        }
    )
    out = tmp_path / "types.hyper"
    write_hyper(df, out, table_name="t")
    with (
        HyperProcess(
            telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            parameters={"log_dir": str(tmp_path)},
        ) as hp,
        Connection(hp.endpoint, str(out)) as c,
    ):
        table_def = c.catalog.get_table_definition(TableName("t"))
        types = {col.name.unescaped: str(col.type) for col in table_def.columns}
        assert types["date"] == "DATE"
        assert types["flag"] == "BOOL"
        assert types["count"] == "BIG_INT"
        assert types["amount"] == "DOUBLE"
        assert types["label"] == "TEXT"
        assert c.execute_scalar_query('select count(*) from "t" where "date" is null') == 1
        assert c.execute_scalar_query('select count(*) from "t" where "flag" is null') == 1


def test_export_all_writes_contract(tmp_path):
    from tableauhyperapi import Connection, HyperProcess, Telemetry

    cwd_log = Path.cwd() / "hyperd.log"
    if cwd_log.exists():
        cwd_log.unlink()

    db = tmp_path / "e.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    # See test_dbt_marts.test_marts_build: the fixture snapshots leave a calendar-date gap.
    run_dbt(db, exclude="assert_dashboard_full_coverage assert_dashboard_date_continuity")
    con = duckdb.connect(str(db), read_only=True)
    gates = [GateResult("freshness", True, "ok"), GateResult("coverage", False, "missing")]
    info = export_all(con, date(2026, 9, 4), gates, export_dir=tmp_path / "exports")
    con.close()
    csv = pd.read_csv(tmp_path / "exports" / "dashboard.csv")
    assert list(csv.columns) == DASHBOARD_COLUMNS
    assert info["dashboard_rows"] == len(csv) > 0
    assert csv["date"].str.match(r"\d{4}-\d{2}-\d{2}$").all()
    meta = json.loads((tmp_path / "exports" / "metadata.json").read_text())
    assert meta["run_date"] == "2026-09-04" and meta["gates"] == {
        "freshness": "pass",
        "coverage": "fail",
    }
    for name in [
        "dashboard.parquet",
        "dashboard.hyper",
        "warnings.csv",
        "river.csv",
        "monthly_normal.csv",
    ]:
        assert (tmp_path / "exports" / name).exists()

    warnings_csv = pd.read_csv(tmp_path / "exports" / "warnings.csv")
    assert warnings_csv["ts"].str.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$").all()

    monthly_normal = pd.read_csv(tmp_path / "exports" / "monthly_normal.csv")
    assert set(monthly_normal["is_complete"].unique()) <= {True, False}

    with (
        HyperProcess(
            telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
            parameters={"log_dir": str(tmp_path)},
        ) as hp,
        Connection(hp.endpoint, str(tmp_path / "exports" / "dashboard.hyper")) as c,
    ):
        hyper_count = c.execute_scalar_query('select count(*) from "dashboard"')
    assert hyper_count == len(csv)

    assert info["files"] == sorted(
        [
            "dashboard.csv",
            "dashboard.parquet",
            "dashboard.hyper",
            "warnings.csv",
            "river.csv",
            "monthly_normal.csv",
            "metadata.json",
        ]
    )

    assert not cwd_log.exists()
    # hyperd.log is a Hyper debugging artifact, not part of the export contract.
    assert not (tmp_path / "exports" / "hyperd.log").exists()


def test_export_all_is_atomic(tmp_path, monkeypatch):
    db = tmp_path / "e2.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    run_dbt(db, exclude="assert_dashboard_full_coverage assert_dashboard_date_continuity")
    con = duckdb.connect(str(db), read_only=True)
    gates = [GateResult("freshness", True, "ok")]

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("pipeline.export.write_hyper", boom)
    export_dir = tmp_path / "exports"
    try:
        with pytest.raises(RuntimeError):
            export_all(con, date(2026, 9, 4), gates, export_dir=export_dir)
    finally:
        con.close()
    assert not export_dir.exists() or not any(export_dir.iterdir())
    assert not (tmp_path / "exports.tmp").exists()

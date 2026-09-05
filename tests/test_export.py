import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

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
        HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp,
        Connection(hp.endpoint, str(out)) as c,
    ):
        assert c.execute_scalar_query('select count(*) from "t"') == 1


def test_export_all_writes_contract(tmp_path):
    db = tmp_path / "e.duckdb"
    load_all(raw_dir=FIX, db_path=db)
    run_dbt(db, exclude="assert_dashboard_full_coverage")
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

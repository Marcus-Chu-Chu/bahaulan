"""Thin wrapper around dbt's programmatic runner."""

from __future__ import annotations

import os
from pathlib import Path

from pipeline import config


def run_dbt(
    db_path: Path = config.DB_PATH,
    select: str | None = None,
    command: str = "build",
    exclude: str | None = None,
) -> None:
    from dbt.adapters.factory import cleanup_connections
    from dbt.cli.main import dbtRunner

    os.environ["BAHAULAN_DB"] = str(db_path)
    args = [command, "--project-dir", str(config.DBT_DIR), "--profiles-dir", str(config.DBT_DIR), "--no-use-colors"]
    if select:
        args += ["--select", select]
    if exclude:
        args += ["--exclude", exclude]
    try:
        result = dbtRunner().invoke(args)
    finally:
        # dbt-duckdb keeps its connection open across invocations within the
        # same process; release it so callers can immediately reopen the
        # database file (e.g. read-only) without hitting a lock conflict.
        cleanup_connections()
    if not result.success:
        raise RuntimeError(f"dbt {command} failed: {result.exception}")

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

    prior_db = os.environ.get("BAHAULAN_DB")
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
        if prior_db is None:
            os.environ.pop("BAHAULAN_DB", None)
        else:
            os.environ["BAHAULAN_DB"] = prior_db
    if not result.success:
        if result.exception is not None:
            raise RuntimeError(f"dbt {command} failed: {result.exception}")
        failures = _failing_nodes(result.result)
        if failures:
            raise RuntimeError(f"dbt {command} failed: {', '.join(failures)}")
        raise RuntimeError(f"dbt {command} failed with no exception or failing nodes reported")


def _failing_nodes(run_result: object) -> list[str]:
    """Best-effort extraction of failed/errored node names from a dbtRunnerResult.result.

    Returns an empty list (never raises) if the shape doesn't match what we expect,
    so callers still get a generic RuntimeError instead of a confusing traceback.
    """
    try:
        node_results = run_result.results
    except AttributeError:
        return []
    failures = []
    for node_result in node_results:
        try:
            status = node_result.status
            status_str = getattr(status, "value", str(status))
            if status_str in ("success", "pass", "skipped", "no-op", "reused"):
                continue
            name = node_result.node.name
        except AttributeError:
            continue
        failures.append(f"{name} ({status_str})")
    return failures

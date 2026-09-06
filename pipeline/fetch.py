"""Open-Meteo clients and raw snapshot writers."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

from pipeline import config
from pipeline.grid import GridPoint


class FetchError(RuntimeError):
    """Raised when Open-Meteo cannot be read after retries or returns a bad shape."""


def _retry_after(resp: object) -> float:
    """Seconds to wait after a 429, from the Retry-After header when it is usable.

    Open-Meteo's free tier answers an over-quota caller with 429 and often a Retry-After
    header. Backing off 1 or 2 seconds there just burns another attempt, so honour the
    header when it parses as a positive number of seconds, capped so one bad header cannot
    stall a scheduled run, and fall back to a flat minute otherwise.
    """
    raw = getattr(resp, "headers", {}) or {}
    value = raw.get("Retry-After")
    try:
        seconds = int(str(value).strip())
    except (TypeError, ValueError):
        return config.RATE_LIMIT_SLEEP
    if seconds <= 0:
        return config.RATE_LIMIT_SLEEP
    return min(seconds, 120)


def _get(url: str, params: dict) -> list | dict:
    last = "no attempt"
    for attempt in range(config.HTTP_RETRIES):
        pause = 2**attempt
        try:
            resp = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                pause = _retry_after(resp)
            last = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.RequestException as exc:
            last = repr(exc)
        if attempt < config.HTTP_RETRIES - 1:
            time.sleep(pause)
    raise FetchError(f"{url} failed after {config.HTTP_RETRIES} attempts: {last}")


def _chunks(seq: list, n: int) -> list[list]:
    return [seq[i : i + n] for i in range(0, len(seq), n)]


def _multi(url: str, points: list[GridPoint], params: dict) -> list[tuple[GridPoint, dict]]:
    out: list[tuple[GridPoint, dict]] = []
    for chunk in _chunks(points, config.MAX_POINTS_PER_REQUEST):
        p = dict(params)
        p["latitude"] = ",".join(str(pt.lat) for pt in chunk)
        p["longitude"] = ",".join(str(pt.lon) for pt in chunk)
        data = _get(url, p)
        if isinstance(data, dict):
            data = [data]
        if len(data) != len(chunk):
            raise FetchError(f"{url}: expected {len(chunk)} locations, got {len(data)}")
        out.extend(zip(chunk, data, strict=True))
    return out


def forecast_params() -> dict:
    return {
        "hourly": "precipitation",
        "daily": "precipitation_sum,precipitation_probability_max,precipitation_hours",
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "timezone": config.TIMEZONE,
    }


def flood_params() -> dict:
    return {
        "daily": "river_discharge,river_discharge_max",
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
    }


def archive_params(start: date, end: date) -> dict:
    return {
        "daily": "precipitation_sum,precipitation_hours",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": config.TIMEZONE,
    }


def _wrap(kind: str, run_date: date, pairs: list[tuple[GridPoint, dict]]) -> dict:
    return {
        "kind": kind,
        "run_date": run_date.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(),
        "points": [
            {"grid_id": pt.grid_id, "lat": pt.lat, "lon": pt.lon, "response": resp}
            for pt, resp in pairs
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def fetch_daily(run_date: date, points: list[GridPoint], raw_dir: Path = config.RAW_DIR) -> Path:
    out = raw_dir / run_date.isoformat()
    forecast_pairs = _multi(config.FORECAST_URL, points, forecast_params())
    _write_json(out / "forecast.json", _wrap("forecast", run_date, forecast_pairs))
    flood_pairs = _multi(config.FLOOD_URL, points, flood_params())
    _write_json(out / "flood.json", _wrap("flood", run_date, flood_pairs))
    return out


def archive_last_date(archive_dir: Path = config.ARCHIVE_DIR) -> date | None:
    if not archive_dir.exists():
        return None
    ends = []
    for f in archive_dir.glob("*_*.json"):
        try:
            ends.append(date.fromisoformat(f.stem.split("_")[1]))
        except ValueError:
            continue
    return max(ends) if ends else None


def year_ranges(start: date, end: date) -> list[tuple[date, date]]:
    ranges = []
    cur = start
    while cur <= end:
        year_end = date(cur.year, 12, 31)
        stop = min(year_end, end)
        ranges.append((cur, stop))
        cur = stop + timedelta(days=1)
    return ranges


def fetch_archive_if_needed(
    run_date: date, points: list[GridPoint], archive_dir: Path = config.ARCHIVE_DIR
) -> list[Path]:
    """Fetch the archive days not on disk yet, plus a trailing re-fetch window.

    ERA5 publishes some grid-days as null and fills them in a few days later, so a pure
    "start where the last file ended" backfill would freeze those holes in place forever.
    Every run therefore re-asks for the last ``config.ARCHIVE_REFETCH_DAYS`` days as well.
    Overlapping windows are safe: ``stg_archive_daily`` drops null rows first, then keeps
    the latest ``fetched_at`` per grid-day, so a later real value replaces an earlier null.
    """
    target_end = run_date - timedelta(days=config.ARCHIVE_LAG_DAYS)
    last = archive_last_date(archive_dir)
    if last is None:
        start = date.fromisoformat(config.ARCHIVE_START)
    else:
        start = min(last + timedelta(days=1), target_end - timedelta(days=config.ARCHIVE_REFETCH_DAYS))
    if start > target_end:
        return []
    written = []
    for s, e in year_ranges(start, target_end):
        pairs = _multi(config.ARCHIVE_URL, points, archive_params(s, e))
        path = archive_dir / f"{s.isoformat()}_{e.isoformat()}.json"
        _write_json(path, _wrap("archive", run_date, pairs))
        written.append(path)
    return written

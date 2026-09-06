import json
from datetime import date

import pytest
import requests

from pipeline import config, fetch
from pipeline.grid import GridPoint

P = [GridPoint("g0000", 14.35, 120.9), GridPoint("g0001", 14.35, 120.95)]


def _fake_response(n):
    return [
        {
            "latitude": 14.35,
            "longitude": 120.9,
            "daily": {"time": ["2026-09-05"], "precipitation_sum": [1.0]},
        }
        for _ in range(n)
    ]


def test_fetch_daily_writes_two_snapshots(tmp_path, monkeypatch):
    calls = []

    def fake_get(url, params):
        calls.append((url, params))
        return _fake_response(len(params["latitude"].split(",")))

    monkeypatch.setattr(fetch, "_get", fake_get)
    out = fetch.fetch_daily(date(2026, 9, 5), P, raw_dir=tmp_path)
    assert out == tmp_path / "2026-09-05"
    snap = json.loads((out / "forecast.json").read_text())
    assert snap["kind"] == "forecast" and snap["run_date"] == "2026-09-05"
    assert [p["grid_id"] for p in snap["points"]] == ["g0000", "g0001"]
    assert snap["points"][0]["response"]["daily"]["precipitation_sum"] == [1.0]
    assert (out / "flood.json").exists()
    assert calls[0][1]["latitude"] == "14.35,14.35"
    assert calls[0][1]["timezone"] == "Asia/Manila"


def test_get_retries_then_raises(monkeypatch):
    calls = []
    sleeps = []

    def fake_get(url, params, timeout=None):
        calls.append((url, params))
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(fetch.FetchError):
        fetch._get("http://x", {})

    assert len(calls) == config.HTTP_RETRIES
    assert sleeps == [1, 2]


def test_get_honours_retry_after_on_429(monkeypatch):
    sleeps = []
    responses = []

    class TooMany:
        status_code = 429
        text = "rate limited"
        headers = {"Retry-After": "5"}

    class Ok:
        status_code = 200
        text = "{}"
        headers = {}

        def json(self):
            return {"ok": True}

    queue = [TooMany(), TooMany(), Ok()]

    def fake_get(url, params, timeout=None):
        resp = queue.pop(0)
        responses.append(resp)
        return resp

    monkeypatch.setattr(fetch.requests, "get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: sleeps.append(s))

    assert fetch._get("http://x", {}) == {"ok": True}
    assert sleeps == [5, 5]
    assert len(responses) == 3


def test_get_falls_back_to_rate_limit_sleep_without_retry_after(monkeypatch):
    sleeps = []

    class TooMany:
        status_code = 429
        text = "rate limited"
        headers = {}

    monkeypatch.setattr(fetch.requests, "get", lambda url, params, timeout=None: TooMany())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: sleeps.append(s))

    with pytest.raises(fetch.FetchError, match="HTTP 429"):
        fetch._get("http://x", {})

    assert sleeps == [config.RATE_LIMIT_SLEEP] * (config.HTTP_RETRIES - 1)


def test_get_raises_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "boom"
        headers = {}

    monkeypatch.setattr(fetch.requests, "get", lambda url, params, timeout=None: FakeResponse())
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)

    with pytest.raises(fetch.FetchError, match="HTTP 500"):
        fetch._get("http://x", {})


def test_multi_raises_on_count_mismatch(monkeypatch):
    monkeypatch.setattr(fetch, "_get", lambda url, params: _fake_response(1))
    with pytest.raises(fetch.FetchError):
        fetch._multi("http://x", P, {})


def test_year_ranges_split_on_calendar_years():
    r = fetch.year_ranges(date(2024, 11, 1), date(2026, 2, 3))
    assert r == [
        (date(2024, 11, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 2, 3)),
    ]


def test_archive_last_date_and_gap_logic(tmp_path, monkeypatch):
    assert fetch.archive_last_date(tmp_path) is None
    (tmp_path / "2020-01-01_2020-12-31.json").write_text("{}")
    (tmp_path / "2021-01-01_2021-06-30.json").write_text("{}")
    assert fetch.archive_last_date(tmp_path) == date(2021, 6, 30)

    monkeypatch.setattr(fetch, "_get", lambda url, params: _fake_response(len(P)))
    # target_end is run_date minus the 5-day ERA5 lag. The window always reaches back
    # ARCHIVE_REFETCH_DAYS before target_end, even when the gap alone is shorter or empty,
    # so null ERA5 cells published earlier get re-asked and overwritten.
    written = fetch.fetch_archive_if_needed(date(2021, 7, 3), P, archive_dir=tmp_path)
    assert written == [tmp_path / "2021-06-14_2021-06-28.json"]
    written = fetch.fetch_archive_if_needed(date(2021, 7, 10), P, archive_dir=tmp_path)
    assert written == [tmp_path / "2021-06-21_2021-07-05.json"]
    # archive_last_date still reports the max END across files, not the max start.
    assert fetch.archive_last_date(tmp_path) == date(2021, 7, 5)


def test_fetch_archive_returns_empty_before_the_archive_start(tmp_path, monkeypatch):
    # No snapshots yet, and the target end sits before ARCHIVE_START, so there is nothing
    # to ask for. With a previous archive on disk the trailing re-fetch always yields a
    # window, so this is the only path that returns nothing.
    monkeypatch.setattr(fetch, "_get", lambda url, params: _fake_response(len(P)))
    assert fetch.fetch_archive_if_needed(date(2019, 12, 1), P, archive_dir=tmp_path) == []

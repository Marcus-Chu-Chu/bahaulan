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


def test_get_raises_on_non_200(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "boom"

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
    written = fetch.fetch_archive_if_needed(date(2021, 7, 3), P, archive_dir=tmp_path)
    assert written == []  # 2021-07-03 minus lag (5) = 06-28, already covered
    written = fetch.fetch_archive_if_needed(date(2021, 7, 10), P, archive_dir=tmp_path)
    assert written == [tmp_path / "2021-07-01_2021-07-05.json"]

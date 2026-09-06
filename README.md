# BahaUlan

BahaUlan pulls Metro Manila rainfall and river discharge from Open-Meteo every morning,
models it with dbt on DuckDB, and publishes a barangay-level extract for Tableau and Power BI.
Each row joins the weather at the nearest grid point to the flood-exposure score that
[BahaMap](https://github.com/Marcus-Chu-Chu/bahamap) computed for that barangay, so you can
ask which places are getting rain and are already exposed to flooding. "Baha" is Filipino for
flood, "ulan" for rain.

[![CI](https://github.com/Marcus-Chu-Chu/bahaulan/actions/workflows/ci.yml/badge.svg)](https://github.com/Marcus-Chu-Chu/bahaulan/actions/workflows/ci.yml)
[![Daily pipeline](https://github.com/Marcus-Chu-Chu/bahaulan/actions/workflows/pipeline.yml/badge.svg)](https://github.com/Marcus-Chu-Chu/bahaulan/actions/workflows/pipeline.yml)
[![Latest extracts](https://img.shields.io/badge/release-latest%20extracts-blue)](https://github.com/Marcus-Chu-Chu/bahaulan/releases/tag/latest)

## Dashboard

The workbook is not published yet. The Tableau Public link and screenshots go here once it is.

Four views are planned, one per export file:

1. A barangay map of `wet_exposure`, with a date slider across the 30 observed days and the
   7 forecast days.
2. This year's monthly rainfall against the 2020 to 2025 normal, with the 10th to 90th
   percentile band behind it.
3. The forecast week hour by hour, colored by PAGASA-style warning band.
4. River discharge per grid point, past days and forecast days on one line.

The data behind them is `exports/dashboard.csv` in this repo, plus `dashboard.hyper` on the
[latest release](https://github.com/Marcus-Chu-Chu/bahaulan/releases/tag/latest) for Tableau.
Power BI Desktop reads the CSV straight from the repo.

## What it does

- Ingests three Open-Meteo endpoints for 31 grid points on a 0.05 degree lattice over the
  National Capital Region: the forecast API for daily and hourly rainfall, the flood API for
  GloFAS river discharge, and the historical API for an ERA5 backfill from 2020-01-01.
- Models the raw JSON into 13 dbt models over DuckDB and joins it to a seed of 1,710
  barangays across 17 cities and municipalities, carrying population, exposure score and the
  nearest grid point.
- Tests every run: 4 quality gates on the raw tables before dbt starts, then 30 dbt tests
  including two singular tests that check the dashboard covers every barangay and has no
  gaps in its date range.
- Publishes `exports/dashboard.csv` at 63,270 rows, which is 1,710 barangays over 37
  continuous days, alongside Parquet, Hyper and a `metadata.json` describing the run.

## Architecture

```mermaid
flowchart TD
    A["Open-Meteo<br/>forecast API, flood API, archive API"] --> B["fetch<br/>raw JSON snapshots on disk"]
    B --> C["load<br/>DuckDB raw schema"]
    C --> D["quality gates<br/>freshness, coverage, null_share, ranges"]
    D --> E["dbt build<br/>staging, intermediate, marts, 30 tests"]
    E --> F["export<br/>dashboard.csv, .parquet, .hyper, metadata.json"]
    F --> G["GitHub commit and 'latest' release"]
    G --> H["Tableau Public / Power BI Desktop"]
```

`docs/architecture.md` covers each stage, what happens when one fails, and the model lineage.
`docs/data-dictionary.md` lists every column in every export file.

## Quickstart

The raw JSON snapshots are committed, so you can rebuild every export without a network call
or an API key.

Windows, PowerShell:

```powershell
git clone https://github.com/Marcus-Chu-Chu/bahaulan.git
cd bahaulan
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pipeline.run --offline
```

macOS and Linux:

```bash
git clone https://github.com/Marcus-Chu-Chu/bahaulan.git
cd bahaulan
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pipeline.run --offline
```

`--offline` rebuilds the DuckDB file, the marts and everything in `exports/` from the
snapshots in `data/raw/`. Drop the flag to fetch today's data from Open-Meteo instead:

```bash
python -m pipeline.run
```

The run prints a summary table and appends one row to `logs/runs.csv` with a status of `ok`,
`fetch_failed`, `gate_failed`, `dbt_failed` or `error`. It exits 1 on anything but `ok`.

For the tests, install `requirements-dev.txt` and run `ruff check .` and `pytest -q`.

## Data notes

Rainfall and discharge are model output, not gauge readings. There is no PAGASA station feed
here. Forecasts come from Open-Meteo's roughly 11 km models, past rainfall from the ERA5
reanalysis at roughly 9 to 11 km, and river discharge from GloFAS at roughly 5 km. Every
value is an area average for a grid cell, so two barangays that share a grid point get
identical weather.

ERA5 trails real time by about 5 days. The forecast request asks for 7 past days to cover
that gap, which is why the dashboard has no hole between the last archived day and the first
forecast day. Rows sourced from the archive are marked `observed`; the rest are `forecast`,
including the recent past days.

Warning levels apply the PAGASA rainfall bands (yellow at 7.5 mm/h, orange at 15, red at 30)
to modelled hourly precipitation. They are not PAGASA warnings and carry none of their
authority. The flood API reports in GMT days while the forecast and archive are queried in
Asia/Manila, so `river.csv` dates can sit up to 8 hours off the rainfall dates.

The exposure score, hazard-area share and exposed population come from BahaMap, built from
NOAH hazard maps, PSGC boundaries and the 2020 census.

Attribution: Open-Meteo forecast and historical data under CC BY 4.0; ERA5 and GloFAS from
Copernicus, the Climate Change Service and the Emergency Management Service.

The pipeline runs at 22:00 UTC daily, which is 06:00 in Manila. It commits new snapshots,
exports and log rows back to `main` and refreshes the `latest` release. Power BI Desktop
picks up new data when you refresh it against the repo CSV. Tableau Public does not refresh
on its own, so the published workbook only moves when it is republished by hand.

## Repository layout

```
pipeline/       fetch, load, quality gates, dbt runner, export, run orchestrator
dbt/            models (staging, intermediate, marts), seeds, tests, profiles
data/raw/       committed JSON snapshots: daily runs and yearly archive windows
exports/        dashboard.csv, warnings.csv, river.csv, monthly_normal.csv, metadata.json
docs/           architecture and data dictionary
logs/runs.csv   one row per run: status, row counts, gate results
tests/          pytest suite with offline fixtures
```

`data/bahaulan.duckdb`, `exports/dashboard.hyper` and `exports/dashboard.parquet` are
gitignored. The database is rebuilt on every run, and the two binary extracts are attached to
the `latest` release.

## Related projects

[BahaMap](https://github.com/Marcus-Chu-Chu/bahamap) is a barangay-level flood exposure atlas
of Metro Manila.
[BahaTanong](https://github.com/Marcus-Chu-Chu/bahatanong) is a bilingual question-answering
agent over the BahaMap data.

Built with AI-assisted tooling (Claude Code); data decisions and the published numbers were reviewed by hand.

## License

MIT. See `LICENSE`.

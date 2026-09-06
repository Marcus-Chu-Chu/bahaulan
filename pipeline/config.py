"""Project-wide constants. Everything tunable lives here."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
ARCHIVE_DIR = RAW_DIR / "archive"
DB_PATH = DATA_DIR / "bahaulan.duckdb"
EXPORT_DIR = ROOT / "exports"
LOG_PATH = ROOT / "logs" / "runs.csv"
DBT_DIR = ROOT / "dbt"
SEED_PATH = DBT_DIR / "seeds" / "dim_barangay.csv"

# Spatial grid over the National Capital Region bounding box.
LAT_MIN, LAT_MAX = 14.35, 14.80
LON_MIN, LON_MAX = 120.90, 121.15
GRID_STEP = 0.05
TIMEZONE = "Asia/Manila"

# Open-Meteo (free, keyless).
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FLOOD_URL = "https://flood-api.open-meteo.com/v1/flood"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_DAYS = 7
# The archive (ERA5 reanalysis) endpoint trails real time by ARCHIVE_LAG_DAYS, so the most
# recent few observed days aren't backfillable from there yet. The forecast/flood snapshot's
# own past_days window has to reach back far enough to bridge that gap by itself, or the
# dashboard span ends up with a hole between "last archived day" and "first forecast day".
# Open-Meteo accepts past_days up to 92, so 7 (> ARCHIVE_LAG_DAYS) keeps every run
# self-sufficient without depending on same-day archive availability.
PAST_DAYS = 7
ARCHIVE_START = "2020-01-01"
ARCHIVE_LAG_DAYS = 5  # ERA5 reanalysis trails real time; don't ask for the last few days
# Always re-fetch this trailing window of archive days on every run. ERA5 cells can land null
# on first publication and fill in a few days later, so a one-shot backfill leaves holes.
# Overlapping windows are safe because stg_archive_daily drops nulls before keeping the latest
# fetched_at per grid-day, so a later non-null value wins over an earlier null.
ARCHIVE_REFETCH_DAYS = 14
# 31 active points fit in one request, which halves the request count against the old 30.
MAX_POINTS_PER_REQUEST = 50
HTTP_TIMEOUT = 60
HTTP_RETRIES = 3
RATE_LIMIT_SLEEP = 60  # fallback pause after an HTTP 429 with no usable Retry-After header

# PAGASA-style hourly rainfall warning bands, mm/h, checked top-down.
WARNING_BANDS = ((30.0, "red"), (15.0, "orange"), (7.5, "yellow"))

# Quality gates.
MAX_DAILY_MM = 500.0
MAX_NULL_SHARE = 0.05
MIN_FORECAST_HORIZON_DAYS = 6

# Only the newest run directories are loaded for forecast_hourly and flood_daily.
HOURLY_RUN_DIRS = 14

# Dashboard window: observed days kept before run_date.
DASHBOARD_LOOKBACK_DAYS = 30
NORMAL_YEARS = (2020, 2025)

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
PAST_DAYS = 1
ARCHIVE_START = "2020-01-01"
ARCHIVE_LAG_DAYS = 5  # ERA5 reanalysis trails real time; don't ask for the last few days
MAX_POINTS_PER_REQUEST = 30
HTTP_TIMEOUT = 60
HTTP_RETRIES = 3

# PAGASA-style hourly rainfall warning bands, mm/h, checked top-down.
WARNING_BANDS = ((30.0, "red"), (15.0, "orange"), (7.5, "yellow"))

# Quality gates.
MAX_DAILY_MM = 500.0
MAX_NULL_SHARE = 0.05
MIN_FORECAST_HORIZON_DAYS = 6

# Dashboard window: observed days kept before run_date.
DASHBOARD_LOOKBACK_DAYS = 30
NORMAL_YEARS = (2020, 2025)

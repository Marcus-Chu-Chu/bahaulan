# Data dictionary

Every file below is written by `pipeline/export.py` from the dbt marts. Column definitions
come from the mart SQL in `dbt/models/marts/`.

Two things apply to every rainfall and discharge column. The values are model output, not
gauge readings: forecasts come from Open-Meteo's roughly 11 km forecast models, past rainfall
comes from the ERA5 reanalysis at roughly 9 to 11 km, and river discharge comes from GloFAS at
roughly 5 km. Each value is the model's area average for a grid cell, assigned to a barangay
by nearest grid-point centroid, so two barangays sharing a grid point carry identical weather.

## dashboard.csv

One row per barangay per day, 1,710 barangays over a 37-day window (30 observed days before
the run date plus a 7-day forecast). `dashboard.parquet` and `dashboard.hyper` hold the same
rows and columns; the Hyper file has a single table named `dashboard`.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `date` | date | Manila day | The day the weather values describe. |
| `source` | text | | `observed` if the value came from the ERA5 archive, `forecast` if it came from a forecast run. ERA5 trails real time by about 5 days, so the most recent past days are labelled `forecast` even though they are behind the run date. |
| `pcode` | text | | PSGC barangay code, the primary key of `dim_barangay`. |
| `name` | text | | Barangay name as published in the PSGC. |
| `city` | text | | City or municipality, one of the 17 in the National Capital Region. |
| `population` | bigint | people | 2020 census population of the barangay. |
| `score` | double | 0 to 100 | BahaMap flood-exposure score. Higher means more of the barangay's people live in a flood-prone area. |
| `pct_area_mh_25` | double | 0 to 1 | Share of the barangay's land area inside the NOAH 25-year medium-or-high flood hazard zone. |
| `est_pop_exposed_25` | bigint | people | Population estimated to live inside that 25-year hazard zone. |
| `grid_id` | text | | Id of the nearest Open-Meteo grid point, on a 0.05 degree lattice over the NCR bounding box. |
| `rain_mm` | double | mm | Total rainfall for the day at that grid point. |
| `rain_prob_max` | double | percent | Highest hourly precipitation probability the forecast gives for the day. Null for observed days, which have no probability. |
| `rain_hours` | double | hours | Hours in the day with measurable precipitation. |
| `rain_3d_mm` | double | mm | Rainfall summed over this day and the two before it. |
| `rain_7d_mm` | double | mm | Rainfall summed over this day and the six before it. |
| `wet_exposure` | double | mm | `rain_3d_mm * score / 100`, rounded to 3 decimals. A barangay scores high only when recent rain and flood exposure are both high. |
| `max_hourly_mm` | double | mm/h | Highest hourly rainfall the forecast gives for the day at that grid point. Null for days outside the current forecast run's hourly window. |
| `warning_level` | text | | The PAGASA-style band that `max_hourly_mm` falls into: `red` at 30 mm/h and above, `orange` at 15, `yellow` at 7.5, otherwise `none`. `none` also covers days with no hourly data. |
| `run_date` | date | Manila day | The date of the pipeline run that produced the file. |
| `lat` | double | degrees | Barangay centroid latitude, WGS 84. |
| `lon` | double | degrees | Barangay centroid longitude, WGS 84. |

## warnings.csv

Every forecast hour from the current run, one row per grid point per hour.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `run_date` | date | Manila day | Run that produced the forecast. |
| `grid_id` | text | | Grid point. |
| `ts` | timestamp | Manila local time | Start of the hour. |
| `date` | date | Manila day | `ts` truncated to the day, for joining to daily tables. |
| `mm_per_hour` | double | mm/h | Forecast precipitation in that hour. |
| `warning_level` | text | | Band for `mm_per_hour`: `red` at 30 and above, `orange` at 15, `yellow` at 7.5, otherwise `none`. |

## river.csv

GloFAS river discharge, kept at grid grain because a discharge cell covers a river reach
rather than a barangay.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `run_date` | date | Manila day | Run that produced the values. |
| `grid_id` | text | | Grid point. |
| `date` | date | GMT day | The day the discharge describes. The flood API reports in GMT days while the forecast and archive endpoints are queried in Asia/Manila, so this column can sit up to 8 hours off the rainfall dates. |
| `source` | text | | `past` when `date` is before `run_date`, `forecast` otherwise. |
| `river_discharge` | double | m3/s | Daily mean discharge in the cell. |
| `river_discharge_max` | double | m3/s | Daily maximum discharge in the cell. |
| `cities_served` | text | | Comma-separated list of the cities whose barangays use this grid point. |

## monthly_normal.csv

Monthly NCR-average rainfall from the ERA5 archive, with the 2020 to 2025 normal for each
calendar month. One row per year and month present in the archive.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `year` | bigint | | Calendar year. |
| `month` | bigint | 1 to 12 | Calendar month. |
| `month_start` | date | | First day of the month, for charting on a time axis. |
| `total_mm` | double | mm | Sum over the month of the daily rainfall averaged across all grid points. |
| `normal_mm` | double | mm | Mean `total_mm` for this calendar month across 2020 to 2025. |
| `p10_mm` | double | mm | 10th percentile of `total_mm` for this calendar month over the same years. |
| `p90_mm` | double | mm | 90th percentile of `total_mm` for this calendar month over the same years. |
| `is_current_year` | boolean | | True when `year` is the latest year in the archive. |
| `days_covered` | bigint | days | Distinct days of the month present in the archive. |
| `is_complete` | boolean | | True when `days_covered` equals the calendar length of the month. The current month is partial until ERA5 catches up, so filter on this before comparing `total_mm` to `normal_mm`. |

## metadata.json

One object describing the run that wrote the exports.

| Key | Type | Definition |
|---|---|---|
| `run_date` | string | Run date in Asia/Manila, ISO format. |
| `generated_at_utc` | string | When the export was written, UTC, to the second. |
| `dashboard_rows` | integer | Row count of `dashboard.csv`. |
| `latest_observed_date` | string | Newest day in the dashboard with `source = 'observed'`. |
| `forecast_through` | string | Newest day in the dashboard. |
| `active_grid_points` | integer | Grid points with at least one barangay assigned to them. |
| `gates` | object | One `pass` or `fail` per quality gate: `freshness`, `coverage`, `null_share`, `ranges`. |
| `sources` | array | Upstream data sources and their attribution. |
| `note` | string | The model-versus-gauge caveat, repeated so it travels with the extract. |

## Attribution

Open-Meteo forecast and historical data are published under CC BY 4.0. ERA5 and GloFAS are
Copernicus products, from the Climate Change Service and the Emergency Management Service.
The exposure score, hazard shares and population come from
[BahaMap](https://github.com/Marcus-Chu-Chu/bahamap), which built them from NOAH hazard maps,
PSGC boundaries and the 2020 census.

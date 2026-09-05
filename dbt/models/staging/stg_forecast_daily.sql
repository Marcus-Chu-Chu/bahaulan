select
    run_date,
    grid_id,
    date,
    precipitation_sum,
    precipitation_probability_max,
    precipitation_hours,
    fetched_at,
    run_date || '|' || grid_id || '|' || date as row_key
from {{ source('raw', 'forecast_daily') }}

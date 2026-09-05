select
    run_date,
    grid_id,
    ts,
    precipitation,
    fetched_at,
    run_date || '|' || grid_id || '|' || ts as row_key
from {{ source('raw', 'forecast_hourly') }}

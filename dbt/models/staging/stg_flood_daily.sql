select
    run_date,
    grid_id,
    date,
    river_discharge,
    river_discharge_max,
    fetched_at,
    run_date || '|' || grid_id || '|' || date as row_key
from {{ source('raw', 'flood_daily') }}

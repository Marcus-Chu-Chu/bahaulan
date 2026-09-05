select
    h.run_date, h.grid_id, h.ts, cast(h.ts as date) as date, h.precipitation as mm_per_hour,
    case
        when h.precipitation >= 30 then 'red'
        when h.precipitation >= 15 then 'orange'
        when h.precipitation >= 7.5 then 'yellow'
        else 'none'
    end as warning_level
from {{ ref('stg_forecast_hourly') }} h
join {{ ref('int_latest_run') }} l on l.run_date = h.run_date
where h.precipitation is not null

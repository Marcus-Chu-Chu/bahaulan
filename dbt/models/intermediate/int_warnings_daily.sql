select
    grid_id, date,
    max(mm_per_hour) as max_hourly_mm,
    case max(case warning_level when 'red' then 3 when 'orange' then 2 when 'yellow' then 1 else 0 end)
        when 3 then 'red' when 2 then 'orange' when 1 then 'yellow' else 'none' end as warning_level
from {{ ref('fct_warnings_hourly') }}
group by grid_id, date

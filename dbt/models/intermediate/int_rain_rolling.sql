select
    grid_id, date, source, rain_mm, rain_hours, rain_prob_max,
    sum(rain_mm) over (partition by grid_id order by date range between interval 2 day preceding and current row) as rain_3d_mm,
    sum(rain_mm) over (partition by grid_id order by date range between interval 6 day preceding and current row) as rain_7d_mm
from {{ ref('int_rain_daily_unioned') }}

-- The forecast/observed union can leave a calendar-day hole between the last archived day
-- and the first forecast day if the forecast snapshot's past_days window doesn't reach back
-- far enough (see PAST_DAYS in pipeline/config.py). Fail if any date between the dashboard's
-- earliest and latest date is missing entirely.
with bounds as (
    select min(date) as min_date, max(date) as max_date
    from {{ ref('mart_dashboard') }}
),
calendar as (
    select unnest(generate_series(min_date, max_date, interval 1 day))::date as date
    from bounds
),
present as (
    select distinct date from {{ ref('mart_dashboard') }}
)
select c.date
from calendar c
left join present p on p.date = c.date
where p.date is null

with ranked as (
    select
        grid_id,
        date,
        precipitation_sum,
        precipitation_hours,
        row_number() over (partition by grid_id, date order by fetched_at desc) as rn
    from {{ source('raw', 'archive_daily') }}
)
select
    grid_id,
    date,
    precipitation_sum,
    precipitation_hours,
    grid_id || '|' || date as row_key
from ranked
where rn = 1 and precipitation_sum is not null

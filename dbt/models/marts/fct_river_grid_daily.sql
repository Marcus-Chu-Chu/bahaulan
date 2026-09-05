with cities as (
    select grid_id, string_agg(distinct city, ', ' order by city) as cities_served
    from {{ ref('dim_barangay') }} group by grid_id
)
select
    d.run_date, d.grid_id, d.date,
    case when d.date < d.run_date then 'past' else 'forecast' end as source,
    d.river_discharge, d.river_discharge_max, c.cities_served
from {{ ref('stg_flood_daily') }} d
join {{ ref('int_latest_run') }} l on l.run_date = d.run_date
join cities c on c.grid_id = d.grid_id

with observed as (
    select grid_id, date, precipitation_sum as rain_mm, precipitation_hours as rain_hours,
           cast(null as double) as rain_prob_max, 'observed' as source
    from {{ ref('stg_archive_daily') }}
),
forecast_ranked as (
    select grid_id, date, precipitation_sum as rain_mm, precipitation_hours as rain_hours,
           precipitation_probability_max as rain_prob_max, 'forecast' as source,
           row_number() over (partition by grid_id, date order by run_date desc) as rn
    from {{ ref('stg_forecast_daily') }}
    where precipitation_sum is not null
),
forecast as (
    select f.grid_id, f.date, f.rain_mm, f.rain_hours, f.rain_prob_max, f.source
    from forecast_ranked f
    left join observed o on o.grid_id = f.grid_id and o.date = f.date
    where f.rn = 1 and o.grid_id is null
)
select * from observed
union all
select * from forecast

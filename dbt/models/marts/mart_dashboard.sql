select
    f.date, f.source, f.pcode, f.name, f.city, f.population, f.score, f.pct_area_mh_25, f.est_pop_exposed_25,
    f.grid_id, f.rain_mm, f.rain_prob_max, f.rain_hours, f.rain_3d_mm, f.rain_7d_mm, f.wet_exposure,
    f.max_hourly_mm, f.warning_level, l.run_date, f.lat, f.lon
from {{ ref('fct_rain_barangay_daily') }} f
cross join {{ ref('int_latest_run') }} l
where f.date >= l.run_date - interval {{ var('lookback_days', 30) }} day

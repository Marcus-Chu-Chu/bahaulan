select
    r.date, r.source, b.pcode, b.name, b.city, b.population, b.score, b.pct_area_mh_25, b.est_pop_exposed_25,
    b.grid_id, r.rain_mm, r.rain_prob_max, r.rain_hours, r.rain_3d_mm, r.rain_7d_mm,
    round(r.rain_3d_mm * b.score / 100.0, 3) as wet_exposure,
    w.max_hourly_mm, coalesce(w.warning_level, 'none') as warning_level,
    b.lat, b.lon,
    b.pcode || '|' || r.date as row_key
from {{ ref('int_rain_rolling') }} r
join {{ ref('dim_barangay') }} b on b.grid_id = r.grid_id
left join {{ ref('int_warnings_daily') }} w on w.grid_id = r.grid_id and w.date = r.date

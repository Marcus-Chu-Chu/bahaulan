-- The furthest horizon day (run_date + 6) is sourced only from the current forecast run and
-- the raw gates tolerate up to 5% null forecast values, so a single null grid-day there would
-- fail the build; require full barangay coverage only through run_date + 5.
select d.date, count(distinct d.pcode) as n
from {{ ref('mart_dashboard') }} d
cross join {{ ref('int_latest_run') }} l
where d.date <= l.run_date + interval 5 day
group by d.date
having count(distinct d.pcode) <> (select count(*) from {{ ref('dim_barangay') }})

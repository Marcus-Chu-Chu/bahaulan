with ncr_daily as (
    select date, avg(precipitation_sum) as rain_mm from {{ ref('stg_archive_daily') }} group by date
),
monthly as (
    select
        year(date) as year, month(date) as month,
        sum(rain_mm) as total_mm, count(distinct date) as days_covered
    from ncr_daily group by 1, 2
),
normal as (
    select month, avg(total_mm) as normal_mm,
           quantile_cont(total_mm, 0.1) as p10_mm, quantile_cont(total_mm, 0.9) as p90_mm
    from monthly where year between {{ var('normal_start', 2020) }} and {{ var('normal_end', 2025) }}
    group by month
),
latest as (select year(max(date)) as current_year from ncr_daily)
select m.year, m.month, make_date(m.year, m.month, 1) as month_start,
       round(m.total_mm, 2) as total_mm,
       round(n.normal_mm, 2) as normal_mm,
       round(n.p10_mm, 2) as p10_mm,
       round(n.p90_mm, 2) as p90_mm,
       m.year = latest.current_year as is_current_year,
       m.days_covered,
       m.days_covered = day(last_day(make_date(m.year, m.month, 1))) as is_complete
from monthly m
left join normal n on n.month = m.month
cross join latest

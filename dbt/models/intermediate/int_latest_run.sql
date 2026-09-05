{{ config(materialized='view') }}
select max(run_date) as run_date from {{ ref('stg_forecast_daily') }}

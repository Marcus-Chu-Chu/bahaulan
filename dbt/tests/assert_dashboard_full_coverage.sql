select date, count(distinct pcode) as n
from {{ ref('mart_dashboard') }}
group by date
having count(distinct pcode) <> (select count(*) from {{ ref('dim_barangay') }})

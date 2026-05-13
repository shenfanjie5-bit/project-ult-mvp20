{{ config(severity="error") }}

select
    ts_code,
    end_date,
    report_type,
    count(*) as latest_count
from {{ ref('mart_fact_financial_indicator') }}
where is_latest
group by ts_code, end_date, report_type
having count(*) > 1

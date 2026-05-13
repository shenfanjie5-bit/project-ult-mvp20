{{ config(severity="error") }}

select
    'mart_fact_event' as model_name,
    column_name
from (describe select * from {{ ref('mart_fact_event') }})
where lower(column_name) in ('body', 'content', 'text')

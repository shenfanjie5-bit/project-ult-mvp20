{{ config(severity="error") }}

with mart_columns as (
    select 'mart_dim_security' as model_name, column_name
    from (describe select * from {{ ref('mart_dim_security') }})

    union all

    select 'mart_dim_index' as model_name, column_name
    from (describe select * from {{ ref('mart_dim_index') }})

    union all

    select 'mart_fact_price_bar' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_price_bar') }})

    union all

    select 'mart_fact_financial_indicator' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_financial_indicator') }})

    union all

    select 'mart_fact_event' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_event') }})

    union all

    select 'mart_fact_market_daily_feature' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_market_daily_feature') }})

    union all

    select 'mart_fact_index_price_bar' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_index_price_bar') }})

    union all

    select 'mart_fact_forecast_event' as model_name, column_name
    from (describe select * from {{ ref('mart_fact_forecast_event') }})
)

select model_name, column_name
from mart_columns
where lower(column_name) in ('submitted_at', 'ingest_seq')

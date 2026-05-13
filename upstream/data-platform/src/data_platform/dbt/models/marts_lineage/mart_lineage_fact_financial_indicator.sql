{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_financial_indicator,
-- joined on (security_id, end_date, report_type). int_financial_reports_latest
-- is sourced from the Tushare fina_indicator interface (with cross-checks from
-- income/balancesheet/cashflow in the int_ join); source_run_id records each
-- contributing raw run that exists for the row.

select
    ts_code as security_id,
    end_date,
    report_type,
    cast('tushare' as varchar) as source_provider,
    concat_ws(
        '+',
        case when fina_indicator_source_run_id is not null then 'fina_indicator' end,
        case when income_source_run_id is not null then 'income' end,
        case when balancesheet_source_run_id is not null then 'balancesheet' end,
        case when cashflow_source_run_id is not null then 'cashflow' end
    ) as source_interface_id,
    concat_ws(
        '|',
        case
            when fina_indicator_source_run_id is not null
                then concat('fina_indicator=', fina_indicator_source_run_id)
        end,
        case
            when income_source_run_id is not null
                then concat('income=', income_source_run_id)
        end,
        case
            when balancesheet_source_run_id is not null
                then concat('balancesheet=', balancesheet_source_run_id)
        end,
        case
            when cashflow_source_run_id is not null
                then concat('cashflow=', cashflow_source_run_id)
        end
    ) as source_run_id,
    greatest(
        coalesce(fina_indicator_raw_loaded_at, timestamp '1970-01-01 00:00:00'),
        coalesce(income_raw_loaded_at, timestamp '1970-01-01 00:00:00'),
        coalesce(balancesheet_raw_loaded_at, timestamp '1970-01-01 00:00:00'),
        coalesce(cashflow_raw_loaded_at, timestamp '1970-01-01 00:00:00')
    ) as raw_loaded_at
from {{ ref('int_financial_reports_latest') }}
where is_latest

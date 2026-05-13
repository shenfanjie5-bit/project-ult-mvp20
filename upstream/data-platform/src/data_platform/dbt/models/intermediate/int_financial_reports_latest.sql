{{ config(materialized="table") }}

with report_groups as (
    select ts_code, end_date, report_type
    from {{ ref('stg_income') }}

    union

    select ts_code, end_date, report_type
    from {{ ref('stg_balancesheet') }}

    union

    select ts_code, end_date, report_type
    from {{ ref('stg_cashflow') }}

    union

    select ts_code, end_date, report_type
    from {{ ref('stg_fina_indicator') }}
),

income_ranked as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        basic_eps,
        diluted_eps,
        total_revenue,
        revenue,
        operate_profit,
        total_profit,
        n_income,
        n_income_attr_p,
        source_run_id,
        raw_loaded_at,
        row_number() over (
            partition by ts_code, end_date, report_type
            order by ann_date desc nulls last,
                     f_ann_date desc nulls last,
                     update_flag desc nulls last,
                     raw_loaded_at desc nulls last,
                     source_run_id desc nulls last
        ) as source_version_rank
    from {{ ref('stg_income') }}
),

income_latest as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        basic_eps,
        diluted_eps,
        total_revenue,
        revenue,
        operate_profit,
        total_profit,
        n_income,
        n_income_attr_p,
        source_run_id,
        raw_loaded_at
    from income_ranked
    where source_version_rank = 1
),

balancesheet_ranked as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        money_cap,
        total_cur_assets,
        total_assets,
        total_cur_liab,
        total_liab,
        total_hldr_eqy_exc_min_int,
        total_liab_hldr_eqy,
        source_run_id,
        raw_loaded_at,
        row_number() over (
            partition by ts_code, end_date, report_type
            order by ann_date desc nulls last,
                     f_ann_date desc nulls last,
                     update_flag desc nulls last,
                     raw_loaded_at desc nulls last,
                     source_run_id desc nulls last
        ) as source_version_rank
    from {{ ref('stg_balancesheet') }}
),

balancesheet_latest as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        money_cap,
        total_cur_assets,
        total_assets,
        total_cur_liab,
        total_liab,
        total_hldr_eqy_exc_min_int,
        total_liab_hldr_eqy,
        source_run_id,
        raw_loaded_at
    from balancesheet_ranked
    where source_version_rank = 1
),

cashflow_ranked as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        net_profit,
        n_cashflow_act,
        n_cashflow_inv_act,
        n_cash_flows_fnc_act,
        n_incr_cash_cash_equ,
        free_cashflow,
        source_run_id,
        raw_loaded_at,
        row_number() over (
            partition by ts_code, end_date, report_type
            order by ann_date desc nulls last,
                     f_ann_date desc nulls last,
                     update_flag desc nulls last,
                     raw_loaded_at desc nulls last,
                     source_run_id desc nulls last
        ) as source_version_rank
    from {{ ref('stg_cashflow') }}
),

cashflow_latest as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        net_profit,
        n_cashflow_act,
        n_cashflow_inv_act,
        n_cash_flows_fnc_act,
        n_incr_cash_cash_equ,
        free_cashflow,
        source_run_id,
        raw_loaded_at
    from cashflow_ranked
    where source_version_rank = 1
),

fina_indicator_ranked as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        eps,
        dt_eps,
        grossprofit_margin,
        netprofit_margin,
        roe,
        roa,
        debt_to_assets,
        or_yoy,
        netprofit_yoy,
        source_run_id,
        raw_loaded_at,
        row_number() over (
            partition by ts_code, end_date, report_type
            order by ann_date desc nulls last,
                     f_ann_date desc nulls last,
                     update_flag desc nulls last,
                     raw_loaded_at desc nulls last,
                     source_run_id desc nulls last
        ) as source_version_rank
    from {{ ref('stg_fina_indicator') }}
),

fina_indicator_latest as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        eps,
        dt_eps,
        grossprofit_margin,
        netprofit_margin,
        roe,
        roa,
        debt_to_assets,
        or_yoy,
        netprofit_yoy,
        source_run_id,
        raw_loaded_at
    from fina_indicator_ranked
    where source_version_rank = 1
),

latest_source_versions as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        1 as source_priority
    from income_latest

    union all

    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        2 as source_priority
    from balancesheet_latest

    union all

    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        3 as source_priority
    from cashflow_latest

    union all

    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        4 as source_priority
    from fina_indicator_latest
),

latest_report_versions as (
    select
        ts_code,
        ann_date,
        f_ann_date,
        end_date,
        report_type,
        comp_type,
        update_flag,
        source_priority,
        row_number() over (
            partition by ts_code, end_date, report_type
            order by ann_date desc nulls last,
                     f_ann_date desc nulls last,
                     update_flag desc nulls last,
                     source_priority
        ) as report_version_rank
    from latest_source_versions
)

select
    report_groups.ts_code,
    report_groups.end_date,
    latest_report_versions.ann_date,
    latest_report_versions.f_ann_date,
    report_groups.report_type,
    latest_report_versions.comp_type,
    latest_report_versions.update_flag,
    true as is_latest,
    income.basic_eps,
    income.diluted_eps,
    income.total_revenue,
    income.revenue,
    income.operate_profit,
    income.total_profit,
    income.n_income,
    income.n_income_attr_p,
    balancesheet.money_cap,
    balancesheet.total_cur_assets,
    balancesheet.total_assets,
    balancesheet.total_cur_liab,
    balancesheet.total_liab,
    balancesheet.total_hldr_eqy_exc_min_int,
    balancesheet.total_liab_hldr_eqy,
    cashflow.net_profit,
    cashflow.n_cashflow_act,
    cashflow.n_cashflow_inv_act,
    cashflow.n_cash_flows_fnc_act,
    cashflow.n_incr_cash_cash_equ,
    cashflow.free_cashflow,
    fina_indicator.eps,
    fina_indicator.dt_eps,
    fina_indicator.grossprofit_margin,
    fina_indicator.netprofit_margin,
    fina_indicator.roe,
    fina_indicator.roa,
    fina_indicator.debt_to_assets,
    fina_indicator.or_yoy,
    fina_indicator.netprofit_yoy,
    coalesce(
        income.source_run_id,
        balancesheet.source_run_id,
        cashflow.source_run_id,
        fina_indicator.source_run_id
    ) as source_run_id,
    coalesce(
        income.raw_loaded_at,
        balancesheet.raw_loaded_at,
        cashflow.raw_loaded_at,
        fina_indicator.raw_loaded_at
    ) as raw_loaded_at,
    income.source_run_id as income_source_run_id,
    balancesheet.source_run_id as balancesheet_source_run_id,
    cashflow.source_run_id as cashflow_source_run_id,
    fina_indicator.source_run_id as fina_indicator_source_run_id,
    income.raw_loaded_at as income_raw_loaded_at,
    balancesheet.raw_loaded_at as balancesheet_raw_loaded_at,
    cashflow.raw_loaded_at as cashflow_raw_loaded_at,
    fina_indicator.raw_loaded_at as fina_indicator_raw_loaded_at
from report_groups
left join latest_report_versions
    on report_groups.ts_code = latest_report_versions.ts_code
    and report_groups.end_date = latest_report_versions.end_date
    and report_groups.report_type = latest_report_versions.report_type
    and latest_report_versions.report_version_rank = 1
left join income_latest as income
    on report_groups.ts_code = income.ts_code
    and report_groups.end_date = income.end_date
    and report_groups.report_type = income.report_type
left join balancesheet_latest as balancesheet
    on report_groups.ts_code = balancesheet.ts_code
    and report_groups.end_date = balancesheet.end_date
    and report_groups.report_type = balancesheet.report_type
left join cashflow_latest as cashflow
    on report_groups.ts_code = cashflow.ts_code
    and report_groups.end_date = cashflow.end_date
    and report_groups.report_type = cashflow.report_type
left join fina_indicator_latest as fina_indicator
    on report_groups.ts_code = fina_indicator.ts_code
    and report_groups.end_date = fina_indicator.end_date
    and report_groups.report_type = fina_indicator.report_type

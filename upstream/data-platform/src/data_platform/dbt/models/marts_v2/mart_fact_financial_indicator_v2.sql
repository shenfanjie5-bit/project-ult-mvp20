{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 fact_financial_indicator mart. Renames the
-- provider-shaped security identifier to the canonical security_id per the
-- provider catalog field_mapping; drops raw-zone lineage columns (they live
-- on mart_lineage_fact_financial_indicator.sql).

select
    ts_code as security_id,
    end_date,
    ann_date,
    f_ann_date,
    report_type,
    comp_type,
    update_flag,
    is_latest,
    cast(basic_eps as decimal(38, 18)) as basic_eps,
    cast(diluted_eps as decimal(38, 18)) as diluted_eps,
    cast(total_revenue as decimal(38, 18)) as total_revenue,
    cast(revenue as decimal(38, 18)) as revenue,
    cast(operate_profit as decimal(38, 18)) as operate_profit,
    cast(total_profit as decimal(38, 18)) as total_profit,
    cast(n_income as decimal(38, 18)) as n_income,
    cast(n_income_attr_p as decimal(38, 18)) as n_income_attr_p,
    cast(money_cap as decimal(38, 18)) as money_cap,
    cast(total_cur_assets as decimal(38, 18)) as total_cur_assets,
    cast(total_assets as decimal(38, 18)) as total_assets,
    cast(total_cur_liab as decimal(38, 18)) as total_cur_liab,
    cast(total_liab as decimal(38, 18)) as total_liab,
    cast(total_hldr_eqy_exc_min_int as decimal(38, 18))
        as total_hldr_eqy_exc_min_int,
    cast(total_liab_hldr_eqy as decimal(38, 18)) as total_liab_hldr_eqy,
    cast(net_profit as decimal(38, 18)) as net_profit,
    cast(n_cashflow_act as decimal(38, 18)) as n_cashflow_act,
    cast(n_cashflow_inv_act as decimal(38, 18)) as n_cashflow_inv_act,
    cast(n_cash_flows_fnc_act as decimal(38, 18)) as n_cash_flows_fnc_act,
    cast(n_incr_cash_cash_equ as decimal(38, 18)) as n_incr_cash_cash_equ,
    cast(free_cashflow as decimal(38, 18)) as free_cashflow,
    cast(eps as decimal(38, 18)) as eps,
    cast(dt_eps as decimal(38, 18)) as dt_eps,
    cast(grossprofit_margin as decimal(38, 18)) as grossprofit_margin,
    cast(netprofit_margin as decimal(38, 18)) as netprofit_margin,
    cast(roe as decimal(38, 18)) as roe,
    cast(roa as decimal(38, 18)) as roa,
    cast(debt_to_assets as decimal(38, 18)) as debt_to_assets,
    cast(or_yoy as decimal(38, 18)) as or_yoy,
    cast(netprofit_yoy as decimal(38, 18)) as netprofit_yoy
from {{ ref('int_financial_reports_latest') }}
where is_latest

{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "cashflow",
    [
        "ts_code",
        "ann_date",
        "f_ann_date",
        "end_date",
        "report_type",
        "comp_type",
        "update_flag",
        "net_profit",
        "c_fr_sale_sg",
        "c_inf_fr_operate_a",
        "c_paid_goods_s",
        "st_cash_out_act",
        "n_cashflow_act",
        "n_cashflow_inv_act",
        "n_cash_flows_fnc_act",
        "n_incr_cash_cash_equ",
        "c_cash_equ_beg_period",
        "c_cash_equ_end_period",
        "free_cashflow"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"f_ann_date\" as varchar)), ''), '%Y%m%d')::date as \"f_ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"report_type\" as varchar)), '') as varchar) as \"report_type\"",
        "cast(nullif(trim(cast(\"comp_type\" as varchar)), '') as varchar) as \"comp_type\"",
        "cast(nullif(trim(cast(\"update_flag\" as varchar)), '') as varchar) as \"update_flag\"",
        "cast(\"net_profit\" as decimal(38, 18)) as \"net_profit\"",
        "cast(\"c_fr_sale_sg\" as decimal(38, 18)) as \"c_fr_sale_sg\"",
        "cast(\"c_inf_fr_operate_a\" as decimal(38, 18)) as \"c_inf_fr_operate_a\"",
        "cast(\"c_paid_goods_s\" as decimal(38, 18)) as \"c_paid_goods_s\"",
        "cast(\"st_cash_out_act\" as decimal(38, 18)) as \"st_cash_out_act\"",
        "cast(\"n_cashflow_act\" as decimal(38, 18)) as \"n_cashflow_act\"",
        "cast(\"n_cashflow_inv_act\" as decimal(38, 18)) as \"n_cashflow_inv_act\"",
        "cast(\"n_cash_flows_fnc_act\" as decimal(38, 18)) as \"n_cash_flows_fnc_act\"",
        "cast(\"n_incr_cash_cash_equ\" as decimal(38, 18)) as \"n_incr_cash_cash_equ\"",
        "cast(\"c_cash_equ_beg_period\" as decimal(38, 18)) as \"c_cash_equ_beg_period\"",
        "cast(\"c_cash_equ_end_period\" as decimal(38, 18)) as \"c_cash_equ_end_period\"",
        "cast(\"free_cashflow\" as decimal(38, 18)) as \"free_cashflow\""
    ]
) }}

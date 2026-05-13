{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "balancesheet",
    [
        "ts_code",
        "ann_date",
        "f_ann_date",
        "end_date",
        "report_type",
        "comp_type",
        "update_flag",
        "money_cap",
        "accounts_receiv",
        "inventories",
        "total_cur_assets",
        "fix_assets",
        "total_assets",
        "total_cur_liab",
        "total_liab",
        "total_hldr_eqy_exc_min_int",
        "total_hldr_eqy_inc_min_int",
        "total_liab_hldr_eqy"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"f_ann_date\" as varchar)), ''), '%Y%m%d')::date as \"f_ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"report_type\" as varchar)), '') as varchar) as \"report_type\"",
        "cast(nullif(trim(cast(\"comp_type\" as varchar)), '') as varchar) as \"comp_type\"",
        "cast(nullif(trim(cast(\"update_flag\" as varchar)), '') as varchar) as \"update_flag\"",
        "cast(\"money_cap\" as decimal(38, 18)) as \"money_cap\"",
        "cast(\"accounts_receiv\" as decimal(38, 18)) as \"accounts_receiv\"",
        "cast(\"inventories\" as decimal(38, 18)) as \"inventories\"",
        "cast(\"total_cur_assets\" as decimal(38, 18)) as \"total_cur_assets\"",
        "cast(\"fix_assets\" as decimal(38, 18)) as \"fix_assets\"",
        "cast(\"total_assets\" as decimal(38, 18)) as \"total_assets\"",
        "cast(\"total_cur_liab\" as decimal(38, 18)) as \"total_cur_liab\"",
        "cast(\"total_liab\" as decimal(38, 18)) as \"total_liab\"",
        "cast(\"total_hldr_eqy_exc_min_int\" as decimal(38, 18)) as \"total_hldr_eqy_exc_min_int\"",
        "cast(\"total_hldr_eqy_inc_min_int\" as decimal(38, 18)) as \"total_hldr_eqy_inc_min_int\"",
        "cast(\"total_liab_hldr_eqy\" as decimal(38, 18)) as \"total_liab_hldr_eqy\""
    ]
) }}

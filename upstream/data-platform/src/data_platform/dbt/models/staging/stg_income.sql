{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "income",
    [
        "ts_code",
        "ann_date",
        "f_ann_date",
        "end_date",
        "report_type",
        "comp_type",
        "update_flag",
        "basic_eps",
        "diluted_eps",
        "total_revenue",
        "revenue",
        "operate_profit",
        "total_profit",
        "income_tax",
        "n_income",
        "n_income_attr_p",
        "minority_gain",
        "ebit",
        "ebitda"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"f_ann_date\" as varchar)), ''), '%Y%m%d')::date as \"f_ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"report_type\" as varchar)), '') as varchar) as \"report_type\"",
        "cast(nullif(trim(cast(\"comp_type\" as varchar)), '') as varchar) as \"comp_type\"",
        "cast(nullif(trim(cast(\"update_flag\" as varchar)), '') as varchar) as \"update_flag\"",
        "cast(\"basic_eps\" as decimal(38, 18)) as \"basic_eps\"",
        "cast(\"diluted_eps\" as decimal(38, 18)) as \"diluted_eps\"",
        "cast(\"total_revenue\" as decimal(38, 18)) as \"total_revenue\"",
        "cast(\"revenue\" as decimal(38, 18)) as \"revenue\"",
        "cast(\"operate_profit\" as decimal(38, 18)) as \"operate_profit\"",
        "cast(\"total_profit\" as decimal(38, 18)) as \"total_profit\"",
        "cast(\"income_tax\" as decimal(38, 18)) as \"income_tax\"",
        "cast(\"n_income\" as decimal(38, 18)) as \"n_income\"",
        "cast(\"n_income_attr_p\" as decimal(38, 18)) as \"n_income_attr_p\"",
        "cast(\"minority_gain\" as decimal(38, 18)) as \"minority_gain\"",
        "cast(\"ebit\" as decimal(38, 18)) as \"ebit\"",
        "cast(\"ebitda\" as decimal(38, 18)) as \"ebitda\""
    ]
) }}

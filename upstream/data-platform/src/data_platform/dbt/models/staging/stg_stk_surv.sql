{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "stk_surv",
    [
        "ts_code",
        "name",
        "surv_date",
        "fund_visitors",
        "rece_place",
        "rece_mode",
        "rece_org",
        "org_type",
        "comp_rece"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "strptime(nullif(trim(cast(\"surv_date\" as varchar)), ''), '%Y%m%d')::date as \"surv_date\"",
        "cast(nullif(trim(cast(\"fund_visitors\" as varchar)), '') as varchar) as \"fund_visitors\"",
        "cast(nullif(trim(cast(\"rece_place\" as varchar)), '') as varchar) as \"rece_place\"",
        "cast(nullif(trim(cast(\"rece_mode\" as varchar)), '') as varchar) as \"rece_mode\"",
        "cast(nullif(trim(cast(\"rece_org\" as varchar)), '') as varchar) as \"rece_org\"",
        "cast(nullif(trim(cast(\"org_type\" as varchar)), '') as varchar) as \"org_type\"",
        "cast(nullif(trim(cast(\"comp_rece\" as varchar)), '') as varchar) as \"comp_rece\""
    ]
) }}

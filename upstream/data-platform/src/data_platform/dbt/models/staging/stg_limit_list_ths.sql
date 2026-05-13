{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "limit_list_ths",
    [
        "trade_date",
        "ts_code",
        "name",
        "price",
        "pct_chg",
        "open_num",
        "lu_desc",
        "limit_type",
        "tag",
        "status",
        "limit_order",
        "limit_amount",
        "turnover_rate",
        "free_float",
        "lu_limit_order",
        "limit_up_suc_rate",
        "turnover",
        "market_type"
    ],
    [
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"price\" as varchar)), '') as varchar) as \"price\"",
        "cast(nullif(trim(cast(\"pct_chg\" as varchar)), '') as varchar) as \"pct_chg\"",
        "cast(nullif(trim(cast(\"open_num\" as varchar)), '') as varchar) as \"open_num\"",
        "cast(nullif(trim(cast(\"lu_desc\" as varchar)), '') as varchar) as \"lu_desc\"",
        "cast(nullif(trim(cast(\"limit_type\" as varchar)), '') as varchar) as \"limit_type\"",
        "cast(nullif(trim(cast(\"tag\" as varchar)), '') as varchar) as \"tag\"",
        "cast(nullif(trim(cast(\"status\" as varchar)), '') as varchar) as \"status\"",
        "cast(nullif(trim(cast(\"limit_order\" as varchar)), '') as varchar) as \"limit_order\"",
        "cast(nullif(trim(cast(\"limit_amount\" as varchar)), '') as varchar) as \"limit_amount\"",
        "cast(nullif(trim(cast(\"turnover_rate\" as varchar)), '') as varchar) as \"turnover_rate\"",
        "cast(nullif(trim(cast(\"free_float\" as varchar)), '') as varchar) as \"free_float\"",
        "cast(nullif(trim(cast(\"lu_limit_order\" as varchar)), '') as varchar) as \"lu_limit_order\"",
        "cast(nullif(trim(cast(\"limit_up_suc_rate\" as varchar)), '') as varchar) as \"limit_up_suc_rate\"",
        "cast(nullif(trim(cast(\"turnover\" as varchar)), '') as varchar) as \"turnover\"",
        "cast(nullif(trim(cast(\"market_type\" as varchar)), '') as varchar) as \"market_type\""
    ]
) }}

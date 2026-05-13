{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "daily_basic",
    [
        "ts_code",
        "trade_date",
        "close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "dv_ratio",
        "dv_ttm",
        "total_share",
        "float_share",
        "free_share",
        "total_mv",
        "circ_mv"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"close\" as varchar)), '') as varchar) as \"close\"",
        "cast(nullif(trim(cast(\"turnover_rate\" as varchar)), '') as varchar) as \"turnover_rate\"",
        "cast(nullif(trim(cast(\"turnover_rate_f\" as varchar)), '') as varchar) as \"turnover_rate_f\"",
        "cast(nullif(trim(cast(\"volume_ratio\" as varchar)), '') as varchar) as \"volume_ratio\"",
        "cast(nullif(trim(cast(\"pe\" as varchar)), '') as varchar) as \"pe\"",
        "cast(nullif(trim(cast(\"pe_ttm\" as varchar)), '') as varchar) as \"pe_ttm\"",
        "cast(nullif(trim(cast(\"pb\" as varchar)), '') as varchar) as \"pb\"",
        "cast(nullif(trim(cast(\"ps\" as varchar)), '') as varchar) as \"ps\"",
        "cast(nullif(trim(cast(\"ps_ttm\" as varchar)), '') as varchar) as \"ps_ttm\"",
        "cast(nullif(trim(cast(\"dv_ratio\" as varchar)), '') as varchar) as \"dv_ratio\"",
        "cast(nullif(trim(cast(\"dv_ttm\" as varchar)), '') as varchar) as \"dv_ttm\"",
        "cast(nullif(trim(cast(\"total_share\" as varchar)), '') as varchar) as \"total_share\"",
        "cast(nullif(trim(cast(\"float_share\" as varchar)), '') as varchar) as \"float_share\"",
        "cast(nullif(trim(cast(\"free_share\" as varchar)), '') as varchar) as \"free_share\"",
        "cast(nullif(trim(cast(\"total_mv\" as varchar)), '') as varchar) as \"total_mv\"",
        "cast(nullif(trim(cast(\"circ_mv\" as varchar)), '') as varchar) as \"circ_mv\""
    ]
) }}

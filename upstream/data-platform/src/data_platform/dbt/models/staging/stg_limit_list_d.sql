{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "limit_list_d",
    [
        "trade_date",
        "ts_code",
        "industry",
        "name",
        "close",
        "pct_chg",
        "amount",
        "limit_amount",
        "float_mv",
        "total_mv",
        "turnover_ratio",
        "fd_amount",
        "first_time",
        "last_time",
        "open_times",
        "up_stat",
        "limit_times",
        "limit"
    ],
    [
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "cast(nullif(trim(cast(\"industry\" as varchar)), '') as varchar) as \"industry\"",
        "cast(nullif(trim(cast(\"name\" as varchar)), '') as varchar) as \"name\"",
        "cast(nullif(trim(cast(\"close\" as varchar)), '') as varchar) as \"close\"",
        "cast(nullif(trim(cast(\"pct_chg\" as varchar)), '') as varchar) as \"pct_chg\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\"",
        "cast(nullif(trim(cast(\"limit_amount\" as varchar)), '') as varchar) as \"limit_amount\"",
        "cast(nullif(trim(cast(\"float_mv\" as varchar)), '') as varchar) as \"float_mv\"",
        "cast(nullif(trim(cast(\"total_mv\" as varchar)), '') as varchar) as \"total_mv\"",
        "cast(nullif(trim(cast(\"turnover_ratio\" as varchar)), '') as varchar) as \"turnover_ratio\"",
        "cast(nullif(trim(cast(\"fd_amount\" as varchar)), '') as varchar) as \"fd_amount\"",
        "cast(nullif(trim(cast(\"first_time\" as varchar)), '') as varchar) as \"first_time\"",
        "cast(nullif(trim(cast(\"last_time\" as varchar)), '') as varchar) as \"last_time\"",
        "cast(nullif(trim(cast(\"open_times\" as varchar)), '') as varchar) as \"open_times\"",
        "cast(nullif(trim(cast(\"up_stat\" as varchar)), '') as varchar) as \"up_stat\"",
        "cast(nullif(trim(cast(\"limit_times\" as varchar)), '') as varchar) as \"limit_times\"",
        "cast(nullif(trim(cast(\"limit\" as varchar)), '') as varchar) as \"limit\""
    ]
) }}

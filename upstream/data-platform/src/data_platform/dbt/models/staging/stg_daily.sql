{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "daily",
    [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"trade_date\" as varchar)), ''), '%Y%m%d')::date as \"trade_date\"",
        "cast(nullif(trim(cast(\"open\" as varchar)), '') as varchar) as \"open\"",
        "cast(nullif(trim(cast(\"high\" as varchar)), '') as varchar) as \"high\"",
        "cast(nullif(trim(cast(\"low\" as varchar)), '') as varchar) as \"low\"",
        "cast(nullif(trim(cast(\"close\" as varchar)), '') as varchar) as \"close\"",
        "cast(nullif(trim(cast(\"pre_close\" as varchar)), '') as varchar) as \"pre_close\"",
        "cast(nullif(trim(cast(\"change\" as varchar)), '') as varchar) as \"change\"",
        "cast(nullif(trim(cast(\"pct_chg\" as varchar)), '') as varchar) as \"pct_chg\"",
        "cast(nullif(trim(cast(\"vol\" as varchar)), '') as varchar) as \"vol\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\""
    ]
) }}

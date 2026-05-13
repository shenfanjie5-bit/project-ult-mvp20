{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "repurchase",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "proc",
        "exp_date",
        "vol",
        "amount",
        "high_limit",
        "low_limit"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"proc\" as varchar)), '') as varchar) as \"proc\"",
        "strptime(nullif(trim(cast(\"exp_date\" as varchar)), ''), '%Y%m%d')::date as \"exp_date\"",
        "cast(nullif(trim(cast(\"vol\" as varchar)), '') as varchar) as \"vol\"",
        "cast(nullif(trim(cast(\"amount\" as varchar)), '') as varchar) as \"amount\"",
        "cast(nullif(trim(cast(\"high_limit\" as varchar)), '') as varchar) as \"high_limit\"",
        "cast(nullif(trim(cast(\"low_limit\" as varchar)), '') as varchar) as \"low_limit\""
    ]
) }}

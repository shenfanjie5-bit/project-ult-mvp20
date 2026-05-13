{{ config(materialized="view") }}

{{ stg_latest_raw(
    "tushare",
    "forecast",
    [
        "ts_code",
        "ann_date",
        "end_date",
        "type",
        "p_change_min",
        "p_change_max",
        "net_profit_min",
        "net_profit_max",
        "last_parent_net",
        "first_ann_date",
        "summary",
        "change_reason",
        "update_flag"
    ],
    [
        "cast(nullif(trim(cast(\"ts_code\" as varchar)), '') as varchar) as \"ts_code\"",
        "strptime(nullif(trim(cast(\"ann_date\" as varchar)), ''), '%Y%m%d')::date as \"ann_date\"",
        "strptime(nullif(trim(cast(\"end_date\" as varchar)), ''), '%Y%m%d')::date as \"end_date\"",
        "cast(nullif(trim(cast(\"type\" as varchar)), '') as varchar) as \"type\"",
        "cast(nullif(trim(cast(\"p_change_min\" as varchar)), '') as varchar) as \"p_change_min\"",
        "cast(nullif(trim(cast(\"p_change_max\" as varchar)), '') as varchar) as \"p_change_max\"",
        "cast(nullif(trim(cast(\"net_profit_min\" as varchar)), '') as varchar) as \"net_profit_min\"",
        "cast(nullif(trim(cast(\"net_profit_max\" as varchar)), '') as varchar) as \"net_profit_max\"",
        "cast(nullif(trim(cast(\"last_parent_net\" as varchar)), '') as varchar) as \"last_parent_net\"",
        "strptime(nullif(trim(cast(\"first_ann_date\" as varchar)), ''), '%Y%m%d')::date as \"first_ann_date\"",
        "cast(nullif(trim(cast(\"summary\" as varchar)), '') as varchar) as \"summary\"",
        "cast(nullif(trim(cast(\"change_reason\" as varchar)), '') as varchar) as \"change_reason\"",
        "cast(nullif(trim(cast(\"update_flag\" as varchar)), '') as varchar) as \"update_flag\""
    ]
) }}

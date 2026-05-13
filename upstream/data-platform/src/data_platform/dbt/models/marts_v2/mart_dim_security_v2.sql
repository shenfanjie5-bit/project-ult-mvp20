{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 dim_security mart.
-- Provider-shaped identifier columns are aliased to canonical names per the
-- provider-catalog field_mapping in registry.py. Raw-zone lineage columns
-- are intentionally not selected here; they live on the sibling mart in
-- dbt/models/marts_lineage/mart_lineage_dim_security.sql.

select
    ts_code as security_id,
    symbol,
    name as display_name,
    market,
    industry,
    list_date,
    is_active,
    area,
    fullname,
    exchange,
    curr_type,
    list_status,
    delist_date,
    setup_date,
    province,
    city,
    cast(nullif(trim(cast(reg_capital as varchar)), '') as decimal(38, 18))
        as reg_capital,
    cast(nullif(trim(cast(employees as varchar)), '') as decimal(38, 18))
        as employees,
    main_business,
    latest_namechange_name,
    latest_namechange_start_date,
    latest_namechange_end_date,
    latest_namechange_ann_date,
    latest_namechange_reason
from {{ ref('int_security_master') }}

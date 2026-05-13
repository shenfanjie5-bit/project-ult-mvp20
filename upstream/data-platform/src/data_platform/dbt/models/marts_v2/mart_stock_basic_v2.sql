{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 stock_basic mart. Renames provider-shaped
-- identifier columns to canonical names per the provider catalog field_mapping
-- in registry.py. Raw-zone lineage columns are intentionally not selected
-- here; they live on dbt/models/marts_lineage/mart_lineage_stock_basic.sql.

select
    ts_code as security_id,
    symbol,
    name as display_name,
    area,
    industry,
    market,
    list_date,
    is_active
from {{ ref('int_security_master') }}

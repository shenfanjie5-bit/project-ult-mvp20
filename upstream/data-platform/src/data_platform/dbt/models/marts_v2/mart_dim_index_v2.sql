{{ config(materialized="table") }}

-- Provider-neutral canonical_v2 dim_index mart. Aliases the provider-shaped
-- index identifier to canonical index_id inside an inner SELECT so the
-- outer aggregation only references the canonical name. Raw-zone lineage
-- columns live on mart_lineage_dim_index.sql.

select
    index_id,
    max(index_name) as index_name,
    max(index_market) as index_market,
    max(index_category) as index_category,
    min(effective_date) as first_effective_date,
    max(effective_date) as latest_effective_date
from (
    select
        index_code as index_id,
        index_name,
        index_market,
        index_category,
        effective_date
    from {{ ref('int_index_membership') }}
) renamed
where index_id is not null
group by index_id

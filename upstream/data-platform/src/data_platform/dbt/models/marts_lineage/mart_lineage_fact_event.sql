{{ config(materialized="table") }}

-- Provider-aware lineage rows for canonical_v2.fact_event, joined on
-- (event_type, entity_id, event_date, event_key). int_event_timeline now
-- carries per-branch source_interface_id constants; this mart projects them
-- per-row (NOT a composite hardcoded string).
--
-- The event_key derivation expression is byte-identical to
-- mart_fact_event_v2.sql so v2/lineage row sets pair on the composite
-- canonical PK in the canonical_writer pairing validator. The intermediate
-- uniqueness key was intentionally widened in M1.8 to include `summary` (so
-- intra-day multi-row event sources like block_trade flow through);
-- canonical row identity is enforced here at the mart-level event_key +
-- canonical PK parity, and at the writer-side validation in canonical_writer.
-- canonical_v2.fact_event currently covers 8 source interfaces (M1.6 added
-- namechange; M1.8 added block_trade).
--
-- canonical_loaded_at is intentionally NOT projected; the canonical writer
-- injects it on insert.

select
    event_type,
    ts_code as entity_id,
    event_date,
    md5(
        concat_ws(
            '|',
            source_interface_id,
            event_type,
            coalesce(title, ''),
            coalesce(summary, ''),
            coalesce(event_subtype, ''),
            coalesce(cast(related_date as varchar), ''),
            coalesce(reference_url, ''),
            coalesce(rec_time, '')
        )
    ) as event_key,
    cast('tushare' as varchar) as source_provider,
    source_interface_id,
    source_run_id,
    raw_loaded_at
from {{ ref('int_event_timeline') }}

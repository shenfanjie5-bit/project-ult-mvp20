CREATE SCHEMA IF NOT EXISTS data_platform;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace
        WHERE pg_namespace.nspname = 'data_platform'
          AND pg_type.typname = 'cycle_status'
    ) THEN
        CREATE TYPE data_platform.cycle_status AS ENUM (
            'pending',
            'phase0',
            'phase1',
            'phase2',
            'phase3',
            'published',
            'failed'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS data_platform.cycle_metadata (
    cycle_id TEXT PRIMARY KEY,
    cycle_date DATE UNIQUE NOT NULL,
    status data_platform.cycle_status NOT NULL DEFAULT 'pending',
    cutoff_submitted_at TIMESTAMPTZ NULL,
    cutoff_ingest_seq BIGINT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    selection_frozen_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cycle_metadata_cycle_id_format CHECK (cycle_id ~ '^CYCLE_[0-9]{8}$'),
    CONSTRAINT cycle_metadata_candidate_count_nonnegative CHECK (candidate_count >= 0)
);

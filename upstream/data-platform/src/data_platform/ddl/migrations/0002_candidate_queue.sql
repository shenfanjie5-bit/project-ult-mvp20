CREATE SCHEMA IF NOT EXISTS data_platform;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace
        WHERE pg_namespace.nspname = 'data_platform'
          AND pg_type.typname = 'candidate_payload_type'
    ) THEN
        CREATE TYPE data_platform.candidate_payload_type AS ENUM (
            'Ex-0',
            'Ex-1',
            'Ex-2',
            'Ex-3'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type
        JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace
        WHERE pg_namespace.nspname = 'data_platform'
          AND pg_type.typname = 'validation_status'
    ) THEN
        CREATE TYPE data_platform.validation_status AS ENUM (
            'pending',
            'accepted',
            'rejected'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS data_platform.candidate_queue (
    id BIGSERIAL PRIMARY KEY,
    payload_type data_platform.candidate_payload_type NOT NULL,
    payload JSONB NOT NULL,
    submitted_by TEXT NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingest_seq BIGSERIAL,
    validation_status data_platform.validation_status NOT NULL DEFAULT 'pending',
    rejection_reason TEXT NULL,
    CONSTRAINT candidate_queue_ingest_seq_key UNIQUE (ingest_seq),
    CONSTRAINT candidate_queue_payload_is_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT candidate_queue_payload_excludes_ingest_metadata CHECK (
        NOT (payload ? 'submitted_at')
        AND NOT (payload ? 'ingest_seq')
    )
);

CREATE OR REPLACE VIEW data_platform.ingest_metadata AS
SELECT
    id AS candidate_id,
    payload_type,
    submitted_by,
    submitted_at,
    ingest_seq,
    validation_status,
    rejection_reason
FROM data_platform.candidate_queue;

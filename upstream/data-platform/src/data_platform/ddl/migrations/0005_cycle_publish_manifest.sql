CREATE SCHEMA IF NOT EXISTS data_platform;

CREATE TABLE IF NOT EXISTS data_platform.cycle_publish_manifest (
    published_cycle_id TEXT PRIMARY KEY REFERENCES data_platform.cycle_metadata(cycle_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    formal_table_snapshots JSONB NOT NULL,
    CONSTRAINT cycle_publish_manifest_snapshots_is_object CHECK (
        jsonb_typeof(formal_table_snapshots) = 'object'
    )
);

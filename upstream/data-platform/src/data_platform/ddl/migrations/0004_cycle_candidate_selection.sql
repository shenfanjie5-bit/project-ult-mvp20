CREATE SCHEMA IF NOT EXISTS data_platform;

CREATE TABLE IF NOT EXISTS data_platform.cycle_candidate_selection (
    cycle_id TEXT NOT NULL REFERENCES data_platform.cycle_metadata(cycle_id),
    candidate_id BIGINT NOT NULL REFERENCES data_platform.candidate_queue(id),
    selected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cycle_id, candidate_id),
    UNIQUE (candidate_id)
);

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS jobs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename      VARCHAR(255) NOT NULL,
    file_key      VARCHAR(500) NOT NULL,
    file_size     BIGINT       NOT NULL DEFAULT 0,
    status        VARCHAR(50)  NOT NULL DEFAULT 'queued',
    current_step  VARCHAR(100),
    result        JSONB,
    error         TEXT,
    elapsed_ms    INTEGER,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC);

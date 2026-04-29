-- migrations/001_audit_log.sql

CREATE TABLE kyc_audit_log (
    id               BIGSERIAL PRIMARY KEY,
    case_id          TEXT          NOT NULL,
    event_type       TEXT          NOT NULL,
    -- Values: intake, agent_called, agent_result, decision,
    --         escalation, reupload_requested, dlq_failure, notified
    agent_id         TEXT,
    input_hash       TEXT,         -- SHA-256 of raw input (not the input itself)
    result_summary   JSONB,        -- Sanitised result — no raw PII
    prompt_version   TEXT,         -- e.g. "decision_v1"
    risk_level       TEXT,         -- Low | Medium | High (when known)
    operator_id      TEXT,         -- NULL if automated; user ID if human action
    latency_ms       INTEGER,
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Indexes for compliance queries
CREATE INDEX idx_audit_case_id    ON kyc_audit_log (case_id);
CREATE INDEX idx_audit_created_at ON kyc_audit_log (created_at);
CREATE INDEX idx_audit_event_type ON kyc_audit_log (event_type);

-- Revoke mutation permissions — append-only
REVOKE UPDATE, DELETE ON kyc_audit_log FROM kyc_app_user;

-- Human review queue
CREATE TABLE kyc_review_queue (
    id           BIGSERIAL PRIMARY KEY,
    case_id      TEXT          NOT NULL UNIQUE,
    reason       TEXT          NOT NULL,  -- sanctions_hit | high_risk | agent_failure
    priority     INTEGER       NOT NULL DEFAULT 5,  -- 1 = highest
    assigned_to  TEXT,
    status       TEXT          NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    resolution   JSONB
);

CREATE INDEX idx_review_status ON kyc_review_queue (status, priority);

-- BigQuery DDL: claims table
-- Tracks individual claims filed against a policy.

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.claims` (
    claim_id            STRING      NOT NULL,
    policy_id           STRING      NOT NULL,
    claim_date          DATE        NOT NULL,
    claim_type          STRING      NOT NULL,  -- MEDICAL | DENTAL | VISION | PHARMACY | MENTAL_HEALTH
    status              STRING      NOT NULL,  -- OPEN | IN_REVIEW | APPROVED | DENIED | CLOSED
    amount_requested    NUMERIC     NOT NULL,
    amount_approved     NUMERIC,
    denial_reason       STRING,
    adjuster_id         STRING,
    resolved_date       DATE,
    created_at          TIMESTAMP   NOT NULL   DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
    description = "Insurance claims filed against policies"
);

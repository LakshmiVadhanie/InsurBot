-- BigQuery DDL: policies table
-- Represents individual insurance policies held by customers.

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.policies` (
    policy_id       STRING      NOT NULL,
    holder_name     STRING      NOT NULL,
    holder_email    STRING,
    plan_id         STRING      NOT NULL,
    plan_type       STRING      NOT NULL,  -- HMO | PPO | EPO | HDHP
    effective_date  DATE        NOT NULL,
    expiry_date     DATE        NOT NULL,
    premium_amount  NUMERIC     NOT NULL,
    status          STRING      NOT NULL,  -- ACTIVE | LAPSED | CANCELLED | PENDING
    state           STRING,                -- US state code
    created_at      TIMESTAMP   NOT NULL   DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
    description = "Insurance policies master table",
    partition_expiration_days = NULL
);

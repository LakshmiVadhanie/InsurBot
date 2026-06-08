-- BigQuery DDL: coverage_plans table
-- Defines the available insurance plan tiers and their coverage attributes.

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.coverage_plans` (
    plan_id                 STRING      NOT NULL,
    plan_name               STRING      NOT NULL,
    tier                    STRING      NOT NULL,  -- BRONZE | SILVER | GOLD | PLATINUM
    plan_type               STRING      NOT NULL,  -- HMO | PPO | EPO | HDHP
    monthly_premium         NUMERIC     NOT NULL,
    deductible              NUMERIC     NOT NULL,
    out_of_pocket_max       NUMERIC     NOT NULL,
    copay_primary           NUMERIC,               -- Primary care copay
    copay_specialist        NUMERIC,               -- Specialist copay
    covers_dental           BOOL        NOT NULL   DEFAULT FALSE,
    covers_vision           BOOL        NOT NULL   DEFAULT FALSE,
    covers_mental_health    BOOL        NOT NULL   DEFAULT FALSE,
    covers_pharmacy         BOOL        NOT NULL   DEFAULT TRUE,
    network_size            STRING,                -- NARROW | BROAD | NATIONAL
    effective_year          INT64       NOT NULL,
    created_at              TIMESTAMP   NOT NULL   DEFAULT CURRENT_TIMESTAMP()
)
OPTIONS (
    description = "Insurance plan tiers and coverage attributes"
);

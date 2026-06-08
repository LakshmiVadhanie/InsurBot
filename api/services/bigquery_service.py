"""
BigQuery service.

Wraps the google-cloud-bigquery client with parameterized query builders
for the three primary InsurBot workflows:

  - policy_lookup    : find policies by ID, holder name, or plan type
  - claims_triage    : aggregate claim status for a policy
  - coverage_compare : return plan details for side-by-side comparison

All queries use QueryJobConfig with query parameters to prevent injection.
Results are validated and returned as typed Pydantic models.
"""

from __future__ import annotations

import structlog
from google.cloud import bigquery
from tenacity import retry, stop_after_attempt, wait_exponential

from api.guardrails.schemas import Claim, ClaimSummary, CoveragePlan, Policy

logger = structlog.get_logger(__name__)


class BigQueryService:
    """Stateful BigQuery client scoped to a single dataset."""

    def __init__(self, project_id: str, dataset: str, location: str) -> None:
        self._project = project_id
        self._dataset = dataset
        self._location = location
        self._client = bigquery.Client(project=project_id)
        self._table = lambda name: f"`{project_id}.{dataset}.{name}`"

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    def ping(self) -> None:
        """Verify BigQuery connectivity by listing datasets. Raises on failure."""
        list(self._client.list_datasets(max_results=1))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def _run_query(
        self,
        sql: str,
        params: list[bigquery.ScalarQueryParameter | bigquery.ArrayQueryParameter],
    ) -> list[dict]:
        job_config = bigquery.QueryJobConfig(
            query_parameters=params,
        )
        job = self._client.query(sql, job_config=job_config, location=self._location)
        rows = list(job.result())
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Policy lookup
    # ------------------------------------------------------------------

    def get_policy_by_id(self, policy_id: str) -> Policy | None:
        sql = f"""
            SELECT
                policy_id, holder_name, holder_email, plan_id, plan_type,
                effective_date, expiry_date, premium_amount, status, state
            FROM {self._table('policies')}
            WHERE policy_id = @policy_id
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("policy_id", "STRING", policy_id)]
        rows = self._run_query(sql, params)
        if not rows:
            return None
        logger.info("policy_lookup_by_id", policy_id=policy_id, found=True)
        return Policy(**rows[0])

    def search_policies_by_holder(
        self,
        holder_name: str,
        limit: int = 5,
    ) -> list[Policy]:
        sql = f"""
            SELECT
                policy_id, holder_name, holder_email, plan_id, plan_type,
                effective_date, expiry_date, premium_amount, status, state
            FROM {self._table('policies')}
            WHERE LOWER(holder_name) LIKE LOWER(@holder_pattern)
            ORDER BY effective_date DESC
            LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("holder_pattern", "STRING", f"%{holder_name}%"),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
        rows = self._run_query(sql, params)
        logger.info("policy_search_by_holder", holder_name=holder_name, result_count=len(rows))
        return [Policy(**r) for r in rows]

    def get_policies_by_status(self, status: str, limit: int = 10) -> list[Policy]:
        sql = f"""
            SELECT
                policy_id, holder_name, holder_email, plan_id, plan_type,
                effective_date, expiry_date, premium_amount, status, state
            FROM {self._table('policies')}
            WHERE status = @status
            ORDER BY expiry_date DESC
            LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("status", "STRING", status.upper()),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
        rows = self._run_query(sql, params)
        return [Policy(**r) for r in rows]

    # ------------------------------------------------------------------
    # Claims triage
    # ------------------------------------------------------------------

    def get_claims_for_policy(self, policy_id: str) -> list[Claim]:
        sql = f"""
            SELECT
                claim_id, policy_id, claim_date, claim_type, status,
                amount_requested, amount_approved, denial_reason,
                adjuster_id, resolved_date
            FROM {self._table('claims')}
            WHERE policy_id = @policy_id
            ORDER BY claim_date DESC
        """
        params = [bigquery.ScalarQueryParameter("policy_id", "STRING", policy_id)]
        rows = self._run_query(sql, params)
        logger.info("claims_fetched", policy_id=policy_id, count=len(rows))
        return [Claim(**r) for r in rows]

    def get_claim_summary(self, policy_id: str) -> ClaimSummary | None:
        sql = f"""
            SELECT
                policy_id,
                COUNT(*) AS total_claims,
                COUNTIF(status = 'OPEN') AS open_claims,
                COUNTIF(status = 'APPROVED') AS approved_claims,
                COUNTIF(status = 'DENIED') AS denied_claims,
                ROUND(SUM(amount_requested), 2) AS total_requested,
                ROUND(SUM(IFNULL(amount_approved, 0)), 2) AS total_approved
            FROM {self._table('claims')}
            WHERE policy_id = @policy_id
            GROUP BY policy_id
        """
        params = [bigquery.ScalarQueryParameter("policy_id", "STRING", policy_id)]
        rows = self._run_query(sql, params)
        if not rows:
            return None
        return ClaimSummary(**rows[0])

    def get_open_claims_by_type(self, claim_type: str, limit: int = 10) -> list[Claim]:
        sql = f"""
            SELECT
                claim_id, policy_id, claim_date, claim_type, status,
                amount_requested, amount_approved, denial_reason,
                adjuster_id, resolved_date
            FROM {self._table('claims')}
            WHERE claim_type = @claim_type
              AND status IN ('OPEN', 'IN_REVIEW')
            ORDER BY claim_date DESC
            LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("claim_type", "STRING", claim_type.upper()),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
        rows = self._run_query(sql, params)
        return [Claim(**r) for r in rows]

    # ------------------------------------------------------------------
    # Coverage comparison
    # ------------------------------------------------------------------

    def get_plan_by_id(self, plan_id: str) -> CoveragePlan | None:
        sql = f"""
            SELECT
                plan_id, plan_name, tier, plan_type, monthly_premium, deductible,
                out_of_pocket_max, copay_primary, copay_specialist, covers_dental,
                covers_vision, covers_mental_health, covers_pharmacy,
                network_size, effective_year
            FROM {self._table('coverage_plans')}
            WHERE plan_id = @plan_id
            LIMIT 1
        """
        params = [bigquery.ScalarQueryParameter("plan_id", "STRING", plan_id)]
        rows = self._run_query(sql, params)
        if not rows:
            return None
        return CoveragePlan(**rows[0])

    def compare_plans(self, plan_ids: list[str]) -> list[CoveragePlan]:
        """Return full details for each plan in the list for side-by-side comparison."""
        if not plan_ids:
            return []
        sql = f"""
            SELECT
                plan_id, plan_name, tier, plan_type, monthly_premium, deductible,
                out_of_pocket_max, copay_primary, copay_specialist, covers_dental,
                covers_vision, covers_mental_health, covers_pharmacy,
                network_size, effective_year
            FROM {self._table('coverage_plans')}
            WHERE plan_id IN UNNEST(@plan_ids)
            ORDER BY monthly_premium ASC
        """
        params = [bigquery.ArrayQueryParameter("plan_ids", "STRING", plan_ids)]
        rows = self._run_query(sql, params)
        return [CoveragePlan(**r) for r in rows]

    def list_plans_by_tier(self, tier: str) -> list[CoveragePlan]:
        sql = f"""
            SELECT
                plan_id, plan_name, tier, plan_type, monthly_premium, deductible,
                out_of_pocket_max, copay_primary, copay_specialist, covers_dental,
                covers_vision, covers_mental_health, covers_pharmacy,
                network_size, effective_year
            FROM {self._table('coverage_plans')}
            WHERE tier = @tier
            ORDER BY monthly_premium ASC
        """
        params = [bigquery.ScalarQueryParameter("tier", "STRING", tier.upper())]
        rows = self._run_query(sql, params)
        return [CoveragePlan(**r) for r in rows]

"""
LangChain retrieval pipeline for InsurBot.

Architecture:
  1. A custom BigQueryRetriever pulls relevant records from BigQuery
     based on parsed intent parameters from Dialogflow CX.
  2. Retrieved records are serialized as context documents.
  3. A PromptTemplate fills the versioned qa_prompt.txt template.
  4. The chain calls VertexService.generate() and returns the response.

The chain is intentionally thin. It does not manage conversation memory -
Dialogflow CX handles session state. Each invocation is stateless.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from langchain.schema import BaseRetriever, Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun

from api.guardrails.schemas import Claim, ClaimSummary, CoveragePlan, Policy
from api.services.bigquery_service import BigQueryService
from api.services.vertex_service import VertexService

logger = structlog.get_logger(__name__)

_PROMPT_TEMPLATE = (Path(__file__).parent.parent.parent / "prompts" / "qa_prompt.txt").read_text()


# ---------------------------------------------------------------------------
# Custom BigQuery retriever
# ---------------------------------------------------------------------------

class BigQueryRetriever(BaseRetriever):
    """
    LangChain BaseRetriever backed by BigQueryService.

    The query parameter dict drives which BQ method is called.
    Supported keys:
      - policy_id       : fetch a single policy + its claim summary
      - holder_name     : search policies by holder name
      - plan_ids        : list of plan IDs for comparison
      - tier            : plan tier for listing
      - claim_type      : filter open claims by type
    """

    bq_service: Any

    model_config = {"arbitrary_types_allowed": True}

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
        **kwargs: Any,
    ) -> list[Document]:
        # query is a JSON-encoded parameter dict supplied by InsurChain
        try:
            params: dict[str, Any] = json.loads(query)
        except json.JSONDecodeError:
            logger.warning("BigQueryRetriever received non-JSON query", query=query)
            params = {}

        documents: list[Document] = []

        if policy_id := params.get("policy_id"):
            policy = self.bq_service.get_policy_by_id(policy_id)
            if policy:
                documents.append(_policy_to_doc(policy))
            summary = self.bq_service.get_claim_summary(policy_id)
            if summary:
                documents.append(_claim_summary_to_doc(summary))

        elif holder_name := params.get("holder_name"):
            policies = self.bq_service.search_policies_by_holder(holder_name)
            documents.extend(_policy_to_doc(p) for p in policies)

        if plan_ids := params.get("plan_ids"):
            plans = self.bq_service.compare_plans(plan_ids)
            documents.extend(_plan_to_doc(p) for p in plans)

        elif tier := params.get("tier"):
            plans = self.bq_service.list_plans_by_tier(tier)
            documents.extend(_plan_to_doc(p) for p in plans)

        if claim_type := params.get("claim_type"):
            claims = self.bq_service.get_open_claims_by_type(claim_type)
            documents.extend(_claim_to_doc(c) for c in claims)

        logger.info("retriever_documents_fetched", count=len(documents), params=params)
        return documents


# ---------------------------------------------------------------------------
# Document serializers
# ---------------------------------------------------------------------------

def _policy_to_doc(policy: Policy) -> Document:
    content = (
        f"Policy ID: {policy.policy_id}\n"
        f"Holder: {policy.holder_name}\n"
        f"Plan: {policy.plan_id} ({policy.plan_type})\n"
        f"Effective: {policy.effective_date} to {policy.expiry_date}\n"
        f"Monthly Premium: ${policy.premium_amount:,.2f}\n"
        f"Status: {policy.status}\n"
        f"State: {policy.state or 'N/A'}"
    )
    return Document(page_content=content, metadata={"type": "policy", "id": policy.policy_id})


def _claim_summary_to_doc(summary: ClaimSummary) -> Document:
    content = (
        f"Claims summary for Policy {summary.policy_id}:\n"
        f"  Total claims: {summary.total_claims}\n"
        f"  Open: {summary.open_claims}\n"
        f"  Approved: {summary.approved_claims}\n"
        f"  Denied: {summary.denied_claims}\n"
        f"  Total requested: ${summary.total_requested:,.2f}\n"
        f"  Total approved: ${summary.total_approved:,.2f}"
    )
    return Document(page_content=content, metadata={"type": "claim_summary", "id": summary.policy_id})


def _claim_to_doc(claim: Claim) -> Document:
    content = (
        f"Claim ID: {claim.claim_id}\n"
        f"Policy: {claim.policy_id}\n"
        f"Type: {claim.claim_type}\n"
        f"Date: {claim.claim_date}\n"
        f"Status: {claim.status}\n"
        f"Requested: ${claim.amount_requested:,.2f}\n"
        f"Approved: ${claim.amount_approved:,.2f}" if claim.amount_approved else f"Approved: N/A\n"
        f"Denial reason: {claim.denial_reason or 'N/A'}"
    )
    return Document(page_content=content, metadata={"type": "claim", "id": claim.claim_id})


def _plan_to_doc(plan: CoveragePlan) -> Document:
    content = (
        f"Plan ID: {plan.plan_id}\n"
        f"Name: {plan.plan_name}\n"
        f"Tier: {plan.tier} | Type: {plan.plan_type}\n"
        f"Monthly Premium: ${plan.monthly_premium:,.2f}\n"
        f"Deductible: ${plan.deductible:,.2f}\n"
        f"Out-of-Pocket Max: ${plan.out_of_pocket_max:,.2f}\n"
        f"Copay (Primary / Specialist): ${plan.copay_primary or 'N/A'} / ${plan.copay_specialist or 'N/A'}\n"
        f"Covers Dental: {plan.covers_dental}\n"
        f"Covers Vision: {plan.covers_vision}\n"
        f"Covers Mental Health: {plan.covers_mental_health}\n"
        f"Network Size: {plan.network_size or 'N/A'}\n"
        f"Effective Year: {plan.effective_year}"
    )
    return Document(page_content=content, metadata={"type": "coverage_plan", "id": plan.plan_id})


# ---------------------------------------------------------------------------
# Main chain
# ---------------------------------------------------------------------------

class InsurChain:
    """
    Orchestrates retrieval and generation for a single Dialogflow CX turn.

    Usage:
        chain = InsurChain(bq_service=bq, vertex_service=vertex)
        answer, context_docs = chain.run(user_question="...", params={"policy_id": "POL-..."})
    """

    def __init__(self, bq_service: BigQueryService, vertex_service: VertexService) -> None:
        self._retriever = BigQueryRetriever(bq_service=bq_service)
        self._vertex = vertex_service

    def run(
        self,
        user_question: str,
        params: dict[str, Any],
    ) -> tuple[str, list[Document]]:
        """
        Returns (answer_text, retrieved_documents).
        The caller (webhook handler) is responsible for running guardrails.
        """
        query_json = json.dumps(params)
        docs = self._retriever.invoke(query_json)

        if not docs:
            return (
                "I was unable to find any matching records in the database for your query. "
                "Please verify the policy ID or holder name and try again.",
                [],
            )

        context = "\n\n---\n\n".join(doc.page_content for doc in docs)
        prompt = _PROMPT_TEMPLATE.format(context=context, question=user_question)

        logger.info(
            "chain_generate_start",
            doc_count=len(docs),
            prompt_chars=len(prompt),
        )

        answer = self._vertex.generate(prompt)
        return answer, docs

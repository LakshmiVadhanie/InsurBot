"""
Dialogflow CX webhook fulfillment handler.

POST /webhook

Receives a WebhookRequest from Dialogflow CX, dispatches to the appropriate
InsurChain workflow based on the matched intent, applies guardrails, and
returns a WebhookResponse with the fulfillment text.

Intent routing:
  - insurance.policy.lookup     -> policy_lookup_handler
  - insurance.claims.triage     -> claims_triage_handler
  - insurance.coverage.compare  -> coverage_compare_handler

Any unrecognized intent falls through to a default response.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.config import Settings, get_settings
from api.dependencies import get_bigquery_service, get_vertex_service
from api.guardrails.prompt_guard import run_input_guards, run_output_guards
from api.guardrails.schemas import WebhookRequest, WebhookResponse
from api.services.bigquery_service import BigQueryService
from api.services.langchain_chain import InsurChain
from api.services.vertex_service import VertexService

router = APIRouter()
logger = structlog.get_logger(__name__)

_FALLBACK_RESPONSE = (
    "I was not able to generate a reliable answer for your question. "
    "Please try rephrasing or contact support."
)

_DEFAULT_RESPONSE = (
    "I can help with insurance policy lookups, claims status, and coverage comparisons. "
    "Please provide a policy ID or holder name to get started."
)


# ---------------------------------------------------------------------------
# Intent parameter extractors
# ---------------------------------------------------------------------------

def _extract_policy_params(intent_params: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if pid := intent_params.get("policy_id", {}).get("stringValue"):
        params["policy_id"] = pid
    if name := intent_params.get("holder_name", {}).get("stringValue"):
        params["holder_name"] = name
    return params


def _extract_claims_params(intent_params: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if pid := intent_params.get("policy_id", {}).get("stringValue"):
        params["policy_id"] = pid
    if ctype := intent_params.get("claim_type", {}).get("stringValue"):
        params["claim_type"] = ctype
    return params


def _extract_coverage_params(intent_params: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if raw_ids := intent_params.get("plan_ids", {}).get("listValue", {}).get("values", []):
        params["plan_ids"] = [v.get("stringValue") for v in raw_ids if v.get("stringValue")]
    if tier := intent_params.get("tier", {}).get("stringValue"):
        params["tier"] = tier
    return params


# ---------------------------------------------------------------------------
# Fulfillment handler
# ---------------------------------------------------------------------------

@router.post("", response_model=None)
async def fulfillment(
    raw_request: Request,
    bq_service: BigQueryService = Depends(get_bigquery_service),
    vertex_service: VertexService = Depends(get_vertex_service),
    settings: Settings = Depends(get_settings),
) -> WebhookResponse:
    """
    Main Dialogflow CX webhook endpoint.
    Parses the request, dispatches by intent, runs guardrails, returns response.
    """
    try:
        body = await raw_request.json()
        webhook_req = WebhookRequest(**body)
    except Exception as exc:
        logger.error("webhook_parse_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Dialogflow CX webhook payload: {exc}",
        ) from exc

    user_text = webhook_req.text or ""
    intent_name = webhook_req.intent_info.display_name
    intent_params = webhook_req.intent_info.parameters
    session = webhook_req.session_info.session

    log = logger.bind(session=session, intent=intent_name)
    log.info("webhook_request_received")

    # Input guardrails
    input_check = run_input_guards(user_text)
    if not input_check.passed:
        log.warning("input_guard_blocked", reason=input_check.reason)
        return WebhookResponse.from_text(input_check.reason or _FALLBACK_RESPONSE)

    # Intent routing
    chain = InsurChain(bq_service=bq_service, vertex_service=vertex_service)

    if "policy.lookup" in intent_name:
        params = _extract_policy_params(intent_params)
    elif "claims.triage" in intent_name:
        params = _extract_claims_params(intent_params)
    elif "coverage.compare" in intent_name:
        params = _extract_coverage_params(intent_params)
    else:
        log.info("webhook_unrecognized_intent")
        return WebhookResponse.from_text(_DEFAULT_RESPONSE)

    if not params:
        return WebhookResponse.from_text(
            "I need more information to answer that. "
            "Could you provide a policy ID or holder name?"
        )

    # Retrieval + generation
    try:
        answer, docs = chain.run(user_question=user_text, params=params)
    except Exception as exc:
        log.error("chain_execution_error", error=str(exc))
        return WebhookResponse.from_text(_FALLBACK_RESPONSE)

    # Output guardrails
    output_check = run_output_guards(
        answer=answer,
        context_docs=docs,
        max_chars=settings.guardrail_max_response_chars,
    )
    if not output_check.passed:
        log.warning(
            "output_guard_blocked",
            reason=output_check.reason,
            blocked_by=output_check.blocked_by,
        )
        return WebhookResponse.from_text(_FALLBACK_RESPONSE)

    log.info("webhook_response_sent", response_chars=len(answer))
    return WebhookResponse.from_text(answer)

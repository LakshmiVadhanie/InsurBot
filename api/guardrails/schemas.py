"""
Pydantic models for all Dialogflow CX webhook request/response payloads
and for typed BigQuery query results.

These are the single source of truth for data shapes across the API.
"""

from __future__ import annotations

import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class PlanType(str, Enum):
    HMO = "HMO"
    PPO = "PPO"
    EPO = "EPO"
    HDHP = "HDHP"


class PlanTier(str, Enum):
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class PolicyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    LAPSED = "LAPSED"
    CANCELLED = "CANCELLED"
    PENDING = "PENDING"


class ClaimStatus(str, Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CLOSED = "CLOSED"


class ClaimType(str, Enum):
    MEDICAL = "MEDICAL"
    DENTAL = "DENTAL"
    VISION = "VISION"
    PHARMACY = "PHARMACY"
    MENTAL_HEALTH = "MENTAL_HEALTH"


# ---------------------------------------------------------------------------
# BigQuery result models
# ---------------------------------------------------------------------------

class Policy(BaseModel):
    policy_id: str
    holder_name: str
    holder_email: str | None = None
    plan_id: str
    plan_type: PlanType
    effective_date: datetime.date
    expiry_date: datetime.date
    premium_amount: float
    status: PolicyStatus
    state: str | None = None


class Claim(BaseModel):
    claim_id: str
    policy_id: str
    claim_date: datetime.date
    claim_type: ClaimType
    status: ClaimStatus
    amount_requested: float
    amount_approved: float | None = None
    denial_reason: str | None = None
    adjuster_id: str | None = None
    resolved_date: datetime.date | None = None


class CoveragePlan(BaseModel):
    plan_id: str
    plan_name: str
    tier: PlanTier
    plan_type: PlanType
    monthly_premium: float
    deductible: float
    out_of_pocket_max: float
    copay_primary: float | None = None
    copay_specialist: float | None = None
    covers_dental: bool
    covers_vision: bool
    covers_mental_health: bool
    covers_pharmacy: bool
    network_size: str | None = None
    effective_year: int


class ClaimSummary(BaseModel):
    policy_id: str
    total_claims: int
    open_claims: int
    approved_claims: int
    denied_claims: int
    total_requested: float
    total_approved: float


# ---------------------------------------------------------------------------
# Dialogflow CX webhook models
# ---------------------------------------------------------------------------

class IntentInfo(BaseModel):
    last_matched_intent: str = Field(alias="lastMatchedIntent")
    display_name: str = Field(alias="displayName")
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0

    model_config = {"populate_by_name": True}


class SessionInfo(BaseModel):
    session: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class WebhookRequest(BaseModel):
    detect_intent_response_id: str = Field(alias="detectIntentResponseId")
    intent_info: IntentInfo = Field(alias="intentInfo")
    session_info: SessionInfo = Field(alias="sessionInfo")
    text: str | None = None
    language_code: str = Field(alias="languageCode", default="en")
    page_info: dict[str, Any] = Field(alias="pageInfo", default_factory=dict)

    model_config = {"populate_by_name": True}


class FulfillmentMessage(BaseModel):
    text: dict[str, list[str]]


class WebhookResponse(BaseModel):
    fulfillment_response: dict[str, Any] = Field(alias="fulfillmentResponse")
    session_info: dict[str, Any] | None = Field(alias="sessionInfo", default=None)

    model_config = {"populate_by_name": True}

    @classmethod
    def from_text(cls, text: str, session_params: dict[str, Any] | None = None) -> WebhookResponse:
        body: dict[str, Any] = {
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [text]}}]
            }
        }
        if session_params:
            body["sessionInfo"] = {"parameters": session_params}
        return cls(**body)


# ---------------------------------------------------------------------------
# Guardrail models
# ---------------------------------------------------------------------------

class GuardrailResult(BaseModel):
    passed: bool
    reason: str | None = None
    blocked_by: str | None = None

"""
Prompt-level guardrails for InsurBot.

Three guard classes run in sequence before each LLM response is returned:

  InputGuard   - validates the raw user message before retrieval and generation
  OutputGuard  - validates the generated answer before it is sent to Dialogflow
  PolicyGuard  - ensures cited figures exist in the retrieved context

Each guard returns a GuardrailResult. If passed=False, the webhook handler
returns a safe fallback message instead of the degraded LLM output.

Guards are intentionally pure functions with no I/O side effects so they
can be unit-tested without mocking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from langchain.schema import Document

from api.guardrails.schemas import GuardrailResult

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Compiled regex patterns
# ---------------------------------------------------------------------------

# SSN patterns: 123-45-6789 or 123456789
_SSN_PATTERN = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")

# Credit/debit card: 13-19 consecutive digits
_CARD_PATTERN = re.compile(r"\b\d{13,19}\b")

# Jailbreak signal phrases (kept minimal - extend as needed)
_JAILBREAK_PATTERNS = [
    re.compile(r"ignore\s+(previous|all|prior)\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"(pretend|act)\s+(you\s+are|as\s+if)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"DAN\b", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
]

# Dollar amount pattern for PolicyGuard cross-check
_DOLLAR_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?")


# ---------------------------------------------------------------------------
# Guard implementations
# ---------------------------------------------------------------------------

@dataclass
class InputGuard:
    """
    Validates the raw user input before it reaches retrieval or the LLM.

    Blocks:
    - SSN or credit card numbers in the query (PII)
    - Prompt injection / jailbreak attempts
    """

    def check(self, user_input: str) -> GuardrailResult:
        if _SSN_PATTERN.search(user_input):
            logger.warning("input_guard_blocked_ssn")
            return GuardrailResult(
                passed=False,
                reason="Input contains what appears to be a Social Security Number. Please remove sensitive personal identifiers.",
                blocked_by="InputGuard.SSN",
            )

        if _CARD_PATTERN.search(user_input):
            logger.warning("input_guard_blocked_card_number")
            return GuardrailResult(
                passed=False,
                reason="Input contains what appears to be a payment card number. Please do not include sensitive financial data.",
                blocked_by="InputGuard.CardNumber",
            )

        for pattern in _JAILBREAK_PATTERNS:
            if pattern.search(user_input):
                logger.warning("input_guard_blocked_jailbreak", pattern=pattern.pattern)
                return GuardrailResult(
                    passed=False,
                    reason="Your request could not be processed. Please ask about insurance policies, claims, or coverage.",
                    blocked_by="InputGuard.Jailbreak",
                )

        return GuardrailResult(passed=True)


@dataclass
class OutputGuard:
    """
    Validates the generated answer before it is returned to the user.

    Checks:
    - Minimum length (too short = likely a non-answer)
    - Maximum length (prevent runaway outputs)
    - Absence of internal system markers that should never surface
    """

    min_chars: int = 20
    max_chars: int = 2000

    def check(self, answer: str) -> GuardrailResult:
        stripped = answer.strip()

        if len(stripped) < self.min_chars:
            logger.warning("output_guard_too_short", length=len(stripped))
            return GuardrailResult(
                passed=False,
                reason="The generated response was too short to be useful.",
                blocked_by="OutputGuard.TooShort",
            )

        if len(stripped) > self.max_chars:
            logger.warning("output_guard_too_long", length=len(stripped))
            return GuardrailResult(
                passed=False,
                reason="The generated response exceeded the allowed length.",
                blocked_by="OutputGuard.TooLong",
            )

        # Surface leak: LLM should never repeat system-level markers
        if "qa_prompt" in stripped or "Rules:" in stripped:
            logger.warning("output_guard_prompt_leak_detected")
            return GuardrailResult(
                passed=False,
                reason="Response contained internal system content and was blocked.",
                blocked_by="OutputGuard.PromptLeak",
            )

        return GuardrailResult(passed=True)


@dataclass
class PolicyGuard:
    """
    Cross-checks that dollar amounts cited in the LLM answer exist
    in the retrieved context documents.

    This guards against hallucinated financial figures - the most
    consequential class of error for an insurance assistant.
    """

    def check(self, answer: str, context_docs: list[Document]) -> GuardrailResult:
        cited_amounts = set(_DOLLAR_PATTERN.findall(answer))
        if not cited_amounts:
            # No dollar amounts cited - nothing to verify
            return GuardrailResult(passed=True)

        context_text = "\n".join(doc.page_content for doc in context_docs)
        context_amounts = set(_DOLLAR_PATTERN.findall(context_text))

        hallucinated = cited_amounts - context_amounts
        if hallucinated:
            logger.warning(
                "policy_guard_hallucinated_amounts",
                hallucinated=sorted(hallucinated),
                context_amounts=sorted(context_amounts),
            )
            return GuardrailResult(
                passed=False,
                reason=(
                    f"Response cited financial figures not found in the source data: "
                    f"{', '.join(sorted(hallucinated))}."
                ),
                blocked_by="PolicyGuard.HallucinatedAmount",
            )

        return GuardrailResult(passed=True)


# ---------------------------------------------------------------------------
# Convenience runner
# ---------------------------------------------------------------------------

def run_input_guards(user_input: str) -> GuardrailResult:
    return InputGuard().check(user_input)


def run_output_guards(
    answer: str,
    context_docs: list[Document],
    max_chars: int = 2000,
) -> GuardrailResult:
    output_result = OutputGuard(max_chars=max_chars).check(answer)
    if not output_result.passed:
        return output_result
    return PolicyGuard().check(answer, context_docs)

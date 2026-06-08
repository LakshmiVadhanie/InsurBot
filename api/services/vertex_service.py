"""
Vertex AI GenerativeModel wrapper.

Wraps vertexai.generative_models.GenerativeModel to provide:
  - Synchronous and async generation
  - Structured error handling with retries
  - A ping() method for readiness checks
"""

from __future__ import annotations

import structlog
import vertexai
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential
from vertexai.generative_models import (
    GenerationConfig,
    GenerativeModel,
    HarmBlockThreshold,
    HarmCategory,
    SafetySetting,
)

logger = structlog.get_logger(__name__)

_SAFETY_SETTINGS = [
    SafetySetting(category=HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
    SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE),
]


class VertexService:
    """Thin wrapper around Vertex AI GenerativeModel."""

    _project: str
    _region: str
    _model_id: str
    _temperature: float
    _max_output_tokens: int
    _model: GenerativeModel
    _generation_config: GenerationConfig

    def __init__(
        self,
        project_id: str,
        region: str,
        model_id: str,
        temperature: float,
        max_output_tokens: int,
    ) -> None:
        self._project = project_id
        self._region = region
        self._model_id = model_id
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

        vertexai.init(project=project_id, location=region)
        self._model = GenerativeModel(model_id)
        self._generation_config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            candidate_count=1,
        )

    def ping(self) -> None:
        """Smoke-test the Vertex AI endpoint. Raises on failure."""
        response = self._model.generate_content(
            "Reply with only the word 'ok'.",
            generation_config=GenerationConfig(max_output_tokens=4, temperature=0),
            safety_settings=_SAFETY_SETTINGS,
        )
        if not response.text:
            raise RuntimeError("Vertex AI ping returned empty response")

    @retry(
        retry=retry_if_not_exception_type(ValueError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
    )
    def generate(self, prompt: str) -> str:
        """
        Send a prompt and return the generated text.
        Raises on blocked safety responses or empty output.
        """
        logger.debug("vertex_generate_start", model=self._model_id)
        response = self._model.generate_content(
            prompt,
            generation_config=self._generation_config,
            safety_settings=_SAFETY_SETTINGS,
        )
        if not response.candidates:
            raise RuntimeError("Vertex AI returned no candidates")

        candidate = response.candidates[0]

        # Surface finish reason for observability
        finish_reason = candidate.finish_reason.name if candidate.finish_reason else "UNKNOWN"
        logger.info("vertex_generate_done", finish_reason=finish_reason, model=self._model_id)

        if finish_reason in ("SAFETY", "RECITATION"):
            raise ValueError(f"Response blocked by Vertex AI safety filter: {finish_reason}")

        text = response.text.strip()
        if not text:
            raise RuntimeError("Vertex AI returned empty text")

        return str(text)

    @property
    def model_id(self) -> str:
        return self._model_id

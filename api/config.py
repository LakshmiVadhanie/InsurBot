"""
Application configuration loaded from environment variables.
Pydantic-settings validates and coerces all values at startup.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # GCP
    gcp_project_id: str = Field("your-gcp-project", description="GCP project ID")
    gcp_region: str = Field("us-central1", description="Default GCP region")

    # BigQuery
    bq_dataset: str = Field("insurbot", description="BigQuery dataset name")
    bq_location: str = Field("US", description="BigQuery job location")

    # Vertex AI
    vertex_model_id: str = Field("gemini-1.5-pro", description="Vertex AI generative model ID")
    vertex_temperature: float = Field(0.2, ge=0.0, le=1.0)
    vertex_max_output_tokens: int = Field(1024, ge=128, le=8192)

    # Guardrails
    guardrail_min_confidence: float = Field(0.75, ge=0.0, le=1.0)
    guardrail_max_response_chars: int = Field(2000, ge=100)

    # FastAPI
    api_host: str = Field("0.0.0.0")
    api_port: int = Field(8080, ge=1, le=65535)
    log_level: str = Field("INFO")

    # Dialogflow CX
    dialogflow_agent_id: str = Field("your-dialogflow-agent-id", description="Dialogflow CX agent resource ID")
    dialogflow_location: str = Field("global")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings

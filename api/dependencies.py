"""
FastAPI dependency providers.
These are injected via Depends() throughout the router layer,
keeping service construction out of route handlers.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from api.config import Settings, get_settings
from api.services.bigquery_service import BigQueryService
from api.services.vertex_service import VertexService


@lru_cache(maxsize=1)
def _bigquery_service(project_id: str, dataset: str, location: str) -> BigQueryService:
    return BigQueryService(project_id=project_id, dataset=dataset, location=location)


@lru_cache(maxsize=1)
def _vertex_service(
    project_id: str,
    region: str,
    model_id: str,
    temperature: float,
    max_output_tokens: int,
) -> VertexService:
    return VertexService(
        project_id=project_id,
        region=region,
        model_id=model_id,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )


def get_bigquery_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> BigQueryService:
    return _bigquery_service(
        project_id=settings.gcp_project_id,
        dataset=settings.bq_dataset,
        location=settings.bq_location,
    )


def get_vertex_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> VertexService:
    return _vertex_service(
        project_id=settings.gcp_project_id,
        region=settings.gcp_region,
        model_id=settings.vertex_model_id,
        temperature=settings.vertex_temperature,
        max_output_tokens=settings.vertex_max_output_tokens,
    )

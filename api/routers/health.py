"""
Health and readiness endpoints.

/health  - liveness probe (always 200 if process is alive)
/readiness - readiness probe (checks downstream dependencies)
"""

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from api.dependencies import get_bigquery_service, get_vertex_service
from api.services.bigquery_service import BigQueryService
from api.services.vertex_service import VertexService

router = APIRouter()
logger = structlog.get_logger(__name__)


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    """Liveness probe. Returns 200 as long as the process is running."""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(
    bq_service: BigQueryService = Depends(get_bigquery_service),
    vertex_service: VertexService = Depends(get_vertex_service),
) -> JSONResponse:
    """
    Readiness probe. Validates that BigQuery and Vertex AI are reachable.
    Returns 200 if all checks pass, 503 otherwise.
    """
    checks: dict[str, str] = {}
    overall_ok = True

    try:
        bq_service.ping()
        checks["bigquery"] = "ok"
    except Exception as exc:
        logger.warning("BigQuery readiness check failed", error=str(exc))
        checks["bigquery"] = "unavailable"
        overall_ok = False

    try:
        vertex_service.ping()
        checks["vertex_ai"] = "ok"
    except Exception as exc:
        logger.warning("Vertex AI readiness check failed", error=str(exc))
        checks["vertex_ai"] = "unavailable"
        overall_ok = False

    code = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content={"status": "ready" if overall_ok else "degraded", "checks": checks}, status_code=code)

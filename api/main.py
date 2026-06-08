"""
FastAPI application entry point.
Registers routers, configures structured logging, and sets lifespan hooks.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers import health, webhook


def _configure_logging(log_level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _configure_logging(settings.log_level)
    logger = structlog.get_logger(__name__)
    logger.info(
        "InsurBot API starting",
        project=settings.gcp_project_id,
        region=settings.gcp_region,
        model=settings.vertex_model_id,
    )
    yield
    logger.info("InsurBot API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="InsurBot API",
        description=(
            "Conversational AI webhook service for insurance policy queries. "
            "Integrates Dialogflow CX fulfillment with Vertex AI and BigQuery."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization"],
    )

    app.include_router(health.router, tags=["observability"])
    app.include_router(webhook.router, prefix="/webhook", tags=["dialogflow"])

    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )

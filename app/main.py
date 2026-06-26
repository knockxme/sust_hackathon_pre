"""
QueueStorm Investigator — FastAPI Application Entry Point

Endpoints:
  GET  /health         → {"status": "ok"}
  POST /analyze-ticket → Structured ticket analysis
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Load .env file if present (for local development)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models import (
    AnalyzeTicketRequest,
    AnalyzeTicketResponse,
    HealthResponse,
    ErrorResponse,
)
from app.analyzer import analyze_ticket


# ─── Logging Setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── App Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("QueueStorm Investigator starting up...")
    # Validate required env vars on startup
    if not os.getenv("GROQ_API_KEY"):
        logger.warning(
            "GROQ_API_KEY is not set! The /analyze-ticket endpoint will not work."
        )
    logger.info("Service ready.")
    yield
    logger.info("QueueStorm Investigator shutting down.")


# ─── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="QueueStorm Investigator",
    description=(
        "AI-powered support ticket analysis copilot for digital finance platforms. "
        "Analyzes customer complaints, matches transaction evidence, classifies cases, "
        "routes to the correct department, and drafts safe customer replies."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─── Middleware: Request Timing ────────────────────────────────────────────────

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.1f}"
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        process_time,
    )
    return response


# ─── Exception Handlers ────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 400 for malformed/missing required fields."""
    errors = exc.errors()
    detail_parts = []
    for err in errors:
        loc = " → ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "invalid")
        detail_parts.append(f"{loc}: {msg}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Invalid request", "detail": "; ".join(detail_parts)},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_handler(request: Request, exc: ValidationError):
    """Return 422 for schema-valid but semantically invalid input."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "Semantic validation error", "detail": str(exc)},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Return 500 for unexpected errors. Never expose internals."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error"},
    )


# ─── Endpoints ─────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns OK immediately. Must respond within 60 seconds of service start.",
    tags=["System"],
)
async def health_check():
    """Liveness probe — returns {\"status\": \"ok\"}."""
    return HealthResponse(status="ok")


@app.post(
    "/analyze-ticket",
    response_model=AnalyzeTicketResponse,
    summary="Analyze a support ticket",
    description=(
        "Accepts a customer support ticket with complaint text and optional transaction history. "
        "Returns structured analysis: case type, severity, routing department, evidence verdict, "
        "agent summary, recommended next action, and a safe customer reply. "
        "Supports English, Bangla, and mixed Banglish complaints."
    ),
    responses={
        200: {"description": "Successful analysis"},
        400: {"model": ErrorResponse, "description": "Malformed input (invalid JSON, missing required fields)"},
        422: {"model": ErrorResponse, "description": "Schema valid but semantically invalid"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
    tags=["Analysis"],
)
async def analyze_ticket_endpoint(request: AnalyzeTicketRequest):
    """
    Main analysis endpoint.

    Required fields: ticket_id, complaint
    Optional: language, channel, user_type, campaign_context, transaction_history, metadata

    Must respond within 30 seconds.
    """
    logger.info("Received ticket: %s (lang=%s, channel=%s)", request.ticket_id, request.language, request.channel)

    try:
        result = await analyze_ticket(request)
        return result
    except Exception as e:
        # Catch-all: log privately, return generic 500
        logger.error("analyze_ticket failed for ticket %s: %s", request.ticket_id, e, exc_info=True)
        raise  # Will be caught by generic_exception_handler

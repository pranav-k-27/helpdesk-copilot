"""
GenAI Helpdesk Copilot — Main Application Entry Point
"""
import time
import uuid
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from api.routes import router

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(
    title="GenAI Helpdesk Copilot",
    description="Conversational AI for helpdesk insights using NLQ + RAG",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request ID + Latency Middleware ───────────────────────────
@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    request.state.request_id = request_id

    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled error [{request_id}]: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    latency_ms = round((time.time() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Latency-MS"] = str(latency_ms)
    logger.info(f"{request.method} {request.url.path} | {response.status_code} | {latency_ms}ms")
    return response

# ── Routes ────────────────────────────────────────────────────
app.include_router(router, prefix="/api/v1")

# ── Health check (root level) ─────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    return {
        "status":  "healthy",
        "service": "helpdesk-copilot",
        "version": "1.0.0",
        "env":     settings.ENV,
    }

# ── Startup event ─────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    import os
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    logger.info("=" * 50)
    logger.info("  GenAI Helpdesk Copilot — Starting up")
    logger.info(f"  ENV:   {settings.ENV}")
    logger.info(f"  Model: {settings.OPENAI_MODEL}")
    logger.info(f"  Docs:  http://localhost:{settings.BACKEND_PORT}/docs")
    logger.info("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Helpdesk Copilot — Shutting down")

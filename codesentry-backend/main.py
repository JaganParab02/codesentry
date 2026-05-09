"""
CodeSentry Backend — FastAPI application entry point.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

from api.routes import router
from privacy.privacy_guard import ZDRMiddleware

# ──────────────────────────────────────────
# Logging
# ──────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("codesentry")


# ──────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("=" * 60)
    logger.info("  CodeSentry Backend starting up")
    logger.info("  vLLM endpoint: %s", os.getenv("VLLM_BASE_URL", "http://localhost:8080"))
    logger.info("  Model: %s", os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct"))
    logger.info("  Zero Data Retention: ENABLED")
    logger.info("=" * 60)

    # Pre-warm orchestrator (initialises agents without LLM calls)
    from api.routes import get_orchestrator
    get_orchestrator()
    logger.info("Orchestrator initialised.")

    yield

    logger.info("CodeSentry Backend shutting down.")


# ──────────────────────────────────────────
# App factory
# ──────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="CodeSentry Backend",
        description=(
            "AI/ML Code Security Analysis Engine — "
            "OWASP + OWASP LLM Top-10 scanning powered by Qwen2.5-Coder-32B on AMD MI300X. "
            "Zero Data Retention: all inference runs on localhost."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ────────────────────────────────
    allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── ZDR Middleware ───────────────────────
    app.add_middleware(ZDRMiddleware)

    # ── Routes ──────────────────────────────
    app.include_router(router, prefix="/api")

    # ── Root ────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse({
            "service": "CodeSentry Backend",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs",
            "health": "/api/health",
        })

    # ── Global exception handler ─────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "error": str(exc)},
        )

    return app


app = create_app()

# ──────────────────────────────────────────
# Dev runner
# ──────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
        log_level="info",
    )

"""
FastAPI route definitions for CodeSentry Backend.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from agents.orchestrator import Orchestrator
from api.models import AnalyzeRequest, HealthResponse, PrivacyCertificate, AMDMetricsSnapshot
from amd_metrics import AMDMetricsCollector
from memory.session_store import get_store

logger = logging.getLogger(__name__)
router = APIRouter()

VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8080")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct")

# Shared orchestrator instance (lazily initialised)
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


# Shared AMD metrics collector for the health endpoint
_amd_collector: AMDMetricsCollector | None = None

def get_amd_collector() -> AMDMetricsCollector:
    global _amd_collector
    if _amd_collector is None:
        _amd_collector = AMDMetricsCollector()
    return _amd_collector


# ──────────────────────────────────────────
# Health
# ──────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """
    Returns vLLM readiness and available GPU memory.
    Works even if vLLM is not running (vllm_ready=false).
    """
    vllm_ready = False
    gpu_memory_free_gb: float | None = None

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{VLLM_BASE_URL}/health")
            vllm_ready = resp.status_code == 200
    except Exception:
        vllm_ready = False

    # Try to get GPU memory stats via vLLM models endpoint
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{VLLM_BASE_URL}/v1/models")
            if resp.status_code == 200:
                vllm_ready = True
    except Exception:
        pass

    # Attempt to read GPU memory from system (Linux / ROCm)
    try:
        import subprocess
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Parse first GPU's free VRAM
            for card_data in data.values():
                if isinstance(card_data, dict):
                    free_bytes = card_data.get("VRAM Total Memory (B)", 0)
                    used_bytes = card_data.get("VRAM Total Used Memory (B)", 0)
                    gpu_memory_free_gb = round((free_bytes - used_bytes) / (1024 ** 3), 1)
                    break
    except Exception:
        # On non-AMD or non-Linux systems, skip GPU stats
        try:
            import torch
            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                gpu_memory_free_gb = round(free / (1024 ** 3), 1)
        except Exception:
            pass

    # Try to get AMD GPU metrics
    amd_hw = None
    try:
        collector = get_amd_collector()
        metrics = await collector.collect()
        amd_hw = AMDMetricsSnapshot(**metrics)
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        model=MODEL_NAME,
        vllm_ready=vllm_ready,
        gpu_memory_free_gb=gpu_memory_free_gb,
        vllm_endpoint=VLLM_BASE_URL,
        amd_hardware=amd_hw,
    )


# ──────────────────────────────────────────
# Main analysis endpoint (SSE streaming)
# ──────────────────────────────────────────

@router.post("/scan", tags=["Analysis"])
async def create_scan(request: AnalyzeRequest) -> JSONResponse:
    """Create a new scan session."""
    store = get_store()
    await store.create(request.session_id, {
        "source": request.source,
        "source_type": request.source_type.value
    })
    return JSONResponse(content={"scanId": request.session_id})

@router.get("/scan/stream/{scan_id}", tags=["Analysis"])
async def scan_stream(scan_id: str) -> EventSourceResponse:
    """Stream the analysis results using SSE."""
    store = get_store()
    session = await store.get(scan_id)
    if not session:
        raise HTTPException(status_code=404, detail="Scan session not found")

    orchestrator = get_orchestrator()
    source = session.get("source")
    source_type = session.get("source_type")

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            async for event in orchestrator.run_stream(
                source=source,
                source_type=source_type,
                session_id=scan_id,
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], default=str),
                }
        except Exception as exc:
            logger.error("[Routes] Unhandled error in analysis stream: %s", exc, exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"message": str(exc)}),
            }

    return EventSourceResponse(event_generator())


# ──────────────────────────────────────────
# Demo endpoint (no GPU required)
# ──────────────────────────────────────────

@router.post("/analyze/demo", tags=["Analysis"])
async def analyze_demo() -> JSONResponse:
    """
    Returns a pre-computed analysis result using the vulnerable_ml_code fixture.
    No vLLM / GPU required — safe for CI and frontend development.
    """
    orchestrator = get_orchestrator()
    try:
        result = await orchestrator.run_demo(session_id="demo-session")
        return JSONResponse(content=result.model_dump(mode="json"))
    except Exception as exc:
        logger.error("[Routes] Demo endpoint error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ──────────────────────────────────────────
# Session retrieval
# ──────────────────────────────────────────

@router.get("/session/{session_id}", tags=["Session"])
async def get_session(session_id: str) -> JSONResponse:
    """
    Retrieve the full analysis result for a completed session.
    Returns 404 if session not found or expired.
    """
    store = get_store()
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found or expired.")

    result = session.get("result")
    if result is None:
        return JSONResponse(content={"session_id": session_id, "status": session.get("_status", "pending")})

    return JSONResponse(content=result)


# ──────────────────────────────────────────
# Privacy certificate
# ──────────────────────────────────────────

@router.get("/privacy-certificate/{session_id}", tags=["Privacy"])
async def get_privacy_certificate(session_id: str) -> JSONResponse:
    """
    Return the Zero Data Retention audit certificate for a completed session.
    """
    store = get_store()
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    result = session.get("result", {})
    cert = result.get("privacy_certificate")
    if cert is None:
        raise HTTPException(status_code=404, detail="Privacy certificate not yet generated for this session.")

    return JSONResponse(content=cert)


# ──────────────────────────────────────────
# Session list (debug / admin)
# ──────────────────────────────────────────

@router.get("/sessions", tags=["Session"], include_in_schema=False)
async def list_sessions() -> JSONResponse:
    """List all active session IDs (debug endpoint)."""
    store = get_store()
    sessions = await store.list_sessions()
    count = await store.count()
    return JSONResponse(content={"active_sessions": sessions, "count": count})

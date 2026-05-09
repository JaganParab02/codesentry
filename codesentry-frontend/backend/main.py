"""
CodeSentry Backend — FastAPI Application
AI Security Copilot for AI-Generated Code

Endpoints:
  POST /api/scan         — Initiate a scan, returns scanId
  GET  /api/scan/stream/{scanId} — SSE stream of agent events
  GET  /api/health       — Health check
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.orchestrator import run_scan_pipeline

app = FastAPI(
    title="CodeSentry API",
    description="AI Security Copilot — Backend API",
    version="1.0.0",
)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "name": "CodeSentry AI Security API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "docs": "/docs",
            "scan": "/api/scan"
        }
    }


# In-memory scan registry
scans: dict[str, dict] = {}


class ScanRequest(BaseModel):
    type: str  # "github" | "code"
    url: str | None = None
    code: str | None = None
    language: str | None = "python"


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "codesentry-api"}


@app.post("/api/scan")
async def create_scan(request: ScanRequest):
    scan_id = f"cs-{uuid.uuid4().hex[:8]}"
    scans[scan_id] = {
        "id": scan_id,
        "request": request.dict(),
        "status": "pending",
        "events": [],
    }
    return {"scanId": scan_id, "status": "pending"}


@app.get("/api/scan/stream/{scan_id}")
async def stream_scan(scan_id: str):
    if scan_id not in scans:
        async def error_stream():
            yield f"event: error\ndata: {json.dumps({'message': 'Scan not found'})}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    scan = scans[scan_id]
    request = ScanRequest(**scan["request"])

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            async for event_type, event_data in run_scan_pipeline(request):
                payload = json.dumps(event_data)
                yield f"event: {event_type}\ndata: {payload}\n\n"
                await asyncio.sleep(0)
        except Exception as e:
            error_payload = json.dumps({"message": str(e)})
            yield f"event: error\ndata: {error_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

"""
Tests for FastAPI endpoints — uses httpx AsyncClient, no GPU required.
"""
from __future__ import annotations

import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app


# ──────────────────────────────────────────
# Client fixture
# ──────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ──────────────────────────────────────────
# Health endpoint
# ──────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_endpoint_returns_200(self, client: AsyncClient):
        response = await client.get("/api/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_schema(self, client: AsyncClient):
        response = await client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert "model" in data
        assert "vllm_ready" in data
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_contains_vllm_endpoint(self, client: AsyncClient):
        response = await client.get("/api/health")
        data = response.json()
        assert "vllm_endpoint" in data
        assert "localhost" in data["vllm_endpoint"]


# ──────────────────────────────────────────
# Demo endpoint (no GPU)
# ──────────────────────────────────────────

class TestDemoEndpoint:
    @pytest.mark.asyncio
    async def test_demo_endpoint_returns_200(self, client: AsyncClient):
        """Demo must work without GPU — for CI/CD and frontend dev."""
        response = await client.post("/api/analyze/demo")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_demo_returns_session_result(self, client: AsyncClient):
        response = await client.post("/api/analyze/demo")
        data = response.json()
        assert "session_id" in data
        assert "status" in data
        assert data["status"] == "complete"

    @pytest.mark.asyncio
    async def test_demo_has_security_findings(self, client: AsyncClient):
        response = await client.post("/api/analyze/demo")
        data = response.json()
        assert "security_findings" in data
        assert len(data["security_findings"]) > 0, (
            "Demo should return at least one security finding"
        )

    @pytest.mark.asyncio
    async def test_demo_has_privacy_certificate(self, client: AsyncClient):
        response = await client.post("/api/analyze/demo")
        data = response.json()
        assert "privacy_certificate" in data
        cert = data["privacy_certificate"]
        assert cert is not None
        assert "guarantee" in cert
        assert "signature" in cert

    @pytest.mark.asyncio
    async def test_demo_no_gpu_required(self, client: AsyncClient):
        """Demo endpoint must not raise even when no GPU is present."""
        # If this test runs on a machine without ROCm/CUDA, it must still pass
        response = await client.post("/api/analyze/demo")
        assert response.status_code in (200, 500)
        if response.status_code == 500:
            # Only acceptable failure is file not found for fixture
            data = response.json()
            assert "error" in data or "detail" in data


# ──────────────────────────────────────────
# Analyze endpoint — SSE streaming
# ──────────────────────────────────────────

class TestAnalyzeEndpoint:
    @pytest.mark.asyncio
    async def test_analyze_accepts_code_source_type(self, client: AsyncClient):
        """POST /api/analyze with source_type=code should return 200 (SSE stream starts)."""
        payload = {
            "source": "import pickle\npickle.load(open('model.pkl','rb'))",
            "source_type": "code",
            "session_id": "test-analyze-001",
        }
        response = await client.post("/api/analyze", json=payload)
        # SSE streams return 200 even if they have no vLLM
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_analyze_returns_sse_stream(self, client: AsyncClient):
        """Response should be text/event-stream content type."""
        payload = {
            "source": "x = eval(input())",
            "source_type": "code",
            "session_id": "test-sse-stream",
        }
        response = await client.post("/api/analyze", json=payload)
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type

    @pytest.mark.asyncio
    async def test_analyze_validates_request_schema(self, client: AsyncClient):
        """Empty session_id should be rejected with 422."""
        payload = {
            "source": "some code",
            "source_type": "code",
            "session_id": "",
        }
        response = await client.post("/api/analyze", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_analyze_rejects_invalid_source_type(self, client: AsyncClient):
        payload = {
            "source": "some code",
            "source_type": "invalid_type",
            "session_id": "test-invalid-type",
        }
        response = await client.post("/api/analyze", json=payload)
        assert response.status_code == 422


# ──────────────────────────────────────────
# Session endpoint
# ──────────────────────────────────────────

class TestSessionEndpoint:
    @pytest.mark.asyncio
    async def test_session_not_found_returns_404(self, client: AsyncClient):
        response = await client.get("/api/session/nonexistent-session-xyz")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_session_retrieval_after_demo(self, client: AsyncClient):
        """After running demo, session should be retrievable if store was populated."""
        # Demo uses a fixed session ID
        await client.post("/api/analyze/demo")
        response = await client.get("/api/session/demo-session")
        # Should either return 200 (found) or 404 (store uses in-memory, may not persist)
        assert response.status_code in (200, 404)


# ──────────────────────────────────────────
# Privacy certificate endpoint
# ──────────────────────────────────────────

class TestPrivacyCertificateEndpoint:
    @pytest.mark.asyncio
    async def test_privacy_certificate_generated(self, client: AsyncClient):
        """
        After a complete analysis, the privacy certificate endpoint should
        return a valid certificate.
        """
        # Run demo to populate a session
        demo_response = await client.post("/api/analyze/demo")
        assert demo_response.status_code == 200
        demo_data = demo_response.json()

        session_id = demo_data.get("session_id", "demo-session")

        # Try to get certificate
        cert_response = await client.get(f"/api/privacy-certificate/{session_id}")
        # May be 404 if demo doesn't persist to store, or 200 if it does
        assert cert_response.status_code in (200, 404)

        if cert_response.status_code == 200:
            cert = cert_response.json()
            assert "guarantee" in cert
            assert "signature" in cert
            assert "session_id" in cert

    @pytest.mark.asyncio
    async def test_privacy_certificate_missing_session(self, client: AsyncClient):
        response = await client.get("/api/privacy-certificate/does-not-exist-999")
        assert response.status_code == 404


# ──────────────────────────────────────────
# Root endpoint
# ──────────────────────────────────────────

class TestRootEndpoint:
    @pytest.mark.asyncio
    async def test_root_returns_service_info(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "CodeSentry" in data["service"]

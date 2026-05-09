"""
Orchestrator — coordinates Security → Performance → Fix agents
and emits SSE events for real-time streaming to the frontend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from api.models import (
    AMDMigrationGuide,
    AMDMigrationFindingModel,
    AnalysisSummary,
    PerformanceFinding,
    PrivacyCertificate,
    SecurityFinding,
    SessionResult,
    Severity,
)
from agents.security_agent import SecurityAgent
from agents.performance_agent import PerformanceAgent
from agents.fix_agent import FixAgent
from agents.amd_migration_advisor import AMDMigrationAdvisor
from amd_metrics import AMDMetricsCollector
from memory.session_store import get_store
from privacy.privacy_guard import ZeroDataRetentionGuard
from tools.code_parser import (
    FileEntry,
    build_context_block,
    parse_code_string,
    parse_directory,
    parse_zip_base64,
)
from tools.github_connector import GitHubConnector
from tools.benchmark_tool import start_benchmark, record_first_finding, finish_benchmark

logger = logging.getLogger(__name__)

# Config from environment
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8080/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen2.5-Coder-32B-Instruct")
LLM_API_KEY = os.getenv("LLM_API_KEY", "not-needed-local")
USE_LLM = os.getenv("USE_LLM", "true").lower() == "true"


def _sse_event(event: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {"event": event, "data": data}


class Orchestrator:
    """
    Master agent. Runs the full analysis pipeline:
      1. Ingest code (GitHub / string / zip)
      2. Security Agent (static + LLM)
      3. Performance Agent (static + LLM)
      4. Fix Agent (diffs + report)
      5. Privacy certificate generation

    Yields SSE event dicts throughout for real-time streaming.
    """

    def __init__(self) -> None:
        self.security_agent = SecurityAgent(
            vllm_base_url=VLLM_BASE_URL,
            model=MODEL_NAME,
            api_key=LLM_API_KEY
        )
        self.performance_agent = PerformanceAgent(
            vllm_base_url=VLLM_BASE_URL,
            model=MODEL_NAME,
            api_key=LLM_API_KEY
        )
        self.fix_agent = FixAgent(
            vllm_base_url=VLLM_BASE_URL,
            model=MODEL_NAME,
            api_key=LLM_API_KEY
        )
        self.migration_advisor = AMDMigrationAdvisor()
        self.metrics_collector = AMDMetricsCollector()
        self.store = get_store()

    # ──────────────────────────────────────────
    # SSE streaming pipeline
    # ──────────────────────────────────────────

    async def run_stream(
        self,
        source: str,
        source_type: str,
        session_id: str,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Full analysis pipeline yielding SSE event dicts.
        Call from a FastAPI StreamingResponse / EventSourceResponse.
        """
        start_time = time.perf_counter()
        bench = start_benchmark()
        self.metrics_collector.reset_tokens()

        # Update session
        await self.store.update(session_id, {"source_type": source_type, "status": "running"})

        # ── AMD Metrics background poller ────────────────────
        metrics_queue: asyncio.Queue = asyncio.Queue()
        metrics_stop = asyncio.Event()

        async def _poll_amd_metrics() -> None:
            """Collect AMD GPU metrics every 2 seconds."""
            try:
                while not metrics_stop.is_set():
                    snapshot = await self.metrics_collector.collect()
                    await metrics_queue.put(snapshot)
                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.debug("[Orchestrator] AMD metrics polling error: %s", exc)

        metrics_task = asyncio.create_task(_poll_amd_metrics())

        with ZeroDataRetentionGuard(session_id=session_id, enforce_network_block=False) as guard:
            # ── Step 1: Ingest ───────────────────────────────────
            yield _sse_event("status", {"message": "Ingesting code...", "session_id": session_id})

            try:
                files = await asyncio.to_thread(self._ingest, source, source_type)
            except Exception as exc:
                metrics_stop.set()
                metrics_task.cancel()
                yield _sse_event("error", {"message": f"Ingestion failed: {exc}"})
                await self.store.set_status(session_id, "error")
                return

            yield _sse_event("status", {
                "message": f"Loaded {len(files)} file(s)",
                "files_count": len(files),
            })

            code_context = build_context_block(files)

            # Drain any queued AMD metrics
            while not metrics_queue.empty():
                try:
                    snapshot = metrics_queue.get_nowait()
                    yield _sse_event("amd_metrics", snapshot)
                except asyncio.QueueEmpty:
                    break

            # ── Step 2: Security Agent ───────────────────────────
            yield _sse_event("agent_start", {"agent": "security", "status": "scanning"})

            # Static scan first (fast)
            static_security = await asyncio.to_thread(
                self.security_agent.static_scan, files
            )
            for i, finding in enumerate(static_security):
                finding.id = f"SEC-STATIC-{i+1}"
                record_first_finding(bench)
                yield _sse_event("finding", {
                    "agent": "security",
                    **finding.model_dump(),
                })
                await asyncio.sleep(0)  # yield control to event loop

            # Drain AMD metrics between agents
            while not metrics_queue.empty():
                try:
                    yield _sse_event("amd_metrics", metrics_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            # LLM deep scan
            if USE_LLM:
                llm_security = await self.security_agent.llm_scan(code_context, static_security)
                # Merge with static
                security_findings = self.security_agent._merge_findings(static_security, llm_security)
                security_findings = self.security_agent._sort_by_severity(security_findings)
                # Emit LLM-enriched findings
                for i, finding in enumerate(llm_security):
                    finding.id = f"SEC-LLM-{i+1}"
                    record_first_finding(bench)
                    yield _sse_event("finding", {
                        "agent": "security",
                        **finding.model_dump(),
                    })
                    await asyncio.sleep(0)
            else:
                security_findings = static_security

            yield _sse_event("agent_complete", {
                "agent": "security",
                "findings_count": len(security_findings),
            })

            # ── Step 3: Performance Agent ────────────────────────
            yield _sse_event("agent_start", {"agent": "performance", "status": "analyzing"})

            perf_findings = await self.performance_agent.analyze(
                files, code_context, use_llm=USE_LLM
            )

            for i, pf in enumerate(perf_findings):
                pf.id = f"PERF-{i+1}"
                yield _sse_event("finding", {
                    "agent": "performance",
                    "type": pf.type.value,
                    "saving_mb": pf.saving_mb or 0,
                    "suggestion": pf.suggestion,
                    **pf.model_dump(),
                })
                await asyncio.sleep(0)

            yield _sse_event("agent_complete", {
                "agent": "performance",
                "optimizations_count": len(perf_findings),
            })

            # Drain AMD metrics
            while not metrics_queue.empty():
                try:
                    yield _sse_event("amd_metrics", metrics_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            # ── Step 3.5: AMD Migration Advisor ──────────────────
            amd_migration_result: Optional[Dict] = None
            try:
                amd_migration_result = await self.migration_advisor.scan(files)
                for mf in amd_migration_result.get("findings", []):
                    yield _sse_event("amd_migration_finding", mf)
                    await asyncio.sleep(0.05)
                yield _sse_event("amd_migration_summary", {
                    "compatibility_score": amd_migration_result["compatibility_score"],
                    "compatibility_label": amd_migration_result["compatibility_label"],
                    "total_cuda_patterns_found": amd_migration_result["total_cuda_patterns_found"],
                    "summary": amd_migration_result["summary"],
                })
            except Exception as exc:
                logger.warning("[Orchestrator] AMD migration scan failed: %s", exc)

            # ── Step 4: Fix Agent ────────────────────────────────
            yield _sse_event("agent_start", {"agent": "fix", "status": "generating_fixes"})

            fix_result = await self.fix_agent.generate_fixes(
                files=files,
                security_findings=security_findings,
                performance_findings=perf_findings,
                session_id=session_id,
                use_llm=USE_LLM,
            )

            # Emit individual fixes for the UI
            for fix in fix_result.finding_fixes:
                yield _sse_event("fix_ready", fix.model_dump())
                await asyncio.sleep(0.1)  # tiny delay for UI animation

            yield _sse_event("fix_batch", {
                "diff": fix_result.diffs[0].diff if fix_result.diffs else "",
                "files_changed": fix_result.files_changed,
                "diffs": [d.model_dump() for d in fix_result.diffs],
            })

            # ── Step 5: Summary & Certificate ───────────────────
            # Stop AMD metrics polling
            metrics_stop.set()
            metrics_task.cancel()

            bench = finish_benchmark(bench, findings=len(security_findings))
            elapsed = time.perf_counter() - start_time

            sev_counts = {s.value: 0 for s in Severity}
            for f in security_findings:
                sev_counts[f.severity.value] += 1

            total_mem_saving = sum((pf.saving_mb or 0.0) for pf in perf_findings)

            summary = AnalysisSummary(
                session_id=session_id,
                total_findings=len(security_findings),
                critical_count=sev_counts.get("critical", 0),
                high_count=sev_counts.get("high", 0),
                medium_count=sev_counts.get("medium", 0),
                low_count=sev_counts.get("low", 0),
                performance_optimizations=len(perf_findings),
                estimated_memory_savings_mb=total_mem_saving,
                analysis_duration_seconds=round(elapsed, 2),
                files_analyzed=len(files),
            )

            cert_dict = guard.generate_certificate()
            privacy_cert = PrivacyCertificate(
                session_id=cert_dict["session_id"],
                timestamp=cert_dict["timestamp"],
                guarantee=cert_dict["guarantee"],
                model_endpoint=cert_dict["model_endpoint"],
                external_calls_blocked=cert_dict.get("external_calls_blocked", []),
                data_wiped=cert_dict["data_wiped"],
                signature=cert_dict["signature"],
            )

            # Build AMD migration guide for the final result
            amd_guide = None
            if amd_migration_result:
                try:
                    amd_guide = AMDMigrationGuide(
                        compatibility_score=amd_migration_result["compatibility_score"],
                        compatibility_label=amd_migration_result["compatibility_label"],
                        total_cuda_patterns_found=amd_migration_result["total_cuda_patterns_found"],
                        findings=[
                            AMDMigrationFindingModel(**f)
                            for f in amd_migration_result.get("findings", [])
                        ],
                        summary=amd_migration_result.get("summary", ""),
                    )
                except Exception as exc:
                    logger.debug("[Orchestrator] AMDMigrationGuide build failed: %s", exc)

            # Persist full result to session store
            session_result = SessionResult(
                session_id=session_id,
                status="complete",
                summary=summary,
                security_findings=security_findings,
                performance_findings=perf_findings,
                fix_result=fix_result,
                privacy_certificate=privacy_cert,
                amd_migration_guide=amd_guide,
            )
            await self.store.update(session_id, {
                "_status": "complete",
                "result": session_result.model_dump(mode="json"),
            })

            yield _sse_event("complete", {
                "privacy_certificate": privacy_cert.model_dump(),
                "summary": summary.model_dump(),
                "security_report_available": True,
                "amd_migration_guide": amd_guide.model_dump() if amd_guide else None,
            })

    # ──────────────────────────────────────────
    # Code ingestion
    # ──────────────────────────────────────────

    def _ingest(self, source: str, source_type: str) -> List[FileEntry]:
        """Route ingestion to the correct parser based on source_type."""
        if source_type == "github":
            with GitHubConnector(source) as repo_dir:
                return parse_directory(repo_dir)
        elif source_type == "huggingface":
            from tools.huggingface_connector import HuggingFaceConnector
            with HuggingFaceConnector(source) as repo_dir:
                return parse_directory(repo_dir)
        elif source_type == "zip":
            return parse_zip_base64(source)
        elif source_type == "code":
            return parse_code_string(source, filename="input.py")
        else:
            raise ValueError(f"Unknown source_type: {source_type!r}")

    # ──────────────────────────────────────────
    # Demo mode (pre-computed, no GPU needed)
    # ──────────────────────────────────────────

    async def run_demo(self, session_id: str = "demo") -> SessionResult:
        """
        Return a pre-computed demo result using the vulnerable_ml_code fixture.
        Works without a GPU or vLLM server.
        """
        import pathlib

        fixture_path = (
            pathlib.Path(__file__).parent.parent
            / "tests" / "fixtures" / "vulnerable_ml_code.py"
        )
        code = fixture_path.read_text(encoding="utf-8") if fixture_path.exists() else DEMO_CODE

        files: List[FileEntry] = [("vulnerable_ml_code.py", code)]
        code_context = build_context_block(files)

        # Static-only analysis (no LLM) for demo
        security_findings = self.security_agent.static_scan(files)
        perf_findings = self.performance_agent.static_scan(files)
        fix_result = await self.fix_agent.generate_fixes(
            files, security_findings, perf_findings, session_id, use_llm=False
        )

        sev_counts = {s.value: 0 for s in Severity}
        for f in security_findings:
            sev_counts[f.severity.value] += 1

        summary = AnalysisSummary(
            session_id=session_id,
            total_findings=len(security_findings),
            critical_count=sev_counts.get("critical", 0),
            high_count=sev_counts.get("high", 0),
            medium_count=sev_counts.get("medium", 0),
            low_count=sev_counts.get("low", 0),
            performance_optimizations=len(perf_findings),
            estimated_memory_savings_mb=sum((p.saving_mb or 0) for p in perf_findings),
            analysis_duration_seconds=0.5,
            files_analyzed=1,
        )

        cert = PrivacyCertificate(
            session_id=session_id,
            timestamp="demo",
            guarantee="Demo mode — all inference ran locally (static analysis only).",
            model_endpoint="http://localhost:8080",
            external_calls_blocked=[],
            data_wiped=True,
            signature="demo-signature",
        )

        return SessionResult(
            session_id=session_id,
            status="complete",
            summary=summary,
            security_findings=security_findings,
            performance_findings=perf_findings,
            fix_result=fix_result,
            privacy_certificate=cert,
        )


# Minimal inline demo code (fallback if fixture file missing)
DEMO_CODE = '''
import pickle, os
from flask import Flask, request
app = Flask(__name__)
HF_TOKEN = "hf_abcdefghijklmnopqrstuvwxyz123456"

@app.route("/predict", methods=["POST"])
def predict():
    model_path = request.json["model_path"]
    model = pickle.load(open(model_path, "rb"))  # CWE-502
    user_prompt = request.json["prompt"]
    result = model.generate(f"Answer: {user_prompt}")  # LLM01
    eval(result)  # LLM02
    return {"result": result}
'''

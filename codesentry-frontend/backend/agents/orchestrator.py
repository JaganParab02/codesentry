"""
Agent Orchestrator — runs Security + Performance agents in parallel,
then feeds results to Fix Agent. Yields SSE events.
"""

import asyncio
from typing import AsyncGenerator

from .security_agent import SecurityAgent
from .performance_agent import PerformanceAgent
from .fix_agent import FixAgent


async def run_scan_pipeline(request) -> AsyncGenerator[tuple[str, dict], None]:
    """Main scan pipeline — orchestrates all three agents."""
    
    # Determine source code
    code = request.code or ""
    language = request.language or "python"

    # If GitHub URL, we'd clone here — for now return placeholder
    if request.type == "github" and request.url:
        code = f"# GitHub URL: {request.url}\n# Clone & scan would happen here\n"
        language = "python"

    findings = []

    # ── Security Agent ──
    yield "agent_start", {"agent": "security", "message": "Security Agent initializing..."}
    await asyncio.sleep(0.3)

    security_agent = SecurityAgent()
    async for event_type, event_data in security_agent.analyze(code, language):
        if event_type == "finding":
            findings.append(event_data)
        yield event_type, event_data

    # ── Performance Agent ──
    yield "agent_start", {"agent": "performance", "message": "Performance Agent initializing..."}
    await asyncio.sleep(0.3)

    perf_agent = PerformanceAgent()
    async for event_type, event_data in perf_agent.analyze(code, language):
        if event_type == "finding":
            findings.append(event_data)
        yield event_type, event_data

    # ── Fix Agent ──
    security_findings = [f for f in findings if f.get("agent") == "security" and f.get("fixAvailable")]
    if security_findings:
        yield "agent_start", {"agent": "fix", "message": "Fix Agent generating patches..."}
        await asyncio.sleep(0.3)

        fix_agent = FixAgent()
        async for event_type, event_data in fix_agent.generate_fixes(security_findings, code):
            yield event_type, event_data

    # ── Complete ──
    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        s = f.get("severity", "low")
        if s in sev:
            sev[s] += 1

    yield "complete", {
        "totalFindings": len(findings),
        **sev,
        "fixesGenerated": len(security_findings),
        "filesAnalyzed": 1,
    }

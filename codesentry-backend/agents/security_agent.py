"""
Security Agent — OWASP + OWASP LLM Top-10 vulnerability scanner.

Uses a two-pass approach:
  1. Fast regex static scan (zero LLM calls, instant results)
  2. Deep LLM analysis via vLLM / Qwen2.5-Coder-32B for semantic findings
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from api.models import SecurityFinding, Severity
from tools.code_parser import FileEntry, find_pattern_in_code, get_snippet
from tools.vulnerability_db import (
    ALL_CATEGORIES,
    ML_SPECIFIC_VULNS,
    get_all_patterns,
)

logger = logging.getLogger(__name__)

SECURITY_SYSTEM_PROMPT = """You are CodeSentry Security Agent — a senior application security engineer specialising in AI/ML systems.

Your task: Analyse the provided source code and identify security vulnerabilities across these categories:

## OWASP LLM Top-10 (AI/ML-Specific):
- LLM01 Prompt Injection: User inputs concatenated directly into prompts
- LLM02 Insecure Output Handling: LLM output passed to eval(), exec(), shell, SQL
- LLM03 Training Data Poisoning: Unvalidated data pipelines
- LLM04 Model Denial of Service: Unbounded context, no token limits
- LLM06 Sensitive Information Disclosure: Hardcoded API keys, PII in embeddings
- LLM08 Excessive Agency: Unrestricted tool/filesystem access for agents
- LLM09 Overreliance: No human-in-the-loop for critical decisions

## OWASP Web Top-10 (Applied to ML Serving):
- A01 Broken Access Control: Unauthenticated model endpoints
- A02 Cryptographic Failures: HTTP not HTTPS, verify=False
- A03 Injection: SQL/command injection in RAG queries
- A04 Insecure Design: pickle.load() from untrusted sources (CWE-502)
- A05 Security Misconfiguration: debug=True, CORS wildcard
- A07 Authentication Failures: Hardcoded secrets/tokens
- A08 Software Integrity Failures: Unverified model weight downloads

## Output Format (STRICT JSON ARRAY):
Return ONLY a valid JSON array of findings. Each finding:
{
  "severity": "critical|high|medium|low",
  "title": "Short descriptive title",
  "cwe": "CWE-XXX",
  "owasp_category": "LLM01|A03|etc",
  "line_number": <integer or null>,
  "file_path": "<filename or null>",
  "code_snippet": "<the vulnerable code snippet>",
  "explanation": "Clear explanation of WHY this is vulnerable",
  "fix_preview": "Concrete fix code or description"
}

Be precise. Only report real vulnerabilities, not style issues.
If no vulnerabilities found, return: []
"""


class SecurityAgent:
    def __init__(
        self,
        vllm_base_url: str = "http://localhost:8080/v1",
        model: str = "Qwen/Qwen2.5-Coder-32B-Instruct",
        api_key: str = "not-needed-local",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = AsyncOpenAI(
            base_url=vllm_base_url,
            api_key=api_key,
        )

    # ──────────────────────────────────────────
    # Static regex scan (fast, no LLM)
    # ──────────────────────────────────────────

    def static_scan(self, files: List[FileEntry]) -> List[SecurityFinding]:
        """
        Fast regex-based pass. Returns findings without LLM.
        Used to: (a) give instant partial results and (b) prime the LLM context.
        """
        findings: List[SecurityFinding] = []
        patterns = get_all_patterns()
        seen: set = set()  # deduplicate by (category_id, file, line)

        for file_path, code in files:
            for pat_info in patterns:
                matches = find_pattern_in_code(code, pat_info["pattern"], file_path)
                for match in matches:
                    key = (pat_info["category_id"], file_path, match["line_number"])
                    if key in seen:
                        continue
                    seen.add(key)

                    severity_str = pat_info.get("severity", "medium")
                    try:
                        sev = Severity(severity_str)
                    except ValueError:
                        sev = Severity.medium

                    findings.append(
                        SecurityFinding(
                            severity=sev,
                            title=f"[Static] {pat_info['category_name']}",
                            cwe=pat_info.get("cwe"),
                            owasp_category=pat_info.get("category_id"),
                            line=match["line_number"],
                            file=file_path,
                            code=match["snippet"],
                            description=pat_info["description"],
                            suggestion=f"Review and patch {pat_info['category_name']} manually, or await AI fix generation.",
                        )
                    )

        return self._sort_by_severity(findings)

    # ──────────────────────────────────────────
    # LLM deep analysis
    # ──────────────────────────────────────────

    async def llm_scan(
        self,
        code_context: str,
        static_findings: Optional[List[SecurityFinding]] = None,
    ) -> List[SecurityFinding]:
        """
        Send the full code context to Qwen for deep semantic analysis.
        Returns a parsed list of SecurityFinding objects.
        """
        # Add static findings hint to focus LLM attention
        static_hint = ""
        if static_findings:
            hint_items = [f"- Line {f.line}: {f.title}" for f in static_findings[:10]]
            static_hint = (
                "\n\n## Static pre-scan flagged these lines (validate and expand):\n"
                + "\n".join(hint_items)
            )

        user_message = (
            f"Analyse the following codebase for security vulnerabilities:{static_hint}\n\n"
            f"```\n{code_context}\n```\n\n"
            "Return ONLY the JSON array of findings."
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SECURITY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw = response.choices[0].message.content or "[]"
            return self._parse_llm_response(raw)

        except Exception as exc:
            logger.error("[SecurityAgent] LLM call failed: %s", exc)
            return []  # Degrade gracefully — static scan results still available

    # ──────────────────────────────────────────
    # Streaming LLM scan (yields findings as they are parsed)
    # ──────────────────────────────────────────

    async def llm_scan_stream(
        self,
        code_context: str,
        static_findings: Optional[List[SecurityFinding]] = None,
    ) -> AsyncGenerator[SecurityFinding, None]:
        """Stream findings from the LLM as they arrive (parsed from accumulated JSON)."""
        static_hint = ""
        if static_findings:
            hint_items = [f"- Line {f.line}: {f.title}" for f in static_findings[:10]]
            static_hint = (
                "\n\n## Static pre-scan flagged (validate and expand):\n"
                + "\n".join(hint_items)
            )

        user_message = (
            f"Analyse the following codebase for security vulnerabilities:{static_hint}\n\n"
            f"```\n{code_context}\n```\n\n"
            "Return ONLY the JSON array of findings. Be thorough."
        )

        buffer = ""
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SECURITY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                buffer += delta

            # Parse full buffer once streaming completes
            for finding in self._parse_llm_response(buffer):
                yield finding

        except Exception as exc:
            logger.error("[SecurityAgent] Streaming LLM call failed: %s", exc)

    # ──────────────────────────────────────────
    # Full analysis pipeline
    # ──────────────────────────────────────────

    async def analyze(
        self,
        files: List[FileEntry],
        code_context: str,
        use_llm: bool = True,
    ) -> List[SecurityFinding]:
        """
        Run static scan + optional LLM scan, merge and deduplicate findings.
        """
        # Phase 1: static
        static = self.static_scan(files)
        logger.info("[SecurityAgent] Static scan: %d findings", len(static))

        if not use_llm:
            return static

        # Phase 2: LLM deep scan
        llm_findings = await self.llm_scan(code_context, static)
        logger.info("[SecurityAgent] LLM scan: %d findings", len(llm_findings))

        # Merge: LLM findings take priority (richer explanations)
        merged = self._merge_findings(static, llm_findings)
        return self._sort_by_severity(merged)

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _parse_llm_response(self, raw: str) -> List[SecurityFinding]:
        """Extract and parse the JSON array from LLM output."""
        # Strip markdown code fences if present
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
        raw = raw.rstrip("`").strip()

        # Find JSON array boundaries
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            logger.warning("[SecurityAgent] No JSON array found in LLM response")
            return []

        try:
            data: List[Dict] = json.loads(raw[start:end])
        except json.JSONDecodeError as exc:
            logger.warning("[SecurityAgent] JSON parse error: %s", exc)
            return []

        findings: List[SecurityFinding] = []
        for item in data:
            try:
                sev_str = item.get("severity", "medium").lower()
                try:
                    sev = Severity(sev_str)
                except ValueError:
                    sev = Severity.medium

                findings.append(
                    SecurityFinding(
                        severity=sev,
                        title=item.get("title", "Unknown Vulnerability"),
                        cwe=item.get("cwe"),
                        owasp_category=item.get("owasp_category"),
                        line=item.get("line_number"),
                        file=item.get("file_path"),
                        code=item.get("code_snippet"),
                        description=item.get("explanation", ""),
                        suggestion=item.get("fix_preview"),
                    )
                )
            except Exception as e:
                logger.debug("[SecurityAgent] Skipping malformed finding: %s", e)
                continue

        return findings

    @staticmethod
    def _sort_by_severity(findings: List[SecurityFinding]) -> List[SecurityFinding]:
        order = {Severity.critical: 0, Severity.high: 1, Severity.medium: 2, Severity.low: 3, Severity.info: 4}
        return sorted(findings, key=lambda f: order.get(f.severity, 99))

    @staticmethod
    def _merge_findings(
        static: List[SecurityFinding],
        llm: List[SecurityFinding],
    ) -> List[SecurityFinding]:
        """
        Merge static and LLM findings.
        LLM findings replace static ones that share the same (owasp_category, line_number).
        """
        # Index static findings by category+line
        static_index: Dict[tuple, SecurityFinding] = {}
        for f in static:
            key = (f.owasp_category, f.line)
            static_index[key] = f

        merged: List[SecurityFinding] = list(llm)  # LLM first
        llm_keys = {(f.owasp_category, f.line) for f in llm}

        # Add static findings not covered by LLM
        for f in static:
            key = (f.owasp_category, f.line)
            if key not in llm_keys:
                merged.append(f)

        return merged

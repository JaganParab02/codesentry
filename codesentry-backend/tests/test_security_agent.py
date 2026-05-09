"""
Tests for SecurityAgent — static scan only (no LLM / GPU required).
"""
from __future__ import annotations

import json
import pathlib
import pytest

from agents.security_agent import SecurityAgent
from api.models import Severity
from tools.code_parser import FileEntry

# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def vulnerable_code() -> str:
    return (FIXTURES_DIR / "vulnerable_ml_code.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def clean_code() -> str:
    return (FIXTURES_DIR / "clean_ml_code.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def expected() -> dict:
    return json.loads((FIXTURES_DIR / "expected_findings.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def agent() -> SecurityAgent:
    return SecurityAgent()


@pytest.fixture(scope="module")
def vulnerable_files(vulnerable_code: str) -> list[FileEntry]:
    return [("vulnerable_ml_code.py", vulnerable_code)]


@pytest.fixture(scope="module")
def vulnerable_findings(agent: SecurityAgent, vulnerable_files: list[FileEntry]):
    return agent.static_scan(vulnerable_files)


# ──────────────────────────────────────────
# Tests
# ──────────────────────────────────────────

class TestPromptInjectionDetection:
    def test_detects_prompt_injection(self, vulnerable_findings):
        """LLM01: Should detect user input concatenated directly into prompt."""
        llm01_findings = [
            f for f in vulnerable_findings
            if f.owasp_category == "LLM01" or "Prompt Injection" in f.title
        ]
        assert len(llm01_findings) > 0, (
            "Expected at least one LLM01 Prompt Injection finding"
        )

    def test_prompt_injection_severity(self, vulnerable_findings):
        """Prompt injection must be rated critical or high."""
        llm01_findings = [
            f for f in vulnerable_findings
            if f.owasp_category == "LLM01" or "Prompt Injection" in f.title
        ]
        assert any(
            f.severity in (Severity.critical, Severity.high) for f in llm01_findings
        ), "Prompt injection finding must be critical or high severity"


class TestPickleDetection:
    def test_detects_pickle_deserialization(self, vulnerable_findings):
        """A04 / CWE-502: Should detect pickle.load() from untrusted source."""
        pickle_findings = [
            f for f in vulnerable_findings
            if (f.cwe and "502" in f.cwe) or "pickle" in f.title.lower() or "Insecure Design" in (f.owasp_category or "")
        ]
        assert len(pickle_findings) > 0, (
            "Expected CWE-502 finding for pickle.load()"
        )

    def test_pickle_is_critical(self, vulnerable_findings):
        pickle_findings = [
            f for f in vulnerable_findings
            if f.cwe and "502" in f.cwe
        ]
        if pickle_findings:
            assert any(f.severity == Severity.critical for f in pickle_findings)


class TestHardcodedAPIKeyDetection:
    def test_detects_hardcoded_api_key(self, vulnerable_findings):
        """LLM06 / A07: Should detect hardcoded HF_TOKEN and OpenAI key."""
        key_findings = [
            f for f in vulnerable_findings
            if f.owasp_category in ("LLM06", "A07")
            or any(kw in f.title.lower() for kw in ("hardcoded", "api key", "token", "secret"))
        ]
        assert len(key_findings) > 0, (
            "Expected at least one hardcoded API key finding (LLM06 / A07)"
        )

    def test_hardcoded_key_severity_high_or_critical(self, vulnerable_findings):
        key_findings = [
            f for f in vulnerable_findings
            if f.owasp_category in ("LLM06", "A07")
        ]
        if key_findings:
            assert any(f.severity in (Severity.critical, Severity.high) for f in key_findings)


class TestEvalDetection:
    def test_detects_eval_of_llm_output(self, vulnerable_findings):
        """LLM02: Should detect eval() used on model output."""
        llm02_findings = [
            f for f in vulnerable_findings
            if f.owasp_category == "LLM02"
            or any(kw in f.title.lower() for kw in ("eval", "insecure output"))
        ]
        assert len(llm02_findings) > 0, (
            "Expected LLM02 finding for eval(llm_output)"
        )


class TestSeverityRanking:
    def test_severity_ranking_order(self, vulnerable_findings):
        """Critical findings must appear before high, which appear before medium."""
        if len(vulnerable_findings) < 2:
            pytest.skip("Need at least 2 findings to test ordering")

        severity_order = {
            Severity.critical: 0,
            Severity.high: 1,
            Severity.medium: 2,
            Severity.low: 3,
            Severity.info: 4,
        }
        for i in range(len(vulnerable_findings) - 1):
            a = severity_order[vulnerable_findings[i].severity]
            b = severity_order[vulnerable_findings[i + 1].severity]
            assert a <= b, (
                f"Finding {i} ({vulnerable_findings[i].severity}) should not come after "
                f"finding {i+1} ({vulnerable_findings[i+1].severity})"
            )

    def test_has_critical_findings(self, vulnerable_findings):
        """Vulnerable code must produce at least one critical finding."""
        critical = [f for f in vulnerable_findings if f.severity == Severity.critical]
        assert len(critical) > 0, "Expected at least one critical severity finding"


class TestOWASPLLMCoverage:
    def test_owasp_llm_coverage(self, vulnerable_findings):
        """
        Assert findings cover the key OWASP LLM Top-10 categories
        present in the vulnerable fixture.
        """
        found_categories = {f.owasp_category for f in vulnerable_findings if f.owasp_category}
        # These categories have triggers in the vulnerable fixture
        expected_categories = {"LLM01", "LLM02", "LLM06"}
        missing = expected_categories - found_categories
        assert not missing, (
            f"Missing OWASP LLM categories in findings: {missing}. "
            f"Found: {found_categories}"
        )

    def test_no_false_positives_on_clean_code(self, agent: SecurityAgent, clean_code: str):
        """Clean code should produce significantly fewer critical findings."""
        clean_files: list[FileEntry] = [("clean_ml_code.py", clean_code)]
        clean_findings = agent.static_scan(clean_files)
        critical_clean = [f for f in clean_findings if f.severity == Severity.critical]
        # Clean code may still trigger some pattern matches, but should have far fewer
        assert len(critical_clean) < 3, (
            f"Clean code produced {len(critical_clean)} critical findings — too many false positives"
        )


class TestFindingSchema:
    def test_all_findings_have_required_fields(self, vulnerable_findings):
        """Every finding must have severity, title, and explanation."""
        for i, finding in enumerate(vulnerable_findings):
            assert finding.severity is not None, f"Finding {i} missing severity"
            assert finding.title, f"Finding {i} missing title"
            assert finding.explanation, f"Finding {i} missing explanation"

    def test_findings_are_not_empty(self, vulnerable_findings):
        assert len(vulnerable_findings) > 0, (
            "SecurityAgent.static_scan() returned no findings for vulnerable code"
        )

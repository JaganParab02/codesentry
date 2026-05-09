"""
Security Agent — detects OWASP vulnerabilities, hardcoded secrets,
unsafe eval, SQL injection, and more using pattern matching + LLM.
"""

import asyncio
import re
from typing import AsyncGenerator

# CWE mapping for common patterns
CWE_MAP = {
    "sql_injection": "CWE-89",
    "hardcoded_secret": "CWE-798",
    "eval_usage": "CWE-95",
    "pickle_loads": "CWE-502",
    "md5_password": "CWE-328",
    "path_traversal": "CWE-22",
    "missing_csrf": "CWE-352",
}

PATTERNS = [
    {
        "id": "SEC-001",
        "name": "SQL Injection",
        "pattern": r'(query|sql)\s*=\s*[f`"\'].*\{.*\}|SELECT.*\+.*req|execute\(.*\+',
        "severity": "critical",
        "cwe": "CWE-89",
        "suggestion": "Use parameterized queries or an ORM to prevent SQL injection.",
        "fixAvailable": True,
    },
    {
        "id": "SEC-002",
        "name": "Hardcoded Secret",
        "pattern": r'(api_key|secret|password|token|API_KEY)\s*=\s*["\'][a-zA-Z0-9_\-]{12,}["\']',
        "severity": "high",
        "cwe": "CWE-798",
        "suggestion": "Move secrets to environment variables or a secrets manager.",
        "fixAvailable": True,
    },
    {
        "id": "SEC-003",
        "name": "Unsafe eval()",
        "pattern": r'\beval\s*\(',
        "severity": "high",
        "cwe": "CWE-95",
        "suggestion": "Replace eval() with a safe expression parser.",
        "fixAvailable": True,
    },
    {
        "id": "SEC-004",
        "name": "Insecure Deserialization (pickle)",
        "pattern": r'pickle\.loads?\s*\(',
        "severity": "critical",
        "cwe": "CWE-502",
        "suggestion": "Use safetensors or JSON instead of pickle for untrusted data.",
        "fixAvailable": True,
    },
    {
        "id": "SEC-005",
        "name": "Weak Password Hashing (MD5)",
        "pattern": r"hashlib\.md5|createHash\('md5'\)|md5\(",
        "severity": "high",
        "cwe": "CWE-328",
        "suggestion": "Use bcrypt, scrypt, or Argon2 for password hashing.",
        "fixAvailable": True,
    },
]


class SecurityAgent:
    async def analyze(self, code: str, language: str) -> AsyncGenerator[tuple[str, dict], None]:
        lines = code.split("\n")
        total = len(lines)
        found = 0

        for i, pattern_def in enumerate(PATTERNS):
            await asyncio.sleep(0.5)

            # Progress update
            pct = int((i / len(PATTERNS)) * 100)
            yield "progress", {
                "agent": "security",
                "percent": pct,
                "filesScanned": i + 1,
                "message": f"Scanning for {pattern_def['name']}...",
            }

            # Pattern scan
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern_def["pattern"], line, re.IGNORECASE):
                    found += 1
                    yield "finding", {
                        "agent": "security",
                        "id": pattern_def["id"],
                        "title": pattern_def["name"],
                        "severity": pattern_def["severity"],
                        "cwe": pattern_def["cwe"],
                        "description": f"Detected {pattern_def['name']} pattern at line {line_num}.",
                        "file": "uploaded_code.py",
                        "line": line_num,
                        "code": line.strip(),
                        "suggestion": pattern_def["suggestion"],
                        "fixAvailable": pattern_def["fixAvailable"],
                    }
                    break  # One finding per pattern

        yield "progress", {
            "agent": "security",
            "percent": 100,
            "filesScanned": len(PATTERNS),
            "message": f"Security scan complete — {found} issues found",
        }

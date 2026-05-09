"""
Performance Agent — detects N+1 queries, memory leaks,
unoptimized tensor ops, and redundant re-renders.
"""

import asyncio
import re
from typing import AsyncGenerator

PERF_PATTERNS = [
    {
        "id": "PERF-001",
        "name": "N+1 Query Pattern",
        "pattern": r'for.*(await|async).*query|forEach.*db\.|for.*execute\(',
        "severity": "high",
        "suggestion": "Use a single JOIN or batch query to eliminate N+1.",
        "description": "Database queries inside loops cause N+1 performance degradation.",
    },
    {
        "id": "PERF-002",
        "name": "Memory Leak (Missing Cleanup)",
        "pattern": r'addEventListener|setInterval|setTimeout(?!.*clearTimeout)',
        "severity": "medium",
        "suggestion": "Add cleanup functions to remove event listeners and clear timers.",
        "description": "Event listeners or timers without cleanup cause memory leaks over time.",
    },
    {
        "id": "PERF-003",
        "name": "CPU Tensor Operation (use GPU)",
        "pattern": r"\.to\(['\"]cpu['\"]\)|\.cpu\(\)|device=['\"]cpu['\"]",
        "severity": "high",
        "suggestion": "Move tensor operations to GPU with .to('cuda') and use torch.no_grad() for inference.",
        "description": "Tensor ops on CPU when GPU is available slows inference significantly.",
    },
    {
        "id": "PERF-004",
        "name": "Missing React Memoization",
        "pattern": r'const \w+ = \(\{.*\}\) =>|function \w+\(\{.*\}\)',
        "severity": "low",
        "suggestion": "Wrap expensive components with React.memo() and use useCallback/useMemo.",
        "description": "Missing memoization causes unnecessary re-renders on every parent update.",
    },
]


class PerformanceAgent:
    async def analyze(self, code: str, language: str) -> AsyncGenerator[tuple[str, dict], None]:
        lines = code.split("\n")
        found = 0

        for i, pattern_def in enumerate(PERF_PATTERNS):
            await asyncio.sleep(0.6)

            pct = int((i / len(PERF_PATTERNS)) * 100)
            yield "progress", {
                "agent": "performance",
                "percent": pct,
                "filesScanned": i + 1,
                "message": f"Checking for {pattern_def['name']}...",
            }

            for line_num, line in enumerate(lines, 1):
                if re.search(pattern_def["pattern"], line, re.IGNORECASE):
                    found += 1
                    yield "finding", {
                        "agent": "performance",
                        "id": pattern_def["id"],
                        "title": pattern_def["name"],
                        "severity": pattern_def["severity"],
                        "cwe": None,
                        "description": pattern_def["description"],
                        "file": "uploaded_code.py",
                        "line": line_num,
                        "code": line.strip(),
                        "suggestion": pattern_def["suggestion"],
                        "fixAvailable": False,
                    }
                    break

        yield "progress", {
            "agent": "performance",
            "percent": 100,
            "filesScanned": len(PERF_PATTERNS),
            "message": f"Performance analysis complete — {found} issues found",
        }

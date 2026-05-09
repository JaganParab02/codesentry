"""
AMD ROCm Migration Advisor — CUDA → ROCm/HIP compatibility scanner.

Scans code for CUDA-specific patterns and provides actionable migration
guidance for AMD MI300X hardware.  Produces an AMD Compatibility Score
and a per-file migration guide.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from tools.code_parser import FileEntry, get_snippet

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────
# Migration pattern definitions (10 categories)
# ──────────────────────────────────────────────────

MIGRATION_PATTERNS: List[Dict[str, Any]] = [
    {
        "id": "AMD_M01",
        "pattern": re.compile(
            r"torch\.cuda\.is_available\s*\(\)", re.MULTILINE
        ),
        "title": "CUDA Device Check",
        "description": (
            "torch.cuda.is_available() works on ROCm but torch.version.hip "
            "is more explicit for AMD hardware detection."
        ),
        "rocm_fix": (
            "Use `torch.cuda.is_available()` (ROCm compatible) "
            "or check `hasattr(torch.version, 'hip')` for explicit AMD detection."
        ),
        "severity": "low",
    },
    {
        "id": "AMD_M02",
        "pattern": re.compile(
            r"""(?:nvidia[\-_]smi|nvidia_smi|["']nvidia-smi["'])""",
            re.MULTILINE,
        ),
        "title": "NVIDIA-Specific CLI Tool",
        "description": "nvidia-smi is NVIDIA-only and will fail on AMD hardware.",
        "rocm_fix": (
            "Replace nvidia-smi with rocm-smi. "
            "Example: subprocess.run(['rocm-smi', '--showmeminfo', 'vram'])"
        ),
        "severity": "critical",
    },
    {
        "id": "AMD_M03",
        "pattern": re.compile(
            r"CUDA_VISIBLE_DEVICES", re.MULTILINE
        ),
        "title": "CUDA Device Selection Environment Variable",
        "description": "CUDA_VISIBLE_DEVICES is ignored on AMD/ROCm hardware.",
        "rocm_fix": "Replace with HIP_VISIBLE_DEVICES=0 for AMD GPU selection.",
        "severity": "high",
    },
    {
        "id": "AMD_M04",
        "pattern": re.compile(
            r"torch\.cuda\.amp\.(?:autocast|GradScaler)", re.MULTILINE
        ),
        "title": "Legacy CUDA AMP API",
        "description": "Old torch.cuda.amp API has limited ROCm support.",
        "rocm_fix": (
            "Upgrade to torch.amp.autocast('cuda') and torch.amp.GradScaler('cuda') "
            "which are ROCm-native and match MI300X bfloat16 support."
        ),
        "severity": "high",
    },
    {
        "id": "AMD_M05",
        "pattern": re.compile(
            r"\.half\s*\(\)|torch\.float16|dtype\s*=\s*torch\.float16",
            re.MULTILINE,
        ),
        "title": "FP16 Precision (Suboptimal on MI300X)",
        "description": (
            "FP16 works on AMD but bfloat16 is natively supported on MI300X "
            "with no accuracy loss and better numerical stability."
        ),
        "rocm_fix": (
            "Replace .half() with .bfloat16() and torch.float16 with torch.bfloat16. "
            "MI300X executes bfloat16 at the same speed with higher stability."
        ),
        "severity": "medium",
    },
    {
        "id": "AMD_M06",
        "pattern": re.compile(
            r"torch\.backends\.cudnn\.(?:benchmark|enabled|deterministic)",
            re.MULTILINE,
        ),
        "title": "cuDNN Backend Configuration",
        "description": (
            "torch.backends.cudnn settings are NVIDIA-specific. "
            "AMD uses MIOpen as its deep learning backend."
        ),
        "rocm_fix": (
            "Remove cudnn-specific flags. ROCm/MIOpen auto-configures. "
            "Use torch.backends.cuda.matmul.allow_tf32 for equivalent behavior."
        ),
        "severity": "medium",
    },
    {
        "id": "AMD_M07",
        "pattern": re.compile(
            r"(?:import\s+flash_attn|from\s+flash_attn)", re.MULTILINE
        ),
        "title": "Flash Attention — CUDA Build",
        "description": "Default flash-attn pip package is compiled for CUDA only.",
        "rocm_fix": (
            "Build flash-attn from source with ROCm flag: "
            "MAX_JOBS=4 pip install flash-attn --no-build-isolation "
            "Or use torch.nn.functional.scaled_dot_product_attention() "
            "which has native ROCm support."
        ),
        "severity": "high",
    },
    {
        "id": "AMD_M08",
        "pattern": re.compile(
            r"torch\.cuda\.(?:memory_allocated|max_memory_reserved|max_memory_allocated)\s*\(",
            re.MULTILINE,
        ),
        "title": "CUDA Memory Profiling API",
        "description": (
            "torch.cuda.memory_allocated() works on ROCm but "
            "rocm-smi gives more accurate MI300X HBM3 readings."
        ),
        "rocm_fix": (
            "Continue using torch.cuda.memory_allocated() (ROCm compatible) "
            "but add rocm-smi polling for accurate HBM3 bandwidth metrics."
        ),
        "severity": "low",
    },
    {
        "id": "AMD_M09",
        "pattern": re.compile(
            r"""device\s*=\s*['"]cuda['"]""", re.MULTILINE
        ),
        "title": "Hardcoded CUDA Device String",
        "description": (
            "Hardcoded 'cuda' string works on ROCm but poor practice "
            "for hardware-agnostic code."
        ),
        "rocm_fix": (
            "Replace with: device = torch.device('cuda' if torch.cuda.is_available() else 'cpu') "
            "This works identically on AMD ROCm."
        ),
        "severity": "low",
    },
    {
        "id": "AMD_M10",
        "pattern": re.compile(
            r"load_in_8bit\s*=\s*True|load_in_4bit\s*=\s*True|BitsAndBytesConfig",
            re.MULTILINE,
        ),
        "title": "BitsAndBytes Quantization (CUDA Only)",
        "description": "bitsandbytes library does not support AMD ROCm.",
        "rocm_fix": (
            "Use AutoAWQ or llama.cpp with ROCm backend for quantization. "
            "For vLLM on MI300X: use --quantization awq or --dtype bfloat16 "
            "with FP8 quantization which is natively supported."
        ),
        "severity": "critical",
    },
]

# Pre-built lookup for severity weighting
_SEVERITY_WEIGHT = {
    "critical": 20,
    "high": 10,
    "medium": 3,
    "low": 1,
}


# ──────────────────────────────────────────────────
# Migration Finding data class
# ──────────────────────────────────────────────────

class MigrationFinding:
    """A single CUDA → ROCm migration finding."""

    __slots__ = (
        "id", "title", "description", "rocm_fix", "severity",
        "file", "line", "code_snippet",
    )

    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        rocm_fix: str,
        severity: str,
        file: str,
        line: int,
        code_snippet: str,
    ) -> None:
        self.id = id
        self.title = title
        self.description = description
        self.rocm_fix = rocm_fix
        self.severity = severity
        self.file = file
        self.line = line
        self.code_snippet = code_snippet

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "rocm_fix": self.rocm_fix,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "code_snippet": self.code_snippet,
        }


# ──────────────────────────────────────────────────
# Main advisor class
# ──────────────────────────────────────────────────

class AMDMigrationAdvisor:
    """
    Scans source files for CUDA-specific patterns and produces
    an AMD Compatibility Score with migration guidance.
    """

    def __init__(self) -> None:
        self.patterns = MIGRATION_PATTERNS

    async def scan(self, files: List[FileEntry]) -> Dict[str, Any]:
        """
        Scan all files for CUDA-specific patterns.

        Parameters
        ----------
        files : list of (filename, content) tuples

        Returns
        -------
        dict with keys:
            findings, compatibility_score, compatibility_label,
            total_cuda_patterns_found
        """
        all_findings: List[MigrationFinding] = []
        seen: set = set()  # deduplicate by (pattern_id, file, line)

        for file_path, code in files:
            for pat_def in self.patterns:
                try:
                    for match in pat_def["pattern"].finditer(code):
                        line_number = code[: match.start()].count("\n") + 1
                        key = (pat_def["id"], file_path, line_number)
                        if key in seen:
                            continue
                        seen.add(key)

                        snippet = get_snippet(code, line_number, context=2)

                        all_findings.append(
                            MigrationFinding(
                                id=pat_def["id"],
                                title=pat_def["title"],
                                description=pat_def["description"],
                                rocm_fix=pat_def["rocm_fix"],
                                severity=pat_def["severity"],
                                file=file_path,
                                line=line_number,
                                code_snippet=snippet,
                            )
                        )
                except Exception as exc:
                    logger.debug(
                        "[AMDMigration] Pattern %s failed on %s: %s",
                        pat_def["id"], file_path, exc,
                    )

        # ── Compute AMD Compatibility Score ─────────────────────
        penalty = 0
        for f in all_findings:
            penalty += _SEVERITY_WEIGHT.get(f.severity, 1)

        score = max(0, min(100, 100 - penalty))

        if score >= 90:
            label = "Fully ROCm Ready"
        elif score >= 70:
            label = "Mostly Compatible"
        elif score >= 50:
            label = "Needs Migration Work"
        else:
            label = "CUDA-Specific Codebase"

        logger.info(
            "[AMDMigration] Scanned %d files — %d CUDA patterns found — score %d%% (%s)",
            len(files), len(all_findings), score, label,
        )

        return {
            "findings": [f.to_dict() for f in all_findings],
            "compatibility_score": score,
            "compatibility_label": label,
            "total_cuda_patterns_found": len(all_findings),
            "summary": (
                f"Found {len(all_findings)} CUDA-specific pattern(s). "
                f"After applying fixes, this codebase will be fully "
                f"optimized for AMD MI300X."
                if all_findings
                else "No CUDA-specific patterns detected — codebase is ROCm-ready."
            ),
        }

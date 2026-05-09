"""
GPU memory estimation and benchmark utilities.
Provides before/after estimates for ML code optimisations.
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional


# ──────────────────────────────────────────────
# Memory constants (approximate, in MB)
# ──────────────────────────────────────────────

DTYPE_BYTES: Dict[str, float] = {
    "float32": 4.0,
    "float16": 2.0,
    "bfloat16": 2.0,
    "int8": 1.0,
    "int4": 0.5,
}

MODEL_SIZE_PARAMS: Dict[str, int] = {
    "7b":  7_000_000_000,
    "13b": 13_000_000_000,
    "32b": 32_000_000_000,
    "70b": 70_000_000_000,
    "72b": 72_000_000_000,
}


def estimate_model_vram_mb(params: int, dtype: str = "float16") -> float:
    """Estimate VRAM (MB) required for a model given its parameter count and dtype."""
    bytes_per_param = DTYPE_BYTES.get(dtype, 2.0)
    return (params * bytes_per_param) / (1024 ** 2)


def estimate_activation_vram_mb(batch_size: int, seq_len: int, hidden_size: int, dtype: str = "float16") -> float:
    """Rough VRAM estimate for activations during inference."""
    bytes_per_param = DTYPE_BYTES.get(dtype, 2.0)
    # Approximate: batch * seq * hidden * ~12 layers worth of activations
    activation_elements = batch_size * seq_len * hidden_size * 12
    return (activation_elements * bytes_per_param) / (1024 ** 2)


def calculate_fp32_to_fp16_saving(vram_mb: float) -> float:
    """Saving in MB from switching from FP32 → FP16."""
    return vram_mb / 2.0


# ──────────────────────────────────────────────
# Code analysis heuristics
# ──────────────────────────────────────────────

def detect_dtype_from_code(code: str) -> str:
    """Detect the dtype being used in code via regex heuristics."""
    if re.search(r"torch\.float32|\.float\(\)", code):
        return "float32"
    if re.search(r"torch\.float16|fp16", code, re.IGNORECASE):
        return "float16"
    if re.search(r"torch\.bfloat16|bf16", code, re.IGNORECASE):
        return "bfloat16"
    return "float16"  # modern default


def detect_model_size_from_code(code: str) -> Optional[int]:
    """Try to detect model parameter count from code strings."""
    for label, count in MODEL_SIZE_PARAMS.items():
        if label in code.lower():
            return count
    return None


def detect_batch_size(code: str) -> int:
    """Extract batch size from code heuristics."""
    match = re.search(r"batch_size\s*=\s*(\d+)", code)
    if match:
        return int(match.group(1))
    return 1  # conservative default


def detect_seq_length(code: str) -> int:
    """Extract sequence length from code heuristics."""
    match = re.search(r"max_length\s*=\s*(\d+)|max_tokens\s*=\s*(\d+)|seq_len\s*=\s*(\d+)", code)
    if match:
        return int(next(g for g in match.groups() if g is not None))
    return 512  # safe default


# ──────────────────────────────────────────────
# Optimisation analysis
# ──────────────────────────────────────────────

def analyse_memory_optimisations(code: str) -> List[Dict]:
    """
    Scan code and return a list of memory optimisation opportunities
    with before/after estimates.
    """
    findings: List[Dict] = []
    dtype = detect_dtype_from_code(code)
    params = detect_model_size_from_code(code)

    # FP32 → FP16 opportunity
    if dtype == "float32" and params:
        current_mb = estimate_model_vram_mb(params, "float32")
        optimised_mb = estimate_model_vram_mb(params, "float16")
        saving = current_mb - optimised_mb
        findings.append({
            "type": "gpu_memory",
            "title": "Switch from FP32 to FP16/BF16",
            "current_estimate": f"{current_mb:.0f} MB",
            "optimized_estimate": f"{optimised_mb:.0f} MB",
            "saving_mb": saving,
            "saving": f"{saving:.0f} MB ({saving / current_mb * 100:.0f}% reduction)",
            "code_fix": "# Change: model.float() → model.half()  OR  torch_dtype=torch.bfloat16",
        })

    # Missing no_grad
    inference_fns = re.findall(
        r"def\s+(predict|infer|inference|generate|run_model)\s*\(", code
    )
    no_grad_present = bool(re.search(r"@torch\.no_grad|with torch\.no_grad", code))
    if inference_fns and not no_grad_present:
        findings.append({
            "type": "gpu_memory",
            "title": "Missing @torch.no_grad() on inference path",
            "current_estimate": "2x gradient memory overhead",
            "optimized_estimate": "Gradient tensors freed immediately",
            "saving_mb": 512.0,  # conservative estimate
            "saving": "~512 MB (eliminates gradient buffers)",
            "code_fix": "@torch.no_grad()\ndef predict(...):",
        })

    # Missing empty_cache
    if re.search(r"\.cuda\(\)|\.to\(['\"]cuda", code) and not re.search(r"empty_cache", code):
        findings.append({
            "type": "gpu_memory",
            "title": "Missing torch.cuda.empty_cache() after batch inference",
            "current_estimate": "Fragmented VRAM accumulates between requests",
            "optimized_estimate": "VRAM returned to pool after each batch",
            "saving_mb": 256.0,
            "saving": "~256 MB per batch cycle",
            "code_fix": "torch.cuda.empty_cache()  # Add after inference loop",
        })

    # N+1 embedding calls
    if re.search(r"for .+ in .+:\s*\n.*(embed|encode)\(", code, re.DOTALL):
        findings.append({
            "type": "throughput",
            "title": "N+1 Embedding Calls — Should Batch",
            "current_estimate": "1 GPU kernel launch per item",
            "optimized_estimate": "1 GPU kernel launch per batch",
            "saving_mb": 0.0,
            "saving": "Up to 50x latency reduction",
            "code_fix": "embeddings = model.encode(all_texts, batch_size=32)  # Batch all at once",
        })

    return findings


# ──────────────────────────────────────────────
# Benchmark runner
# ──────────────────────────────────────────────

class BenchmarkResult:
    def __init__(self) -> None:
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.ttff_seconds: float = 0.0  # time to first finding
        self.total_seconds: float = 0.0
        self.tokens_processed: int = 0
        self.findings_count: int = 0

    @property
    def tokens_per_second(self) -> float:
        if self.total_seconds > 0 and self.tokens_processed > 0:
            return self.tokens_processed / self.total_seconds
        return 0.0

    def to_dict(self) -> Dict:
        return {
            "ttff_seconds": round(self.ttff_seconds, 3),
            "total_analysis_seconds": round(self.total_seconds, 3),
            "tokens_processed": self.tokens_processed,
            "tokens_per_second": round(self.tokens_per_second, 1),
            "findings_count": self.findings_count,
        }


def start_benchmark() -> BenchmarkResult:
    result = BenchmarkResult()
    result.start_time = time.perf_counter()
    return result


def record_first_finding(result: BenchmarkResult) -> None:
    if result.ttff_seconds == 0.0:
        result.ttff_seconds = time.perf_counter() - result.start_time


def finish_benchmark(result: BenchmarkResult, tokens: int = 0, findings: int = 0) -> BenchmarkResult:
    result.end_time = time.perf_counter()
    result.total_seconds = result.end_time - result.start_time
    result.tokens_processed = tokens
    result.findings_count = findings
    return result

"""
Performance Agent — GPU memory, latency and ROCm optimisation analyser.
Identifies ML-specific inefficiencies in code running on AMD MI300X.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from api.models import PerformanceFinding, OptimizationType
from tools.code_parser import FileEntry, build_context_block
from tools.benchmark_tool import analyse_memory_optimisations

logger = logging.getLogger(__name__)

PERFORMANCE_SYSTEM_PROMPT = """You are CodeSentry Performance Agent — an AMD ROCm GPU performance engineer specialising in ML systems.

Analyse the provided code for performance issues specific to AI/ML workloads on AMD MI300X (192 GB HBM3).

## Check these categories (MANDATORY):

### GPU Memory Issues:
- Tensors allocated on GPU never moved back to CPU or deleted → VRAM leak
- Missing torch.cuda.empty_cache() / hip.device_synchronize() after batch inference
- Model loaded in float32 when float16/bfloat16 suffices → 2x VRAM waste
- Gradient tracking enabled during inference (missing @torch.no_grad or torch.inference_mode)
- KV cache not bounded → unbounded context growth

### Latency Issues:
- Model weights loaded inside per-request handler (should be singleton loaded at startup)
- Synchronous blocking calls inside async endpoints
- Tokenizer instantiated per-request instead of pre-loaded
- Missing torch.compile() for repeated inference patterns

### Throughput Issues:
- N+1 embedding calls: embed() called in a loop instead of batching all inputs
- Sequential agent calls that could be parallelised
- Missing continuous batching configuration in vLLM serving
- Single-worker serving when tensor parallelism is available

### ROCm/AMD-Specific:
- Using CUDA-only APIs not available on ROCm (use HIP equivalents)
- Missing HIP_VISIBLE_DEVICES environment configuration
- Not using Flash Attention 2 compatible with ROCm
- Memory bandwidth not maximised (FP8 quantisation available on MI300X)

## Output Format (STRICT JSON ARRAY):
[
  {
    "type": "gpu_memory|latency|throughput",
    "title": "Short descriptive title",
    "current_estimate": "Description of current resource usage",
    "optimized_estimate": "Description after fix",
    "saving_mb": <float MB saved or 0>,
    "saving": "Human-readable saving description",
    "suggestion": "Detailed explanation of the issue",
    "code_fix": "Concrete code fix or snippet",
    "line_number": <integer or null>,
    "file_path": "<filename or null>"
  }
]

Return ONLY the JSON array. If no issues found, return: []
"""


class PerformanceAgent:
    def __init__(
        self,
        vllm_base_url: str = "http://localhost:8080/v1",
        model: str = "Qwen/Qwen2.5-Coder-32B-Instruct",
        api_key: str = "not-needed-local",
        max_tokens: int = 3072,
        temperature: float = 0.05,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = AsyncOpenAI(
            base_url=vllm_base_url,
            api_key=api_key,
        )

    # ─────────────────────────────────────────
    # Static heuristic scan (no LLM)
    # ─────────────────────────────────────────

    def static_scan(self, files: List[FileEntry]) -> List[PerformanceFinding]:
        """Regex-based performance heuristics across all files."""
        findings: List[PerformanceFinding] = []

        for file_path, code in files:
            heuristic_results = analyse_memory_optimisations(code)
            for r in heuristic_results:
                try:
                    opt_type = OptimizationType(r["type"])
                except ValueError:
                    opt_type = OptimizationType.gpu_memory

                findings.append(
                    PerformanceFinding(
                        type=opt_type,
                        title=f"[Static] {r['title']}",
                        current_estimate=r.get("current_estimate"),
                        optimized_estimate=r.get("optimized_estimate"),
                        saving_mb=r.get("saving_mb", 0.0),
                        saving=r.get("saving"),
                        description=r.get("suggestion", ""),
                        suggestion=r.get("code_fix", ""),
                        file=file_path,
                    )
                )

            # Additional per-file checks
            findings.extend(self._check_model_loading_in_handler(code, file_path))
            findings.extend(self._check_n_plus_one_loop(code, file_path))
            findings.extend(self._check_fp32_usage(code, file_path))

        return findings

    def _check_model_loading_in_handler(self, code: str, file_path: str) -> List[PerformanceFinding]:
        """Detect model loading inside route/request handlers."""
        results: List[PerformanceFinding] = []
        # Find route decorators followed by from_pretrained within ~20 lines
        lines = code.splitlines()
        in_handler = False
        handler_start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"@(app|router)\.(get|post|put|delete|patch)", stripped):
                in_handler = True
                handler_start = i + 1
            if in_handler and re.search(r"from_pretrained|AutoModel|AutoTokenizer", stripped):
                if i - handler_start < 25:
                    results.append(
                        PerformanceFinding(
                            type=OptimizationType.latency,
                            title="[Static] Model loaded inside request handler",
                            current_estimate="Model weights loaded on every request (~10-30s cold start)",
                            optimized_estimate="Model singleton pre-loaded at startup (<1ms per request)",
                            saving_mb=0.0,
                            saving="Eliminates per-request load latency",
                            description="Model loaded once at startup using a global singleton or lifespan event.",
                            suggestion=(
                                "# At module level:\n"
                                "model = AutoModel.from_pretrained(...)\n\n"
                                "# In handler: use the pre-loaded `model`"
                            ),
                            line=i + 1,
                            file=file_path,
                        )
                    )
                in_handler = False
        return results

    def _check_n_plus_one_loop(self, code: str, file_path: str) -> List[PerformanceFinding]:
        """Detect embedding/encode calls inside for loops."""
        results: List[PerformanceFinding] = []
        lines = code.splitlines()
        for i, line in enumerate(lines):
            if re.match(r"\s*for\s+\w+\s+in\s+", line):
                # Check next 5 lines for embed/encode calls
                lookahead = "\n".join(lines[i + 1 : i + 6])
                if re.search(r"\.(embed|encode|get_embedding)\(", lookahead):
                    results.append(
                        PerformanceFinding(
                            type=OptimizationType.throughput,
                            title="[Static] N+1 embedding calls in loop",
                            current_estimate="1 GPU kernel launch per item",
                            optimized_estimate="1 GPU kernel launch for all items",
                            saving_mb=0.0,
                            saving="Up to 50x throughput improvement",
                            description=(
                                "Embedding model called inside a loop. "
                                "Collect all inputs first, then batch-encode in one call."
                            ),
                            suggestion=(
                                "# Instead of:\n"
                                "for text in texts:\n"
                                "    emb = model.encode(text)\n\n"
                                "# Use:\n"
                                "embeddings = model.encode(texts, batch_size=32)"
                            ),
                            line=i + 1,
                            file=file_path,
                        )
                    )
        return results

    def _check_fp32_usage(self, code: str, file_path: str) -> List[PerformanceFinding]:
        """Flag explicit float32 usage where bfloat16 would suffice."""
        results: List[PerformanceFinding] = []
        lines = code.splitlines()
        for i, line in enumerate(lines):
            if re.search(r"torch\.float32|torch_dtype\s*=\s*torch\.float32|\.float\(\)", line):
                if not re.search(r"#.*noqa|#.*keep-fp32", line, re.IGNORECASE):
                    results.append(
                        PerformanceFinding(
                            type=OptimizationType.gpu_memory,
                            title="[Static] FP32 dtype — should use BF16",
                            current_estimate="4 bytes/param (float32)",
                            optimized_estimate="2 bytes/param (bfloat16) — 50% VRAM saving",
                            saving_mb=None,
                            saving="~50% VRAM reduction on MI300X",
                            description="AMD MI300X supports bfloat16 natively with no accuracy loss for inference.",
                            suggestion=(
                                "# Replace:\n"
                                "model = model.float()\n"
                                "# With:\n"
                                "model = model.to(torch.bfloat16)  # or torch_dtype=torch.bfloat16"
                            ),
                            line=i + 1,
                            file=file_path,
                        )
                    )
        return results

    # ─────────────────────────────────────────
    # LLM analysis
    # ─────────────────────────────────────────

    async def llm_scan(self, code_context: str) -> List[PerformanceFinding]:
        """Deep LLM-based performance analysis."""
        user_message = (
            "Analyse the following codebase for GPU memory, latency, and throughput issues "
            "on AMD MI300X hardware:\n\n"
            f"```\n{code_context}\n```\n\n"
            "Return ONLY the JSON array of performance findings."
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": PERFORMANCE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            raw = response.choices[0].message.content or "[]"
            return self._parse_llm_response(raw)
        except Exception as exc:
            logger.error("[PerformanceAgent] LLM call failed: %s", exc)
            return []

    async def analyze(
        self,
        files: List[FileEntry],
        code_context: str,
        use_llm: bool = True,
    ) -> List[PerformanceFinding]:
        """Full pipeline: static heuristics + LLM deep analysis."""
        static = self.static_scan(files)
        logger.info("[PerformanceAgent] Static scan: %d findings", len(static))

        if not use_llm:
            return static

        llm_findings = await self.llm_scan(code_context)
        logger.info("[PerformanceAgent] LLM scan: %d findings", len(llm_findings))

        # Merge: deduplicate by title
        llm_titles = {f.title for f in llm_findings}
        merged = list(llm_findings)
        for f in static:
            clean_title = f.title.replace("[Static] ", "")
            if clean_title not in llm_titles:
                merged.append(f)

        return merged

    # ─────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────

    def _parse_llm_response(self, raw: str) -> List[PerformanceFinding]:
        raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        try:
            data: List[Dict] = json.loads(raw[start:end])
        except json.JSONDecodeError:
            return []

        findings: List[PerformanceFinding] = []
        for item in data:
            try:
                opt_type_str = item.get("type", "gpu_memory")
                try:
                    opt_type = OptimizationType(opt_type_str)
                except ValueError:
                    opt_type = OptimizationType.gpu_memory

                findings.append(
                    PerformanceFinding(
                        type=opt_type,
                        title=item.get("title", "Unknown"),
                        current_estimate=item.get("current_estimate"),
                        optimized_estimate=item.get("optimized_estimate"),
                        saving_mb=item.get("saving_mb"),
                        saving=item.get("saving"),
                        description=item.get("suggestion", ""),
                        suggestion=item.get("code_fix"),
                        line=item.get("line_number"),
                        file=item.get("file_path"),
                        code=item.get("code_snippet"),
                    )
                )
            except Exception as e:
                logger.debug("[PerformanceAgent] Skipping malformed finding: %s", e)
        return findings

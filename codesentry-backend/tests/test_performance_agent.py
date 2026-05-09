"""
Tests for PerformanceAgent — static scan only (no LLM / GPU required).
"""
from __future__ import annotations

import pathlib
import pytest

from agents.performance_agent import PerformanceAgent
from api.models import OptimizationType
from tools.code_parser import FileEntry

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


# ──────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────

@pytest.fixture(scope="module")
def vulnerable_code() -> str:
    return (FIXTURES_DIR / "vulnerable_ml_code.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def clean_code() -> str:
    return (FIXTURES_DIR / "clean_ml_code.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def agent() -> PerformanceAgent:
    return PerformanceAgent()


@pytest.fixture(scope="module")
def vulnerable_files(vulnerable_code: str) -> list[FileEntry]:
    return [("vulnerable_ml_code.py", vulnerable_code)]


@pytest.fixture(scope="module")
def perf_findings(agent: PerformanceAgent, vulnerable_files: list[FileEntry]):
    return agent.static_scan(vulnerable_files)


# ──────────────────────────────────────────
# Inline test code snippets
# ──────────────────────────────────────────

GPU_LEAK_CODE = '''
import torch

model = load_model().cuda()

def infer(text):
    inputs = tokenizer(text, return_tensors="pt").to("cuda")
    outputs = model.generate(**inputs)
    # Tensor never moved to CPU or deleted — memory leak
    return outputs
'''

N_PLUS_ONE_CODE = '''
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
documents = ["doc1", "doc2", "doc3"]
embeddings = []
for doc in documents:
    emb = model.encode(doc)
    embeddings.append(emb)
'''

FP32_CODE = '''
import torch
from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained(
    "gpt2",
    torch_dtype=torch.float32,
)
'''

NO_GRAD_CODE = '''
import torch

model = load_model()

def predict(text):
    inputs = tokenizer(text, return_tensors="pt")
    outputs = model(inputs)
    return outputs.logits.argmax()
'''

BATCHED_CODE = '''
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
documents = ["doc1", "doc2", "doc3"]
# Correct: batch all at once
embeddings = model.encode(documents, batch_size=32)
'''


# ──────────────────────────────────────────
# Tests
# ──────────────────────────────────────────

class TestGPUMemoryLeakDetection:
    def test_detects_gpu_memory_leak(self, agent: PerformanceAgent):
        """Should detect GPU tensor with no corresponding .cpu() or del."""
        files: list[FileEntry] = [("test_leak.py", GPU_LEAK_CODE)]
        findings = agent.static_scan(files)
        gpu_findings = [
            f for f in findings
            if f.type == OptimizationType.gpu_memory
        ]
        assert len(gpu_findings) > 0, "Expected GPU memory finding for tensor not moved to CPU"

    def test_no_leak_with_empty_cache(self, agent: PerformanceAgent):
        """Code that calls empty_cache should produce fewer GPU memory warnings."""
        clean_gpu_code = GPU_LEAK_CODE + "\ntorch.cuda.empty_cache()\n"
        files: list[FileEntry] = [("clean_gpu.py", clean_gpu_code)]
        findings = agent.static_scan(files)
        # Should have fewer findings because empty_cache is present
        without_cache = agent.static_scan([("test.py", GPU_LEAK_CODE)])
        assert len(findings) <= len(without_cache)


class TestNPlusOneEmbeddings:
    def test_detects_n_plus_one_embeddings(self, agent: PerformanceAgent):
        """Should detect encode() called inside a for-loop."""
        files: list[FileEntry] = [("n_plus_one.py", N_PLUS_ONE_CODE)]
        findings = agent.static_scan(files)
        throughput_findings = [
            f for f in findings
            if f.type == OptimizationType.throughput
            or "n+1" in f.title.lower()
            or "loop" in f.title.lower()
            or "batch" in f.suggestion.lower()
        ]
        assert len(throughput_findings) > 0, (
            "Expected throughput finding for N+1 embedding calls"
        )

    def test_no_n_plus_one_for_batch_code(self, agent: PerformanceAgent):
        """Correctly batched embeddings should not be flagged."""
        files: list[FileEntry] = [("batched.py", BATCHED_CODE)]
        findings = agent.static_scan(files)
        n_plus_one_findings = [
            f for f in findings
            if "n+1" in f.title.lower()
        ]
        assert len(n_plus_one_findings) == 0, "Batched code should not flag N+1"


class TestFP32Inefficiency:
    def test_detects_fp32_inefficiency(self, agent: PerformanceAgent):
        """Should detect torch.float32 / .float() usage."""
        files: list[FileEntry] = [("fp32_code.py", FP32_CODE)]
        findings = agent.static_scan(files)
        fp32_findings = [
            f for f in findings
            if "fp32" in f.title.lower()
            or "float32" in f.title.lower()
            or "bf16" in f.title.lower()
        ]
        assert len(fp32_findings) > 0, "Expected FP32 inefficiency finding"

    def test_fp32_finding_type_is_gpu_memory(self, agent: PerformanceAgent):
        files: list[FileEntry] = [("fp32_code.py", FP32_CODE)]
        findings = agent.static_scan(files)
        fp32_findings = [
            f for f in findings
            if "fp32" in f.title.lower() or "float32" in f.title.lower()
        ]
        if fp32_findings:
            assert fp32_findings[0].type == OptimizationType.gpu_memory


class TestMemorySavingsEstimate:
    def test_estimates_memory_savings(self, perf_findings):
        """At least one finding should report a positive savings_mb value."""
        savings = [f.saving_mb for f in perf_findings if f.saving_mb and f.saving_mb > 0]
        assert len(savings) > 0, (
            "Expected at least one finding with savings_mb > 0"
        )

    def test_total_savings_positive(self, perf_findings):
        total = sum(f.saving_mb or 0 for f in perf_findings)
        assert total > 0, "Total estimated savings should be > 0 MB"


class TestMissingNoGrad:
    def test_detects_missing_no_grad(self, agent: PerformanceAgent):
        """Should detect inference function missing @torch.no_grad."""
        files: list[FileEntry] = [("no_grad.py", NO_GRAD_CODE)]
        findings = agent.static_scan(files)
        no_grad_findings = [
            f for f in findings
            if "no_grad" in f.title.lower()
            or "gradient" in f.suggestion.lower()
        ]
        assert len(no_grad_findings) > 0, "Expected finding for missing @torch.no_grad"


class TestFindingSchema:
    def test_all_performance_findings_have_required_fields(self, perf_findings):
        for i, finding in enumerate(perf_findings):
            assert finding.type is not None, f"Finding {i} missing type"
            assert finding.title, f"Finding {i} missing title"
            assert finding.suggestion, f"Finding {i} missing suggestion"

    def test_vulnerable_code_has_performance_findings(self, perf_findings):
        assert len(perf_findings) > 0, (
            "PerformanceAgent.static_scan() returned no findings for vulnerable code"
        )

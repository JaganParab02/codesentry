"""
Pydantic request/response schemas for CodeSentry API.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class SourceType(str, Enum):
    github = "github"
    huggingface = "huggingface"
    code = "code"
    zip = "zip"


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class OptimizationType(str, Enum):
    gpu_memory = "gpu_memory"
    latency = "latency"
    throughput = "throughput"


# ──────────────────────────────────────────────
# Requests
# ──────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    source: str = Field(..., description="GitHub URL, raw code string, or base64-encoded zip")
    source_type: SourceType = Field(..., description="One of: github | code | zip")
    session_id: str = Field(..., description="UUID to track this analysis session")

    @field_validator("session_id")
    @classmethod
    def session_id_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("session_id must not be empty")
        return v.strip()

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source must not be empty")
        return v.strip()


# ──────────────────────────────────────────────
# Findings
# ──────────────────────────────────────────────

class SecurityFinding(BaseModel):
    id: Optional[str] = None
    agent: str = "security"
    severity: Severity
    title: str
    cwe: Optional[str] = None
    owasp_category: Optional[str] = None
    line: Optional[int] = None
    file: Optional[str] = None
    code: Optional[str] = None
    description: str
    suggestion: Optional[str] = None


class PerformanceFinding(BaseModel):
    id: Optional[str] = None
    agent: str = "performance"
    type: OptimizationType
    title: str
    current_estimate: Optional[str] = None
    optimized_estimate: Optional[str] = None
    saving_mb: Optional[float] = None
    saving: Optional[str] = None
    description: str
    suggestion: Optional[str] = None
    line: Optional[int] = None
    file: Optional[str] = None
    code: Optional[str] = None


class AMDMigrationFindingModel(BaseModel):
    id: str
    title: str
    description: str
    rocm_fix: str
    severity: str
    file: Optional[str] = None
    line: Optional[int] = None
    code_snippet: Optional[str] = None


class AMDMigrationGuide(BaseModel):
    compatibility_score: int = 100
    compatibility_label: str = "Fully ROCm Ready"
    total_cuda_patterns_found: int = 0
    findings: List[AMDMigrationFindingModel] = Field(default_factory=list)
    summary: str = ""


class AMDMetricsSnapshot(BaseModel):
    gpu_utilization_percent: int = 0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 192.0
    temperature_c: int = 0
    power_draw_w: int = 0
    memory_bandwidth_tbs: float = 0.0
    tokens_per_sec: float = 0.0
    timestamp: str = ""


# ──────────────────────────────────────────────
# Fix & Diff
# ──────────────────────────────────────────────

class FindingFix(BaseModel):
    findingId: str
    title: str
    before: str
    after: str
    explanation: str


class FileFix(BaseModel):
    file_path: str
    diff: str
    explanation: str


class FixResult(BaseModel):
    finding_fixes: List[FindingFix] = Field(default_factory=list)
    diffs: List[FileFix] = Field(default_factory=list)
    files_changed: int = 0
    security_report_md: str = ""
    pr_description: str = ""


# ──────────────────────────────────────────────
# Privacy Certificate
# ──────────────────────────────────────────────

class PrivacyCertificate(BaseModel):
    session_id: str
    timestamp: str
    guarantee: str
    model_endpoint: str
    external_calls_blocked: List[str] = Field(default_factory=list)
    data_wiped: bool
    signature: str


# ──────────────────────────────────────────────
# Session / Summary
# ──────────────────────────────────────────────

class AnalysisSummary(BaseModel):
    session_id: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    performance_optimizations: int
    estimated_memory_savings_mb: float
    analysis_duration_seconds: float
    files_analyzed: int


class SessionResult(BaseModel):
    session_id: str
    status: str = "complete"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    summary: Optional[AnalysisSummary] = None
    security_findings: List[SecurityFinding] = Field(default_factory=list)
    performance_findings: List[PerformanceFinding] = Field(default_factory=list)
    fix_result: Optional[FixResult] = None
    privacy_certificate: Optional[PrivacyCertificate] = None
    amd_migration_guide: Optional[AMDMigrationGuide] = None


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    model: str = "Qwen2.5-Coder-32B"
    vllm_ready: bool
    gpu_memory_free_gb: Optional[float] = None
    vllm_endpoint: str = "http://localhost:8080"
    version: str = "1.0.0"
    amd_hardware: Optional[AMDMetricsSnapshot] = None


# ──────────────────────────────────────────────
# SSE Event wrappers (serialisable dicts)
# ──────────────────────────────────────────────

class SSEEvent(BaseModel):
    event: str
    data: Dict[str, Any]

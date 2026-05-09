# 🛡️ CodeSentry Backend

**AI/ML Code Security Analysis Engine — powered by Qwen2.5-Coder-32B on AMD MI300X**

> Zero Data Retention. All inference runs locally. No code leaves your machine.

---

## Overview

CodeSentry is a multi-agent backend that audits AI/ML codebases for security vulnerabilities and performance issues:

- **Security Agent** — OWASP Top-10 + OWASP LLM Top-10 scanning (static regex + LLM deep analysis)
- **Performance Agent** — GPU memory leaks, N+1 embeddings, FP32 waste, missing `@torch.no_grad`
- **Fix Agent** — Generates unified diffs, security reports, and PR descriptions
- **AMD Migration Advisor** — 10-category CUDA → ROCm/HIP compatibility scanner with AMD Compatibility Score
- **AMD Metrics Collector** — Real-time MI300X GPU monitoring via `rocm-smi` (with simulated fallback)
- **Privacy Guard** — Blocks outbound connections, generates cryptographically signed ZDR certificates

**Model stack:** `Qwen/Qwen2.5-Coder-32B-Instruct` via vLLM on AMD MI300X (192 GB HBM3)

---

## Quick Start

### 1. Setup vLLM on AMD MI300X

```bash
cd codesentry-backend
chmod +x scripts/setup_vllm.sh
./scripts/setup_vllm.sh
```

This installs vLLM with ROCm backend, starts the model server, and launches the CodeSentry API.

### 2. Manual startup

```bash
# Copy and configure environment
cp .env.example .env

# Install dependencies
pip install -r requirements.txt

# Start vLLM (in background)
vllm serve Qwen/Qwen2.5-Coder-32B-Instruct \
  --port 8080 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768 &

# Start CodeSentry API
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## API Reference

### `GET /api/health`

Check service status, GPU memory, and live AMD hardware metrics.

```bash
curl http://localhost:8000/api/health
```

**Response:**
```json
{
  "status": "ok",
  "model": "Qwen/Qwen2.5-Coder-32B-Instruct",
  "vllm_ready": true,
  "gpu_memory_free_gb": 142.5,
  "vllm_endpoint": "http://localhost:8080",
  "amd_hardware": {
    "gpu_utilization_percent": 85,
    "vram_used_gb": 48.2,
    "vram_total_gb": 192.0,
    "temperature_c": 63,
    "power_draw_w": 612,
    "memory_bandwidth_tbs": 4.7,
    "tokens_per_sec": 1250,
    "timestamp": "2026-05-09T13:30:00Z"
  }
}
```

---

### `POST /api/scan` & `GET /api/scan/stream/{session_id}` — SSE Stream

Analyse a codebase. Returns a Server-Sent Events stream.

```bash
# Analyse a GitHub repository (creates scan session)
curl -X POST http://localhost:8000/api/scan \
  -H "Content-Type: application/json" \
  -d '{
    "source": "https://github.com/example/vulnerable-ml-app",
    "source_type": "github",
    "session_id": "test-123"
  }'

# Stream the results
curl -N http://localhost:8000/api/scan/stream/test-123
```

**SSE Events:**
```
event: status
data: {"message": "Ingesting code...", "session_id": "test-123"}

event: agent_start
data: {"agent": "security", "status": "scanning"}

event: finding
data: {"severity": "critical", "title": "Insecure Pickle Deserialization", "cwe": "CWE-502", "line_number": 2}

event: amd_metrics
data: {"gpu_utilization_percent": 87, "vram_used_gb": 48.2, "vram_total_gb": 192.0, "temperature_c": 63, ...}

event: agent_start
data: {"agent": "performance", "status": "analyzing"}

event: finding
data: {"agent": "performance", "type": "gpu_memory", "saving_mb": 3584, "suggestion": "Switch from FP32 to BF16"}

event: amd_migration_finding
data: {"id": "AMD_M02", "title": "NVIDIA-Specific CLI Tool", "severity": "critical", "rocm_fix": "..."}

event: amd_migration_summary
data: {"compatibility_score": 72, "compatibility_label": "Mostly Compatible", "total_cuda_patterns_found": 3}

event: fix_ready
data: {"findingId": "SEC-STATIC-1", "title": "Fix pickle.load", "before": "...", "after": "..."}

event: complete
data: {"summary": {...}, "privacy_certificate": {...}, "amd_migration_guide": {...}}
```

---

### `POST /api/analyze/demo`

Pre-computed result from the vulnerable fixture. **No GPU required.** For frontend development and CI.

```bash
curl -X POST http://localhost:8000/api/analyze/demo | python -m json.tool
```

---

### `GET /api/session/{session_id}`

Retrieve the full analysis result for a completed session (includes `amd_migration_guide`).

```bash
curl http://localhost:8000/api/session/test-123
```

---

### `GET /api/privacy-certificate/{session_id}`

Get the Zero Data Retention audit certificate for a session.

```bash
curl http://localhost:8000/api/privacy-certificate/test-123
```

**Response:**
```json
{
  "session_id": "test-123",
  "timestamp": "2024-01-01T00:00:00+00:00",
  "guarantee": "All inference ran exclusively on localhost AMD MI300X via vLLM. Zero data transmitted to external services.",
  "model_endpoint": "http://localhost:8080",
  "external_calls_blocked": [],
  "data_wiped": true,
  "signature": "a3f8d2..."
}
```

---

## Running Tests

```bash
# Install test dependencies and run all tests (no GPU required)
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh

# Or directly with pytest
export USE_LLM=false
pytest tests/ -v --asyncio-mode=auto
```

All 15+ tests use **static analysis only** — no GPU or vLLM server needed.

---

## Benchmarking

```bash
# Requires running API at localhost:8000
chmod +x scripts/benchmark.sh
./scripts/benchmark.sh

# Custom URL and run count
CODESENTRY_URL=http://localhost:8000 BENCHMARK_RUNS=5 ./scripts/benchmark.sh
```

Outputs `benchmark_results.json` with TTFF, total latency, and findings statistics.

---

## Project Structure

```
codesentry-backend/
├── main.py                    # FastAPI app entry point
├── amd_metrics.py             # AMD MI300X live metrics (rocm-smi + simulated fallback)
├── api/
│   ├── routes.py              # All API endpoints
│   └── models.py              # Pydantic request/response schemas
├── agents/
│   ├── orchestrator.py        # Master agent (coordinates all sub-agents, SSE)
│   ├── security_agent.py      # OWASP + OWASP-LLM-Top-10 scanner
│   ├── performance_agent.py   # GPU memory, latency, ROCm optimisation
│   ├── fix_agent.py           # Code fixes, diffs, security report
│   └── amd_migration_advisor.py  # CUDA → ROCm migration (10 pattern categories)
├── tools/
│   ├── code_parser.py         # AST parsing, GitHub/zip/string ingestion
│   ├── github_connector.py    # GitHub shallow clone
│   ├── vulnerability_db.py    # OWASP knowledge base + regex patterns
│   ├── diff_generator.py      # Unified diff generation
│   └── benchmark_tool.py      # GPU memory estimation + timing
├── privacy/
│   └── privacy_guard.py       # ZDR enforcement + HMAC certificates
├── memory/
│   └── session_store.py       # In-memory TTL session store
├── tests/
│   ├── fixtures/
│   │   ├── vulnerable_ml_code.py  # Deliberately vulnerable ML app
│   │   ├── clean_ml_code.py       # Secure baseline
│   │   └── expected_findings.json # Ground truth for assertions
│   ├── test_security_agent.py
│   ├── test_performance_agent.py
│   ├── test_api_endpoints.py
│   └── test_privacy_guard.py
├── scripts/
│   ├── setup_vllm.sh          # One-command AMD MI300X setup
│   ├── run_tests.sh           # Full test suite runner
│   └── benchmark.sh           # Latency + throughput benchmark
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VLLM_BASE_URL` | `http://localhost:8080/v1` | vLLM OpenAI-compatible endpoint |
| `MODEL_NAME` | `Qwen/Qwen2.5-Coder-32B-Instruct` | Model served by vLLM |
| `USE_LLM` | `true` | Set `false` for static-only mode (CI) |
| `PORT` | `8000` | CodeSentry API port |
| `CORS_ORIGINS` | `*` | Allowed frontend origins |
| `ZDR_SIGNING_KEY` | (dev default) | HMAC key for certificates — **change in production** |
| `GROQ_API_KEY` | — | Groq cloud API key (alternative to local vLLM) |

---

## Zero Data Retention

Every analysis session runs inside a `ZeroDataRetentionGuard` that:

1. **Blocks** all outbound non-localhost network connections at the socket level
2. **Logs** any blocked connection attempts to the audit trail
3. **Wipes** all session data from memory after the analysis completes
4. **Generates** a cryptographically signed audit certificate

The certificate is available at `GET /api/privacy-certificate/{session_id}`.

---

## Vulnerability Coverage

### Security (OWASP)

| Category | ID | Description |
|---|---|---|
| OWASP LLM | LLM01 | Prompt Injection |
| OWASP LLM | LLM02 | Insecure Output Handling (eval, exec) |
| OWASP LLM | LLM03 | Training Data Poisoning |
| OWASP LLM | LLM04 | Model Denial of Service |
| OWASP LLM | LLM06 | Sensitive Information Disclosure |
| OWASP LLM | LLM08 | Excessive Agency |
| OWASP LLM | LLM09 | Overreliance |
| OWASP Web | A01 | Broken Access Control |
| OWASP Web | A02 | Cryptographic Failures |
| OWASP Web | A03 | SQL Injection |
| OWASP Web | A04 | Insecure Deserialization (CWE-502) |
| OWASP Web | A05 | Security Misconfiguration |
| OWASP Web | A07 | Hardcoded Credentials |
| OWASP Web | A08 | Software & Data Integrity Failures |
| OWASP Web | A10 | Server-Side Request Forgery |
| ML-Specific | ML01 | GPU Memory Leak |
| ML-Specific | ML02 | Missing `@torch.no_grad` |
| ML-Specific | ML03 | N+1 Embedding Calls |
| ML-Specific | ML04 | FP32 vs BF16 Inefficiency |
| ML-Specific | ML05 | Synchronous Model Loading in Handler |

### AMD Migration (CUDA → ROCm)

| ID | Severity | Description |
|---|---|---|
| AMD_M01 | Low | `torch.cuda.is_available()` — CUDA device check |
| AMD_M02 | Critical | `nvidia-smi` — NVIDIA-only CLI tool |
| AMD_M03 | High | `CUDA_VISIBLE_DEVICES` — CUDA env variable |
| AMD_M04 | High | `torch.cuda.amp.autocast/GradScaler` — Legacy CUDA AMP |
| AMD_M05 | Medium | `.half()` / `torch.float16` — FP16 suboptimal on MI300X |
| AMD_M06 | Medium | `torch.backends.cudnn.*` — cuDNN configuration |
| AMD_M07 | High | `import flash_attn` — CUDA-only Flash Attention |
| AMD_M08 | Low | `torch.cuda.memory_allocated()` — CUDA memory profiling |
| AMD_M09 | Low | `device = 'cuda'` — Hardcoded device string |
| AMD_M10 | Critical | `BitsAndBytesConfig` — CUDA-only quantization |

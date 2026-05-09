# 🛡️ CodeSentry

> **CodeSentry** is an enterprise-grade, agentic AI security and performance copilot designed to seamlessly analyze codebases, identify critical vulnerabilities, and generate intelligent, ready-to-merge patches — with built-in CUDA → ROCm migration guidance for AMD hardware.

Built with a strict **Zero Data Retention (ZDR)** architecture, CodeSentry ensures that your proprietary code never leaves your secure environment or gets used for model training, making it perfect for highly sensitive, enterprise-scale environments.

---

## ✨ Key Features

- **🧠 Agentic Pipeline:** CodeSentry uses a multi-agent orchestration architecture:
  - **Security Agent:** Combines lightning-fast static analysis with deep semantic LLM reasoning to catch complex vulnerabilities (e.g., prompt injections, hardcoded secrets, unsafe deserialization).
  - **Performance Agent:** Specifically tailored to analyze ML/AI logic. It detects GPU memory bottlenecks, inefficient loop structures, and suggests hardware-native optimizations (like `bfloat16` for AMD MI300X).
  - **Fix Agent:** Automatically generates unified Git-style diffs and line-by-line patch recommendations for every finding.
  - **AMD Migration Advisor:** Scans for 10 categories of CUDA-specific patterns (nvidia-smi, CUDA_VISIBLE_DEVICES, BitsAndBytes, cuDNN, FP16 usage, etc.) and provides actionable ROCm/HIP migration guidance with a 0–100 AMD Compatibility Score.
- **⚡ AMD MI300X Live Metrics:** Real-time GPU performance monitoring (utilization, VRAM, temperature, power draw, inference speed) streamed to the dashboard during every scan via SSE. Uses `rocm-smi` on AMD hardware, with simulated fallback for development environments.
- **🔒 Zero Data Retention (ZDR):** Every analysis session generates a unique cryptographic Privacy Certificate. The backend actively blocks outgoing network calls during the scan and wipes all data from memory the millisecond the scan completes.
- **⚡ Real-Time Streaming:** The analysis engine uses Server-Sent Events (SSE) to stream findings to the frontend instantaneously, creating a highly responsive "live" dashboard experience.
- **📋 One-Click Reporting:** Export full `SECURITY_REPORT.md` documents, structured JSON audit logs, copy-paste ready GitHub Pull Request descriptions, and `AMD_MIGRATION_GUIDE.md` reports.

---

## 🏗️ System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      CODESENTRY FRONTEND                         │
│           React + Vite | Cyberpunk Terminal Aesthetic            │
│  LandingPage → AnalysisView (SSE Live Feed) → ReportView        │
│         ┌───────────────────┐  ┌────────────────────────┐       │
│         │ AMD MI300X Live   │  │ AMD Migration Advisor  │       │
│         │ Metrics Card      │  │ Panel + Score Circle   │       │
│         └───────────────────┘  └────────────────────────┘       │
└─────────────────────────────┬────────────────────────────────────┘
                              │  SSE (Server-Sent Events) + REST
┌─────────────────────────────▼────────────────────────────────────┐
│                       CODESENTRY BACKEND                         │
│                        FastAPI / Python                          │
│                                                                  │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────────┐  │
│  │  Security   │  │  Performance     │  │    Fix Agent       │  │
│  │  Agent      │  │  Agent           │  │ (patches + diffs)  │  │
│  └──────┬──────┘  └────────┬─────────┘  └────────┬───────────┘  │
│         │          ┌───────▼────────┐            │              │
│         │          │ AMD Migration  │            │              │
│         │          │ Advisor (10    │            │              │
│         │          │ CUDA patterns) │            │              │
│         │          └───────┬────────┘            │              │
│         └─────────────────►│◄────────────────────┘              │
│                     ┌──────▼──────┐                              │
│                     │ Orchestrator│                              │
│                     └──────┬──────┘                              │
│                            │                                     │
│  ┌──────────────────────────▼───────────────────────────────┐   │
│  │ Privacy Guard │ Session Store │ AMD Metrics │ Code Parser │   │
│  └──────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                     ┌──────▼──────┐                              │
│                     │  vLLM Server│ (Qwen2.5-Coder-32B)         │
│                     └─────────────┘                              │
└──────────────────────────────────────────────────────────────────┘
```

The project is divided into two main components:

### 1. The Backend (`/codesentry-backend`)
A high-performance **FastAPI** server that acts as the orchestrator. 
- Ingests code via GitHub URLs, Hugging Face Spaces URLs, Zip files, or raw code snippets.
- Manages the stateful analysis session and memory lifecycle.
- Runs **AMD MI300X live metrics polling** via `rocm-smi` (with simulated fallback for dev environments).
- Runs the **AMD Migration Advisor** to detect CUDA-specific patterns and calculate an AMD Compatibility Score.
- Connects to an LLM endpoint (optimized for local deployment via `vLLM` on AMD hardware, using Qwen2.5-Coder-32B) to power the intelligent agents.

### 2. The Frontend (`/codesentry-frontend`)
A modern **React + Vite** dashboard built with a premium, cyberpunk-inspired terminal aesthetic.
- Connects to the backend via SSE for live streaming.
- Features the **AMD MI300X Live Performance Card** in the Analysis View — 6 GPU metrics updated every 2 seconds.
- Features the **AMD ROCm Migration Advisor Panel** in the Report View — animated score circle, collapsible findings, and one-click `AMD_MIGRATION_GUIDE.md` export.
- Dynamic data visualization, animated severity charts, and side-by-side Before/After code diffing for AI-generated fixes.

---

## 🔴 AMD-Specific Features

### Live Hardware Metrics (Analysis View)
During every scan, CodeSentry polls the AMD MI300X GPU via `rocm-smi` and streams live metrics to the dashboard:

| Metric | Description |
|--------|-------------|
| GPU Utilization | Current compute load (%) |
| VRAM Used | GB used / 192 GB total with visual bar |
| Memory Bandwidth | TB/s data throughput |
| Temperature | GPU edge temperature (°C) |
| Power Draw | Current wattage consumption (W) |
| Inference Speed | LLM tokens per second |

> On development machines without AMD hardware, the card displays realistic simulated values.

### CUDA → ROCm Migration Advisor (Report View)
The Migration Advisor scans code for 10 categories of CUDA-specific patterns:

| ID | Severity | What It Detects |
|----|----------|-----------------|
| AMD_M01 | Low | `torch.cuda.is_available()` — CUDA device check |
| AMD_M02 | **Critical** | `nvidia-smi` — NVIDIA-only CLI tool |
| AMD_M03 | High | `CUDA_VISIBLE_DEVICES` — CUDA env variable |
| AMD_M04 | High | `torch.cuda.amp.autocast/GradScaler` — Legacy CUDA AMP |
| AMD_M05 | Medium | `.half()` / `torch.float16` — FP16 suboptimal on MI300X |
| AMD_M06 | Medium | `torch.backends.cudnn.*` — cuDNN configuration |
| AMD_M07 | High | `import flash_attn` — CUDA-only Flash Attention |
| AMD_M08 | Low | `torch.cuda.memory_allocated()` — CUDA memory profiling |
| AMD_M09 | Low | `device = 'cuda'` — Hardcoded device string |
| AMD_M10 | **Critical** | `BitsAndBytesConfig` — CUDA-only quantization |

**Compatibility Scoring:**
```
≥ 90% → "Fully ROCm Ready" (green)
≥ 70% → "Mostly Compatible" (yellow)  
≥ 50% → "Needs Migration Work" (orange)
< 50% → "CUDA-Specific Codebase" (red)
```

---

## 💡 How It Works (An Example Workflow)

To understand CodeSentry, imagine you have a Python scraping script that takes user input and feeds it into an LLM.

1. **Initiate Scan:** You paste the GitHub or Hugging Face Space URL of the script into the CodeSentry dashboard.
2. **Live GPU Monitoring:** The AMD MI300X Live Performance card immediately starts showing real-time GPU utilization, VRAM usage, temperature, and inference speed.
3. **Security Sweep:** The Security Agent immediately flags `cli.py:61` for a **Prompt Injection** (CWE-74) vulnerability because it detects raw user input being passed to the model without sanitization.
4. **Performance Sweep:** The Performance Agent notices the code is loading a large transformer model inside a loop. It flags this and estimates you are wasting significant inference time.
5. **AMD Migration Scan:** The Migration Advisor detects `nvidia-smi` calls and `CUDA_VISIBLE_DEVICES` usage, calculating an AMD Compatibility Score and suggesting `rocm-smi` and `HIP_VISIBLE_DEVICES` replacements.
6. **Fix Generation:** The Fix Agent takes these findings and writes a patch. It refactors the prompt injection to use a parameterized template and hoists the model initialization outside the loop.
7. **Review:** You view the dashboard. The findings are categorized by severity. You click on the Prompt Injection finding, and an AI-Generated Fix panel opens showing exactly what lines to change. The AMD Migration Panel shows your compatibility score with collapsible fix guidance.
8. **Export:** You click "Copy PR Description" and paste a perfectly formatted summary of the fixes directly into your GitHub Pull Request. You also export the `AMD_MIGRATION_GUIDE.md` for your DevOps team.

---

## 🚀 Installation & Setup

### Prerequisites
- Node.js (v20.19+ or v22.12+)
- Python (v3.10+)
- An API Key for your LLM provider (e.g., Groq) if not running a completely local vLLM instance.

### 1. Backend Setup

Open a terminal and navigate to the backend directory:

```bash
cd codesentry-backend

# Create and activate a virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure Environment Variables
# Create a .env file based on the example and add your LLM_API_KEY
cp .env.example .env

# Run the backend server
uvicorn main:app --reload --port 8000
```
*The backend will now be running on `http://127.0.0.1:8000`.*

### 2. Frontend Setup

Open a second terminal and navigate to the frontend directory:

```bash
cd codesentry-frontend

# Install dependencies
npm install

# Ensure VITE_MOCK_MODE is set to false to connect to the live backend
echo "VITE_MOCK_MODE=false" > .env

# Run the development server
npm run dev
```
*The dashboard will be available at `http://127.0.0.1:5173`.*

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VLLM_BASE_URL` | `http://localhost:8080/v1` | vLLM OpenAI-compatible endpoint |
| `MODEL_NAME` | `Qwen/Qwen2.5-Coder-32B-Instruct` | Model served by vLLM |
| `USE_LLM` | `true` | Set `false` for static-only mode (CI) |
| `PORT` | `8000` | CodeSentry API port |
| `CORS_ORIGINS` | `*` | Allowed frontend origins |
| `ZDR_SIGNING_KEY` | (dev default) | HMAC key for certificates — **change in production** |
| `GROQ_API_KEY` | — | Groq cloud API key (alternative to local vLLM) |
| `VITE_MOCK_MODE` | `false` | Frontend: use mock data instead of live backend |
| `VITE_API_URL` | `http://localhost:8000` | Frontend: backend base URL |

---

## 📊 SSE Event Types

| Event | Description |
|-------|-------------|
| `scan_started` | Scan session created, ID returned |
| `agent_start` | An agent begins (security / performance / fix) |
| `finding` | A security or performance vulnerability found |
| `fix_ready` | A fix patch generated for a specific finding |
| `amd_metrics` | Live AMD MI300X GPU metrics snapshot (every 2s) |
| `amd_migration_finding` | A CUDA → ROCm migration issue detected |
| `amd_migration_summary` | Compatibility score and summary |
| `complete` | Full analysis finished with summary + certificates |
| `error` | An error occurred during analysis |

---

## 📦 Export Formats

| Format | Description |
|--------|-------------|
| 📄 **JSON Report** | Machine-readable full report with all findings and fixes |
| 📝 **SECURITY_REPORT.md** | Human-readable markdown security report |
| 📋 **Copy PR Description** | GitHub Pull Request description copied to clipboard |
| 🔴 **AMD_MIGRATION_GUIDE.md** | AMD ROCm migration guide with score, findings, and fixes |

---

## 🔐 Built for the AMD Hackathon

CodeSentry was specifically designed to showcase the power of **Agentic AI** running on high-performance AMD MI300X compute hardware. By combining a suite of specialized agents with real-time GPU monitoring and CUDA → ROCm migration guidance, we shift the paradigm of static code analysis from "reporting problems" to "actively writing solutions."

**Zero Data Retention. 100% Agentic. AMD-Optimized. Enterprise Ready.**

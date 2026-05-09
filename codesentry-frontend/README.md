## 🛡️ CodeSentry Frontend — AI Security Copilot

> AMD Developer Hackathon 2026 — Track 1: AI Agents & Agentic Workflows

**CodeSentry** is an enterprise-grade AI security intelligence platform. Built for the modern agentic workflow, it orchestrates multiple specialized AI agents to scan, analyze, and remediate security threats in real-time.

---

## ⚡ Why CodeSentry?

In an era of AI-generated code, vulnerabilities move faster than human reviewers. CodeSentry provides:

- **Agentic Intelligence**: Not just a static scanner. Three specialized agents (Security, Performance, Fix) reason over your code like a senior security team.
- **Cinematic Experience**: A futuristic SOC-style dashboard designed for high-stakes security monitoring.
- **AMD MI300X Live Metrics**: Real-time hardware telemetry (GPU Util, VRAM, Temp, Power, Bandwidth) streamed directly to the dashboard.
- **CUDA → ROCm Migration Advisor**: Scans code for CUDA-specific patterns and provides actionable ROCm migration guidance with an AMD Compatibility Score.
- **Privacy-First**: Optimized for the AMD ecosystem, ensuring high-performance local inference. Your proprietary code never leaves your network.
- **Instant Remediation**: Don't just find bugs—fix them. Get PR-ready patches in seconds.

---

## ✨ Demo Flow

1. **Clone** this repo
2. **Run** `npm install && npm run dev`
3. **Open** `http://localhost:5173`
4. **Click** "Launch Security Scan" — demo runs in mock mode with no backend needed. You will see simulated AMD metrics and migration findings!

---

## 🏗️ Architecture

```
Frontend (Vite + React)     Backend (FastAPI + Python)
┌────────────────────┐      ┌──────────────────────────┐
│  Landing Page      │      │  POST /api/scan           │
│  Analysis View  ───┼─SSE──│  GET  /api/scan/stream   │
│  Report Page       │      │                          │
└────────────────────┘      │  Security Agent          │
                            │  Performance Agent       │
                            │  AMD Migration Advisor   │
                            │  Fix Agent               │
                            │  AMD Metrics Collector   │
                            └──────────────────────────┘
```

## 🤖 AI Agents & Tools

| Component | Responsibilities | Output |
|-----------|-----------------|--------|
| **Security Agent** | SQL injection, hardcoded secrets, unsafe eval, pickle deserialization, weak hashing | CWE-mapped findings with severity |
| **Performance Agent** | N+1 queries, memory leaks, GPU inefficiencies, FP32 waste | Optimization suggestions |
| **Fix Agent** | Generates before/after patches for all fixable findings | Downloadable diffs |
| **AMD Migration Advisor** | Detects CUDA APIs (nvidia-smi, cudnn, etc) | Compatibility score + ROCm fixes |
| **AMD Metrics Collector**| Polls `rocm-smi` every 2s for hardware stats | Real-time GPU telemetry |

---

## 🚀 Quick Start

### Frontend Only (Mock Mode — demo-safe)
```bash
npm install
npm run dev
# Open http://localhost:5173
# VITE_MOCK_MODE=true by default
```

### Full Stack (Frontend + Backend)
```bash
# Terminal 1 — Frontend
npm install && npm run dev

# Terminal 2 — Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Then set in .env:
# VITE_MOCK_MODE=false
```

---

## 🔧 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_MOCK_MODE` | `true` | Use mock data (no backend needed) |
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL |

---

## 🔒 Privacy-First Design

- **Zero data retention** — no code stored after session
- **Local inference** — all analysis on-device via vLLM
- **No external API calls** — code never leaves your machine
- **Session data wiped** on completion
- **Cryptographic Audit** — signed ZDR certificates generated

---

## 🎨 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vite + React 18 |
| Styling | Vanilla CSS with custom design system (`index.css`) |
| Charts | Chart.js + react-chartjs-2 |
| Fonts | Syne (headings) + JetBrains Mono (code) |
| Streaming | Server-Sent Events (SSE) |

---

## 📁 Project Structure

```
codesentry-frontend/
├── src/
│   ├── components/
│   │   ├── LandingPage.jsx      # Hero + inputs
│   │   ├── AnalysisView.jsx     # Live analysis split-panel
│   │   ├── ReportView.jsx       # Full report + exports
│   │   ├── AgentCard.jsx        # Agent status card
│   │   ├── FindingCard.jsx      # Expandable finding
│   │   ├── SeverityBadge.jsx    # Severity indicator
│   │   ├── SeverityChart.jsx    # Donut chart
│   │   ├── PrivacyCertificate.jsx
│   │   ├── AMDMetricsCard.jsx   # Live GPU telemetry card
│   │   ├── AMDMigrationPanel.jsx # ROCm compatibility report
│   │   └── ParticleBackground.jsx
│   ├── context/
│   │   └── ScanContext.jsx      # Global state + SSE reducers
│   ├── services/
│   │   ├── scanService.js       # SSE client
│   │   └── mockService.js       # Mock replay engine (simulates AMD data)
│   └── index.css                # Cyberpunk design system
├── public/
│   ├── mock_analysis.json       # Demo data payload
│   └── background.png           # Cyberpunk UI background
└── .env                         # Environment config
```

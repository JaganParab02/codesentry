#!/bin/bash
# =============================================================================
# setup_vllm.sh — One-command vLLM setup on AMD MI300X for CodeSentry
# =============================================================================
set -euo pipefail

echo "============================================================"
echo "  CodeSentry — vLLM + Qwen2.5-Coder-32B Setup (AMD MI300X)"
echo "============================================================"

# ── 1. Install vLLM with ROCm backend ─────────────────────────
echo "[1/4] Installing vLLM with ROCm 6.2 support..."
pip install vllm --extra-index-url https://download.pytorch.org/whl/rocm6.2

# ── 2. Install project dependencies ───────────────────────────
echo "[2/4] Installing CodeSentry requirements..."
pip install -r requirements.txt

# ── 3. Start vLLM server ──────────────────────────────────────
echo "[3/4] Starting vLLM server with Qwen2.5-Coder-32B-Instruct..."
echo "  Model: Qwen/Qwen2.5-Coder-32B-Instruct"
echo "  Port: 8080"
echo "  GPU utilisation: 85%"
echo "  Max context: 32768 tokens"

vllm serve Qwen/Qwen2.5-Coder-32B-Instruct \
  --port 8080 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.85 \
  --max-model-len 32768 \
  --enable-chunked-prefill \
  --trust-remote-code \
  &

VLLM_PID=$!
echo "  vLLM PID: $VLLM_PID"

# ── 4. Wait for vLLM to be ready ──────────────────────────────
echo "[4/4] Waiting for vLLM to be ready..."
MAX_WAIT=300  # 5 minutes max
ELAPSED=0
until curl -sf http://localhost:8080/health > /dev/null 2>&1; do
  if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
    echo "ERROR: vLLM did not become ready within ${MAX_WAIT}s"
    kill "$VLLM_PID" 2>/dev/null || true
    exit 1
  fi
  echo "  Waiting... (${ELAPSED}s elapsed)"
  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

echo ""
echo "============================================================"
echo "  vLLM is READY at http://localhost:8080"
echo "  Starting CodeSentry API at http://localhost:8000 ..."
echo "============================================================"
echo ""

# Start CodeSentry
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

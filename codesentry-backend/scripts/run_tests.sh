#!/bin/bash
# =============================================================================
# run_tests.sh — Full test suite runner for CodeSentry Backend
# =============================================================================
set -euo pipefail

echo "============================================================"
echo "  CodeSentry Backend — Test Suite"
echo "============================================================"

# Move to project root (one level up from scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# ── Install test dependencies ──────────────────────────────────
echo "[Setup] Installing test dependencies..."
pip install pytest pytest-asyncio httpx -q

# ── Set environment so tests run in no-LLM mode ───────────────
export USE_LLM=false
export VLLM_BASE_URL=http://localhost:8080
export MODEL_NAME=Qwen/Qwen2.5-Coder-32B-Instruct

echo ""
echo "[Config]"
echo "  USE_LLM       = $USE_LLM"
echo "  VLLM_BASE_URL = $VLLM_BASE_URL"
echo ""

# ── Run test suite ─────────────────────────────────────────────
echo "[Running] pytest tests/ ..."
echo ""

pytest tests/ \
  -v \
  --tb=short \
  --asyncio-mode=auto \
  --color=yes \
  -x  # Stop on first failure for hackathon speed

EXIT_CODE=$?

echo ""
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "============================================================"
  echo "  ✅  All tests PASSED"
  echo "============================================================"
else
  echo "============================================================"
  echo "  ❌  Some tests FAILED (exit code: $EXIT_CODE)"
  echo "============================================================"
fi

exit "$EXIT_CODE"

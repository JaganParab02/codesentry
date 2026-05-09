#!/bin/bash
# =============================================================================
# benchmark.sh — Latency + throughput benchmark for CodeSentry
# Runs 10 analyses on the vulnerable fixture and outputs benchmark_results.json
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FIXTURE="$PROJECT_ROOT/tests/fixtures/vulnerable_ml_code.py"
API_URL="${CODESENTRY_URL:-http://localhost:8000}"
RESULTS_FILE="$PROJECT_ROOT/benchmark_results.json"
RUNS="${BENCHMARK_RUNS:-10}"

echo "============================================================"
echo "  CodeSentry Benchmark"
echo "  API: $API_URL"
echo "  Runs: $RUNS"
echo "  Fixture: $FIXTURE"
echo "============================================================"

if [ ! -f "$FIXTURE" ]; then
  echo "ERROR: Fixture file not found: $FIXTURE"
  exit 1
fi

# Encode fixture code for JSON
FIXTURE_CODE=$(python3 -c "
import json, sys
code = open('$FIXTURE').read()
print(json.dumps(code))
")

# Collect timings
declare -a TOTAL_TIMES=()
declare -a TTFF_TIMES=()
TOTAL_FINDINGS=0

echo ""
echo "Running $RUNS benchmark iterations..."
echo ""

for i in $(seq 1 "$RUNS"); do
  SESSION_ID="bench-$(date +%s%N)-$i"
  START_TS=$(date +%s%N)
  FIRST_FINDING_TS=0
  END_TS=0

  PAYLOAD=$(python3 -c "
import json
print(json.dumps({
    'source': $FIXTURE_CODE,
    'source_type': 'code',
    'session_id': '$SESSION_ID'
}))
")

  FINDINGS_IN_RUN=0
  while IFS= read -r line; do
    if [[ "$line" == data:* ]]; then
      DATA="${line#data: }"
      if [ "$FIRST_FINDING_TS" -eq 0 ] && echo "$DATA" | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); sys.exit(0 if d.get('event')!='finding' else 1)" 2>/dev/null; then
        :
      fi
      EVENT=$(echo "$DATA" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('event',''))" 2>/dev/null || echo "")
      if [[ "$EVENT" == "finding" ]] && [ "$FIRST_FINDING_TS" -eq 0 ]; then
        FIRST_FINDING_TS=$(date +%s%N)
        FINDINGS_IN_RUN=$((FINDINGS_IN_RUN + 1))
      fi
      if [[ "$EVENT" == "complete" ]]; then
        END_TS=$(date +%s%N)
      fi
    fi
  done < <(curl -sf -X POST "$API_URL/api/analyze" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --no-buffer 2>/dev/null || true)

  if [ "$END_TS" -eq 0 ]; then
    END_TS=$(date +%s%N)
  fi

  TOTAL_MS=$(( (END_TS - START_TS) / 1000000 ))
  TTFF_MS=0
  if [ "$FIRST_FINDING_TS" -gt 0 ]; then
    TTFF_MS=$(( (FIRST_FINDING_TS - START_TS) / 1000000 ))
  fi

  TOTAL_TIMES+=("$TOTAL_MS")
  TTFF_TIMES+=("$TTFF_MS")
  TOTAL_FINDINGS=$((TOTAL_FINDINGS + FINDINGS_IN_RUN))

  echo "  Run $i: total=${TOTAL_MS}ms  ttff=${TTFF_MS}ms  findings=$FINDINGS_IN_RUN"
done

# Compute averages using Python
echo ""
echo "Computing results..."

python3 - <<PYEOF
import json, statistics

total_times = [${TOTAL_TIMES[*]:-0}]
ttff_times = [t for t in [${TTFF_TIMES[*]:-0}] if t > 0]

results = {
    "benchmark_config": {
        "runs": $RUNS,
        "fixture": "vulnerable_ml_code.py",
        "api_url": "$API_URL",
    },
    "latency_ms": {
        "total_analysis": {
            "mean": round(statistics.mean(total_times), 1) if total_times else 0,
            "median": round(statistics.median(total_times), 1) if total_times else 0,
            "min": min(total_times) if total_times else 0,
            "max": max(total_times) if total_times else 0,
            "stdev": round(statistics.stdev(total_times), 1) if len(total_times) > 1 else 0,
        },
        "time_to_first_finding": {
            "mean": round(statistics.mean(ttff_times), 1) if ttff_times else 0,
            "median": round(statistics.median(ttff_times), 1) if ttff_times else 0,
            "min": min(ttff_times) if ttff_times else 0,
            "max": max(ttff_times) if ttff_times else 0,
        },
    },
    "findings": {
        "total_across_runs": $TOTAL_FINDINGS,
        "avg_per_run": round($TOTAL_FINDINGS / $RUNS, 1),
    },
}

with open("$RESULTS_FILE", "w") as f:
    json.dump(results, f, indent=2)

print(json.dumps(results, indent=2))
PYEOF

echo ""
echo "============================================================"
echo "  Benchmark complete! Results saved to:"
echo "  $RESULTS_FILE"
echo "============================================================"

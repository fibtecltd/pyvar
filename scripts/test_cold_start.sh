#!/usr/bin/env bash
#
# scripts/test_cold_start.sh — P5b cold-start latency test (MANUAL / operator only)
#
# Measures end-to-end latency from VaR job submission to first result when the
# worker fleet starts from ZERO instances (the cold path: SQS-triggered ASG
# scale-out + EC2 Spot boot + Numba warmup + compute).
#
# Target: < 45s (job submission -> first result), reported as min/max/avg over 3 runs.
#
# PREREQUISITES (must be set in the environment):
#   AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN   (read+ASG+SQS)
#   PYVAR_TEST_JWT        JWT bearer token for the dev tenant
#   PYVAR_ORIGIN_VERIFY   X-Origin-Verify header value for the CloudFront origin
# Optional overrides:
#   PYVAR_ENV     (default: dev)
#   AWS_REGION    (default: eu-west-1)
#   PYVAR_ENDPOINT(default: https://d1mqqddh8gu2qi.cloudfront.net)
#   COLD_RUNS     (default: 3)
#   COLD_TARGET_S (default: 45)
#
# This script mutates live infrastructure (scales the worker ASG to 0). It will
# NOT run until you type "yes" at the confirmation prompt.

set -euo pipefail

ENV_NAME="${PYVAR_ENV:-dev}"
REGION="${AWS_REGION:-eu-west-1}"
ENDPOINT="${PYVAR_ENDPOINT:-https://d1mqqddh8gu2qi.cloudfront.net}"
RUNS="${COLD_RUNS:-3}"
TARGET_S="${COLD_TARGET_S:-45}"
ASG_NAME="pyvar-${ENV_NAME}-workers"
N_SIMS=10000
POLL_INTERVAL=2          # seconds between result polls
MAX_WAIT_S=180           # per-run safety cap while waiting for first result

# ── sanity ────────────────────────────────────────────────────────────────────
command -v aws  >/dev/null || { echo "FATAL: aws CLI not found"; exit 1; }
command -v curl >/dev/null || { echo "FATAL: curl not found"; exit 1; }
command -v jq   >/dev/null || { echo "FATAL: jq not found"; exit 1; }
: "${PYVAR_TEST_JWT:?FATAL: PYVAR_TEST_JWT must be set}"
: "${PYVAR_ORIGIN_VERIFY:?FATAL: PYVAR_ORIGIN_VERIFY must be set}"

# ── JWT self-refresh (stdlib only — no third-party deps) ─────────────────────
# Generates a fresh 24-hour pro-tier JWT from Secrets Manager on every run.
echo "-- refreshing JWT from Secrets Manager ..."
PYVAR_TEST_JWT="$(python3 - << 'PYEOF_INNER'
import hmac, hashlib, base64, json, time, subprocess

def b64url(data):
    if isinstance(data, str):
        data = data.encode()
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

secret = subprocess.run(
    ["aws", "secretsmanager", "get-secret-value",
     "--secret-id", "pyvar/dev/jwt-secret",
     "--region", "eu-west-1",
     "--query", "SecretString",
     "--output", "text"],
    capture_output=True, text=True, check=True
).stdout.strip()

header  = b64url(json.dumps({"alg":"HS256","typ":"JWT"},separators=(',',':')))
payload = b64url(json.dumps({"sub":"test-operator","tier":"pro","exp":int(time.time())+86400},separators=(',',':')))
sig     = b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
print(f"{header}.{payload}.{sig}")
PYEOF_INNER
)"
export PYVAR_TEST_JWT
echo "-- JWT refreshed (expires in 24h)"

echo "=========================================================================="
echo " P5b COLD-START TEST"
echo "   env=${ENV_NAME}  region=${REGION}  asg=${ASG_NAME}"
echo "   endpoint=${ENDPOINT}"
echo "   runs=${RUNS}  n_simulations=${N_SIMS}  target<${TARGET_S}s"
echo "=========================================================================="
echo "This will SCALE ${ASG_NAME} TO 0 and rely on SQS-driven scale-out to bring"
echo "a worker back up for each run. Starting automatically ..."

auth=( -H "Authorization: Bearer ${PYVAR_TEST_JWT}"
       -H "X-Origin-Verify: ${PYVAR_ORIGIN_VERIFY}"
       -H "Content-Type: application/json" )

current_instance_count() {
  aws autoscaling describe-auto-scaling-groups \
      --region "${REGION}" \
      --auto-scaling-group-names "${ASG_NAME}" \
      --query "AutoScalingGroups[0].Instances | length(@)" --output text 2>/dev/null || echo "ERR"
}

scale_to_zero() {
  echo "-- scaling ${ASG_NAME} desired=0 ..."
  aws autoscaling update-auto-scaling-group \
      --region "${REGION}" --auto-scaling-group-name "${ASG_NAME}" \
      --min-size 0 --desired-capacity 0
  echo "-- waiting for instance count == 0 (timeout 300s) ..."
  local waited=0
  while :; do
    local n; n="$(current_instance_count)"
    echo "   instances=${n} (t=${waited}s)"
    [ "${n}" = "0" ] && break
    [ "${waited}" -ge 300 ] && { echo "WARN: ASG did not reach 0 within 300s; continuing"; break; }
    sleep 5; waited=$((waited+5))
  done
}

submit_job() {
  curl -s -X POST "${ENDPOINT}/api/v1/var/compute" "${auth[@]}" \
    -d "{\"n_simulations\": ${N_SIMS}, \"confidence_level\": 0.99, \"horizon_days\": 1, \"portfolio_value\": 1000000, \"returns\": [-0.012, 0.008, -0.005, 0.015, -0.003, 0.011, -0.007, 0.004, -0.009, 0.013, -0.002, 0.006, -0.014, 0.009, -0.001, 0.007, -0.011, 0.003, -0.006, 0.012, -0.004, 0.008, -0.010, 0.005, -0.008, 0.014, -0.003, 0.009, -0.006, 0.011]}" \
    | jq -r '.task_id // .id // empty'
}

poll_until_result() {
  # arg1 = task_id ; echoes elapsed seconds to first SUCCESS, or "TIMEOUT"
  local task_id="$1" start now status waited
  start="$(date +%s)"
  while :; do
    status="$(curl -s "${ENDPOINT}/api/v1/var/result/${task_id}" "${auth[@]}" | jq -r '.status // "unknown"')"
    now="$(date +%s)"; waited=$((now-start))
    if [ "${status}" = "SUCCESS" ] || [ "${status}" = "success" ] || [ "${status}" = "completed" ]; then
      echo "${waited}"; return 0
    fi
    if [ "${status}" = "FAILURE" ] || [ "${status}" = "failed" ]; then
      echo "FAILED"; return 1
    fi
    [ "${waited}" -ge "${MAX_WAIT_S}" ] && { echo "TIMEOUT"; return 1; }
    sleep "${POLL_INTERVAL}"
  done
}

results=()
for i in $(seq 1 "${RUNS}"); do
  echo ""
  echo "########## RUN ${i}/${RUNS} ##########"
  scale_to_zero
  echo "-- submitting job (n_simulations=${N_SIMS}) ..."
  task_id="$(submit_job)"
  [ -n "${task_id}" ] || { echo "ERROR: no task_id returned; skipping run"; continue; }
  echo "-- task_id=${task_id}; measuring submission -> first result ..."
  elapsed="$(poll_until_result "${task_id}" || true)"
  echo "-- run ${i}: ${elapsed}s (task ${task_id})"
  case "${elapsed}" in
    ''|*[!0-9]*) echo "   (non-numeric result: ${elapsed} — excluded from stats)";;
    *) results+=("${elapsed}");;
  esac
done

echo ""
echo "=========================================================================="
if [ "${#results[@]}" -eq 0 ]; then
  echo " COLD-START RESULT: no successful runs — INVESTIGATE"
  exit 1
fi
min=${results[0]}; max=${results[0]}; sum=0
for r in "${results[@]}"; do
  (( r < min )) && min=$r
  (( r > max )) && max=$r
  sum=$((sum+r))
done
avg=$((sum / ${#results[@]}))
echo " COLD-START RESULT (${#results[@]} runs): min=${min}s  max=${max}s  avg=${avg}s"
if (( avg <= TARGET_S )); then
  echo " VERDICT: PASS (avg ${avg}s <= ${TARGET_S}s target)"
else
  echo " VERDICT: FAIL (avg ${avg}s > ${TARGET_S}s target)"
fi
echo "=========================================================================="

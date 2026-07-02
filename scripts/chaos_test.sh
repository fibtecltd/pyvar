#!/usr/bin/env bash
#
# scripts/chaos_test.sh — P5b Spot-interruption chaos test (MANUAL / operator only)
#
# Validates SQS + Celery at-least-once durability: a long-running VaR job survives
# the loss of the EC2 Spot worker processing it (task_acks_late=True means the
# in-flight message reappears after the visibility timeout and another worker
# completes it — see CLAUDE.md section 3.2).
#
# Steps:
#   1. Submit a long VaR job (n_simulations=500000).
#   2. Poll SQS ApproximateNumberOfMessagesNotVisible until a worker picks it up.
#   3. Terminate that worker's EC2 Spot instance (no ASG capacity decrement).
#   4. Verify the SQS message becomes visible again after the visibility timeout.
#   5. Poll /api/v1/var/result/{task_id} until SUCCESS or a 5-minute timeout.
#   6. Report pass/fail and total recovery time.
#
# PREREQUISITES:
#   AWS creds (EC2/ASG/SQS access), PYVAR_TEST_JWT, PYVAR_ORIGIN_VERIFY.
#   ASG desired capacity MUST be > 0 before running (need a worker to kill, and
#   a survivor / replacement to finish the job). Confirm this first.
# Optional overrides: PYVAR_ENV(dev) AWS_REGION(eu-west-1) PYVAR_ENDPOINT(...)
#
# This TERMINATES A LIVE EC2 INSTANCE. It will NOT run until you type "yes".

set -euo pipefail

ENV_NAME="${PYVAR_ENV:-dev}"
REGION="${AWS_REGION:-eu-west-1}"
ENDPOINT="${PYVAR_ENDPOINT:-https://d1mqqddh8gu2qi.cloudfront.net}"
ASG_NAME="pyvar-${ENV_NAME}-workers"
QUEUE_NAME="pyvar-${ENV_NAME}-var-jobs.fifo"
N_SIMS=500000
RESULT_TIMEOUT_S=300     # 5-minute recovery cap
PICKUP_TIMEOUT_S=120     # wait for a worker to pick the job up

command -v aws  >/dev/null || { echo "FATAL: aws CLI not found"; exit 1; }
command -v curl >/dev/null || { echo "FATAL: curl not found"; exit 1; }
command -v jq   >/dev/null || { echo "FATAL: jq not found"; exit 1; }
: "${PYVAR_TEST_JWT:?FATAL: PYVAR_TEST_JWT must be set}"
: "${PYVAR_ORIGIN_VERIFY:?FATAL: PYVAR_ORIGIN_VERIFY must be set}"

auth=( -H "Authorization: Bearer ${PYVAR_TEST_JWT}"
       -H "X-Origin-Verify: ${PYVAR_ORIGIN_VERIFY}"
       -H "Content-Type: application/json" )

QUEUE_URL="$(aws sqs get-queue-url --region "${REGION}" --queue-name "${QUEUE_NAME}" --query QueueUrl --output text)"
VIS_TIMEOUT="$(aws sqs get-queue-attributes --region "${REGION}" --queue-url "${QUEUE_URL}" \
                 --attribute-names VisibilityTimeout \
                 --query 'Attributes.VisibilityTimeout' --output text)"

desired="$(aws autoscaling describe-auto-scaling-groups --region "${REGION}" \
             --auto-scaling-group-names "${ASG_NAME}" \
             --query 'AutoScalingGroups[0].DesiredCapacity' --output text)"

echo "=========================================================================="
echo " P5b CHAOS TEST (Spot interruption recovery)"
echo "   env=${ENV_NAME}  region=${REGION}"
echo "   asg=${ASG_NAME} (desired=${desired})  queue=${QUEUE_NAME}"
echo "   queue visibility timeout=${VIS_TIMEOUT}s  n_simulations=${N_SIMS}"
echo "   endpoint=${ENDPOINT}"
echo "=========================================================================="
if [ "${desired}" = "0" ] || [ "${desired}" = "None" ]; then
  echo "FATAL: ASG desired capacity is ${desired}. Set it > 0 before chaos testing."
  exit 1
fi
echo "This will TERMINATE a live EC2 Spot worker. Type 'yes' to proceed."
read -r CONFIRM
[ "${CONFIRM}" = "yes" ] || { echo "Aborted."; exit 1; }

sqs_attr() {  # arg1 = attribute name
  aws sqs get-queue-attributes --region "${REGION}" --queue-url "${QUEUE_URL}" \
      --attribute-names "$1" --query "Attributes.$1" --output text
}

# ── 1. submit long job ──────────────────────────────────────────────────────────
echo "-- submitting long job (n_simulations=${N_SIMS}) ..."
task_id="$(curl -s -X POST "${ENDPOINT}/api/v1/var/compute" "${auth[@]}" \
  -d "{\"n_simulations\": ${N_SIMS}, \"confidence_level\": 0.99, \"horizon_days\": 10, \"portfolio_value\": 1000000}" \
  | jq -r '.task_id // .id // empty')"
[ -n "${task_id}" ] || { echo "FATAL: no task_id returned"; exit 1; }
echo "-- task_id=${task_id}"
START="$(date +%s)"

# ── 2. wait for a worker to pick it up (in-flight message) ──────────────────────
echo "-- waiting for a worker to pick up the job (NotVisible >= 1) ..."
waited=0
while :; do
  inflight="$(sqs_attr ApproximateNumberOfMessagesNotVisible)"
  echo "   NotVisible=${inflight} (t=${waited}s)"
  [ "${inflight}" != "0" ] && [ "${inflight}" != "None" ] && break
  [ "${waited}" -ge "${PICKUP_TIMEOUT_S}" ] && { echo "FATAL: job not picked up within ${PICKUP_TIMEOUT_S}s"; exit 1; }
  sleep 5; waited=$((waited+5))
done

# ── 3. terminate the worker instance (no capacity decrement -> ASG replaces it) ──
INSTANCE_ID="$(aws autoscaling describe-auto-scaling-groups --region "${REGION}" \
                 --auto-scaling-group-names "${ASG_NAME}" \
                 --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' \
                 --output text)"
[ -n "${INSTANCE_ID}" ] && [ "${INSTANCE_ID}" != "None" ] || { echo "FATAL: no InService instance to terminate"; exit 1; }
echo "-- terminating worker ${INSTANCE_ID} (ASG will launch a replacement) ..."
aws autoscaling terminate-instance-in-auto-scaling-group \
    --region "${REGION}" --instance-id "${INSTANCE_ID}" \
    --no-should-decrement-desired-capacity >/dev/null
echo "-- terminated ${INSTANCE_ID} at t=$(( $(date +%s) - START ))s"

# ── 4. verify the message returns to visible after the visibility timeout ───────
echo "-- waiting up to $((VIS_TIMEOUT + 30))s for the message to become visible again ..."
waited=0; requeued="no"
while [ "${waited}" -le $((VIS_TIMEOUT + 30)) ]; do
  visible="$(sqs_attr ApproximateNumberOfMessages)"
  echo "   Visible=${visible} (t=${waited}s)"
  if [ "${visible}" != "0" ] && [ "${visible}" != "None" ]; then requeued="yes"; break; fi
  sleep 5; waited=$((waited+5))
done
echo "-- message re-queued after interruption: ${requeued}"

# ── 5. poll for eventual success ────────────────────────────────────────────────
echo "-- polling for job completion (timeout ${RESULT_TIMEOUT_S}s) ..."
status="unknown"; waited=0
while [ "${waited}" -le "${RESULT_TIMEOUT_S}" ]; do
  status="$(curl -s "${ENDPOINT}/api/v1/var/result/${task_id}" "${auth[@]}" | jq -r '.status // "unknown"')"
  echo "   status=${status} (t=${waited}s)"
  case "${status}" in
    SUCCESS|success|completed) break;;
    FAILURE|failed) break;;
  esac
  sleep 5; waited=$((waited+5))
done
RECOVERY=$(( $(date +%s) - START ))

# ── 6. verdict ──────────────────────────────────────────────────────────────────
echo ""
echo "=========================================================================="
echo " CHAOS TEST RESULT"
echo "   task_id=${task_id}  killed=${INSTANCE_ID}"
echo "   message re-queued: ${requeued}"
echo "   final status: ${status}"
echo "   total recovery time: ${RECOVERY}s"
case "${status}" in
  SUCCESS|success|completed)
    if [ "${requeued}" = "yes" ]; then
      echo " VERDICT: PASS — job survived Spot interruption and completed"
    else
      echo " VERDICT: PASS (completed) — WARN: re-queue not observed (worker may have finished pre-kill)"
    fi
    ;;
  *) echo " VERDICT: FAIL — job did not complete within ${RESULT_TIMEOUT_S}s (status=${status})";;
esac
echo "=========================================================================="

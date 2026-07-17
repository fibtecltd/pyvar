#!/usr/bin/env bash
#
# scripts/force-worker-instance.sh — force a pyvar Celery worker EC2 Spot
# instance up for manual/scripted benchmarking, then tear it down cleanly.
#
# The workers ASG scales on SQS queue depth with min_capacity=0 (see
# compute_stack.py) — at rest there are zero workers. This codifies the
# "force worker up, suspend Terminate, do the work, resume Terminate,
# verify clean" pattern that's been reconstructed manually at least 4-5
# times across P6 and P7:
#
#   1. Force ASG desired capacity up (bypasses the queue-depth trigger).
#   2. Suspend the ASG's Terminate scaling process, so a scale-in event
#      (e.g. the SQS queue draining mid-benchmark) can't kill the instance
#      out from under an in-progress benchmark.
#   3. Wait for the instance to reach InService; report its instance ID.
#   4. [run only] hold for --duration seconds, or execute --action via
#      SSM Session Manager, then automatically tear down (trap-protected —
#      cleanup runs even on Ctrl-C or a failed --action).
#   5. Resume the Terminate process.
#   6. Scale back to 0.
#   7. Verify: 0 instances, 0 suspended processes, ASG back to steady state.
#
# THIS FORCES A LIVE EC2 SPOT INSTANCE. `up` and `run` refuse to execute
# without --yes. `status` and `down` are always safe (read-only / teardown).
#
# Usage:
#   scripts/force-worker-instance.sh status
#   scripts/force-worker-instance.sh up   --yes [--count N]
#   scripts/force-worker-instance.sh down
#   scripts/force-worker-instance.sh run  --yes [--count N] [--duration SECS] [--action "shell command"]
#
# Examples:
#   # Hold a worker up for 20 minutes of manual SSM Session Manager poking:
#   scripts/force-worker-instance.sh run --yes --duration 1200
#
#   # Force a worker, run one command on it via SSM, tear down automatically:
#   scripts/force-worker-instance.sh run --yes --action "systemctl restart pyvar-worker"
#
#   # Force a worker and drive it manually yourself (no auto-teardown):
#   scripts/force-worker-instance.sh up --yes
#   ... aws ssm start-session --target <instance-id> ...
#   scripts/force-worker-instance.sh down
#
# Optional overrides: PYVAR_ENV(dev) AWS_REGION(eu-west-1)

set -euo pipefail

ENV_NAME="${PYVAR_ENV:-dev}"
REGION="${AWS_REGION:-eu-west-1}"
ASG_NAME="pyvar-${ENV_NAME}-workers"

COUNT=1
DURATION=""
ACTION=""
CONFIRMED="no"

command -v aws >/dev/null || { echo "FATAL: aws CLI not found"; exit 1; }

SUBCOMMAND="${1:-}"
[ $# -gt 0 ] && shift

while [ $# -gt 0 ]; do
  case "$1" in
    --yes) CONFIRMED="yes"; shift ;;
    --count) COUNT="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --action) ACTION="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument: $1"; exit 1 ;;
  esac
done

WORKER_INSTANCE_ID=""

asg_state_json() {
  aws autoscaling describe-auto-scaling-groups --region "${REGION}" \
    --auto-scaling-group-names "${ASG_NAME}" \
    --query 'AutoScalingGroups[0].{Desired:DesiredCapacity,Suspended:SuspendedProcesses[].ProcessName,Instances:Instances[].{Id:InstanceId,State:LifecycleState}}' \
    --output json
}

print_status() {
  echo "-- ${ASG_NAME} (${REGION}):"
  asg_state_json | python3 -m json.tool 2>/dev/null || asg_state_json
}

wait_for_in_service() {
  local waited=0 timeout=180 id
  while [ "${waited}" -lt "${timeout}" ]; do
    id="$(aws autoscaling describe-auto-scaling-groups --region "${REGION}" \
      --auto-scaling-group-names "${ASG_NAME}" \
      --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' \
      --output text)"
    if [ -n "${id}" ] && [ "${id}" != "None" ]; then
      WORKER_INSTANCE_ID="${id}"
      return 0
    fi
    echo "   waiting for InService instance ... (t=${waited}s)" >&2
    sleep 5; waited=$((waited + 5))
  done
  echo "FATAL: no instance reached InService within ${timeout}s" >&2
  return 1
}

wait_for_zero_instances() {
  local waited=0 timeout=180 n
  while [ "${waited}" -lt "${timeout}" ]; do
    n="$(aws autoscaling describe-auto-scaling-groups --region "${REGION}" \
      --auto-scaling-group-names "${ASG_NAME}" \
      --query 'length(AutoScalingGroups[0].Instances)' --output text)"
    [ "${n}" = "0" ] && return 0
    echo "   waiting for instance count to reach 0 (currently ${n}) ... (t=${waited}s)" >&2
    sleep 5; waited=$((waited + 5))
  done
  echo "WARNING: instance count did not reach 0 within ${timeout}s — check manually" >&2
  return 1
}

require_confirmation() {
  if [ "${CONFIRMED}" != "yes" ]; then
    echo "FATAL: '${SUBCOMMAND}' forces a live EC2 Spot instance — pass --yes to confirm." >&2
    exit 1
  fi
}

do_up() {
  require_confirmation
  echo "=========================================================================="
  echo " FORCING WORKER INSTANCE — ${ASG_NAME} (${REGION})"
  echo "   desired capacity -> ${COUNT}, Terminate process will be suspended"
  echo "=========================================================================="
  aws autoscaling set-desired-capacity --region "${REGION}" \
    --auto-scaling-group-name "${ASG_NAME}" --desired-capacity "${COUNT}" --honor-cooldown
  echo "-- suspending Terminate scaling process (prevents scale-in mid-benchmark) ..."
  aws autoscaling suspend-processes --region "${REGION}" \
    --auto-scaling-group-name "${ASG_NAME}" --scaling-processes Terminate
  echo "-- waiting for instance to reach InService ..."
  wait_for_in_service
  echo "-- worker instance in service: ${WORKER_INSTANCE_ID}"
}

do_down() {
  echo "-- resuming Terminate scaling process ..."
  aws autoscaling resume-processes --region "${REGION}" \
    --auto-scaling-group-name "${ASG_NAME}" --scaling-processes Terminate || true
  echo "-- scaling ${ASG_NAME} back to 0 ..."
  aws autoscaling set-desired-capacity --region "${REGION}" \
    --auto-scaling-group-name "${ASG_NAME}" --desired-capacity 0 --honor-cooldown || true
  wait_for_zero_instances || true
  echo "-- verifying clean state:"
  print_status
}

run_action_via_ssm() {
  echo "-- running action via SSM on ${WORKER_INSTANCE_ID}: ${ACTION}"
  local cmd_id status
  cmd_id="$(aws ssm send-command --region "${REGION}" \
    --instance-ids "${WORKER_INSTANCE_ID}" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"${ACTION}\"]" \
    --query 'Command.CommandId' --output text)"
  echo "-- SSM command ${cmd_id} dispatched, polling for completion ..."
  while :; do
    status="$(aws ssm get-command-invocation --region "${REGION}" \
      --command-id "${cmd_id}" --instance-id "${WORKER_INSTANCE_ID}" \
      --query 'Status' --output text 2>/dev/null || echo "Pending")"
    echo "   status=${status}"
    case "${status}" in
      Success | Failed | Cancelled | TimedOut) break ;;
    esac
    sleep 5
  done
  echo "-- SSM stdout:"
  aws ssm get-command-invocation --region "${REGION}" \
    --command-id "${cmd_id}" --instance-id "${WORKER_INSTANCE_ID}" \
    --query 'StandardOutputContent' --output text
  echo "-- SSM stderr:"
  aws ssm get-command-invocation --region "${REGION}" \
    --command-id "${cmd_id}" --instance-id "${WORKER_INSTANCE_ID}" \
    --query 'StandardErrorContent' --output text
  [ "${status}" = "Success" ]
}

case "${SUBCOMMAND}" in
  status)
    print_status
    ;;
  up)
    do_up
    echo "${WORKER_INSTANCE_ID}"
    echo "-- worker is up and Terminate is suspended. Run 'down' when finished."
    ;;
  down)
    do_down
    ;;
  run)
    require_confirmation
    trap 'echo "-- teardown (trap) --"; do_down' EXIT INT TERM
    do_up
    if [ -n "${ACTION}" ]; then
      run_action_via_ssm
    elif [ -n "${DURATION}" ]; then
      echo "-- holding worker up for ${DURATION}s (manual use — e.g. SSM Session Manager) ..."
      sleep "${DURATION}"
    else
      echo "-- no --action or --duration given; worker is up, teardown will run on exit."
    fi
    ;;
  *)
    echo "Usage: $0 {status|up|down|run} [--yes] [--count N] [--duration SECS] [--action \"cmd\"]" >&2
    exit 1
    ;;
esac

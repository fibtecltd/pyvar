#!/bin/bash
# ================================================================
# scripts/build-push-api.sh — ECR login + build + push for pyvar-dev-api
#
# Runs on the HOST (Mac Mini), not inside the claude-docker container —
# docker build/login/push need the host Docker daemon. Only the ECR auth
# token retrieval goes through the claude-docker container (AWS CLI lives
# there, not on the host).
#
# #119 closed: pyvar-cdk/stacks/pipeline_stack.py's Synth step now builds and
# pushes a git-SHA-tagged image on every pipeline run — that's the primary
# mechanism now. This script remains as a break-glass fallback for when the
# pipeline itself is broken (mirrors how a manual `cdk deploy pyvar-pipeline`
# has repeatedly served as this session's bootstrap when Synth itself was
# broken) — codifies the same manual sequence used repeatedly during P6/P7
# to work around the lack of Docker daemon in the Claude Code agent sandbox
# and the lack of AWS CLI on the host.
#
# Usage:
#   ./scripts/build-push-api.sh              build + push :latest and :<short-sha>
#   ./scripts/build-push-api.sh --dry-run    print commands, don't execute
# ================================================================

set -euo pipefail

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

REGION="eu-west-1"
ACCOUNT="347228921290"
REPO="pyvar-dev-api"
ECR_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${REPO}"
CLAUDE_DOCKER_DIR="${CLAUDE_DOCKER_DIR:-$HOME/claude-docker}"
COMPOSE_FILE="$CLAUDE_DOCKER_DIR/docker-compose.yml"

run() {
    if [ $DRY_RUN -eq 1 ]; then
        echo "[dry-run] $*"
    else
        eval "$*"
    fi
}

echo "=========================================================================="
echo " build-push-api.sh"
echo "   repo=$ECR_URI"
echo "   region=$REGION"
echo "=========================================================================="

# ── Sanity checks ─────────────────────────────────────────────────
command -v docker >/dev/null || { echo "FATAL: docker not found on host"; exit 1; }
[ -f "$COMPOSE_FILE" ] || { echo "FATAL: $COMPOSE_FILE not found — set CLAUDE_DOCKER_DIR"; exit 1; }
[ -f "Dockerfile" ] || { echo "FATAL: no Dockerfile in current directory — run from ~/projects/pyvar"; exit 1; }

SHORT_SHA="$(git rev-parse --short HEAD)"
echo "-- building from commit ${SHORT_SHA}"

# ── Confirm on current master, warn if not ──────────────────────────
BRANCH="$(git branch --show-current)"
if [ "$BRANCH" != "master" ]; then
    echo "WARNING: current branch is '${BRANCH}', not 'master'."
    read -r -p "         Continue anyway? [y/N] " confirm
    [ "${confirm:-N}" = "y" ] || [ "${confirm:-N}" = "Y" ] || { echo "Aborted."; exit 1; }
fi

# ── Step 1: ECR login (token via claude-docker container) ──────────
echo "-- fetching ECR login token via claude-docker container ..."
run "docker compose -f \"$COMPOSE_FILE\" run --rm --entrypoint bash claude -c \
      'aws ecr get-login-password --region $REGION' \
      | docker login --username AWS --password-stdin $ECR_URI"

# ── Step 2: build for linux/amd64 (Fargate is x86_64) ───────────────
echo "-- building linux/amd64 image ..."
run "docker build --platform linux/amd64 --target runtime \
      -t ${ECR_URI}:latest \
      -t ${ECR_URI}:${SHORT_SHA} \
      ."

# ── Step 3: push both tags ───────────────────────────────────────────
echo "-- pushing :latest ..."
run "docker push ${ECR_URI}:latest"
echo "-- pushing :${SHORT_SHA} ..."
run "docker push ${ECR_URI}:${SHORT_SHA}"

echo ""
echo "=========================================================================="
echo " Done. Image pushed: ${ECR_URI}:latest / :${SHORT_SHA}"
echo " Next: force the ECS deployment and verify the new digest is running —"
echo "   aws ecs update-service --cluster pyvar-dev --service pyvar-dev-api \\"
echo "     --force-new-deployment --region $REGION"
echo "=========================================================================="

#!/usr/bin/env bash
#
# scripts/toggle_kill_switch.sh — emergency API kill switch
#
# Flips the "EmergencyKillSwitch" rule (pyvar-cdk/stacks/edge_stack.py) on
# the CloudFront WAF WebACL between inert (Count) and engaged (Block) —
# i.e. between "normal" and "reject every request at the edge". This is a
# DIRECT `aws wafv2 update-web-acl` call, not a CDK deploy: a `cdk deploy`
# cycle takes minutes, far too slow for "cost is exploding right now, block
# everything" — the WebACL and this rule are provisioned once by CDK, and
# after that this script is the actual emergency lever.
#
# Usage:
#   scripts/toggle_kill_switch.sh status  [env]   # default env: prod
#   scripts/toggle_kill_switch.sh enable  [env]    # block everything NOW
#   scripts/toggle_kill_switch.sh disable [env]    # restore normal traffic
#
# Requires: aws CLI (configured with a principal that can wafv2:GetWebACL /
# wafv2:UpdateWebACL), jq. The WebACL is CLOUDFRONT-scoped, which AWS
# requires to be queried/updated in us-east-1 regardless of where the rest
# of the stack runs (see edge_stack.py's own module docstring).
#
# IMPORTANT: running `cdk deploy` again after using this script resets the
# rule back to Count (CloudFormation drift) — intentional, not a bug. This
# is meant to be a short-lived emergency measure, re-engaged manually via
# this same script if the underlying cost issue isn't resolved by the next
# deploy.

set -euo pipefail

ACTION="${1:-}"
ENV_NAME="${2:-prod}"
REGION="us-east-1" # CLOUDFRONT-scoped WebACLs are always managed here
WAF_NAME="pyvar-${ENV_NAME}-waf"
RULE_NAME="EmergencyKillSwitch"

if [[ "$ACTION" != "status" && "$ACTION" != "enable" && "$ACTION" != "disable" ]]; then
  echo "Usage: $0 {status|enable|disable} [env]  (env defaults to 'prod')" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required (JSON manipulation of the WebACL rule set)." >&2
  exit 1
fi

echo "Looking up WebACL '${WAF_NAME}' (CLOUDFRONT scope, ${REGION})..." >&2
WEB_ACL_ID=$(aws wafv2 list-web-acls \
  --scope CLOUDFRONT --region "$REGION" \
  --query "WebACLs[?Name=='${WAF_NAME}'].Id | [0]" --output text)

if [[ -z "$WEB_ACL_ID" || "$WEB_ACL_ID" == "None" ]]; then
  echo "ERROR: no CLOUDFRONT WebACL named '${WAF_NAME}' found in ${REGION}." >&2
  exit 1
fi

GET_OUT=$(aws wafv2 get-web-acl \
  --name "$WAF_NAME" --scope CLOUDFRONT --id "$WEB_ACL_ID" --region "$REGION")

LOCK_TOKEN=$(echo "$GET_OUT" | jq -r '.LockToken')
CURRENT_ACTION=$(echo "$GET_OUT" | jq -r --arg name "$RULE_NAME" \
  '.WebACL.Rules[] | select(.Name == $name) | .Action | keys[0]')

if [[ -z "$CURRENT_ACTION" ]]; then
  echo "ERROR: rule '${RULE_NAME}' not found on WebACL '${WAF_NAME}' — has the" >&2
  echo "edge_stack.py change that adds it actually been deployed yet?" >&2
  exit 1
fi

echo "Current state: ${RULE_NAME} action = ${CURRENT_ACTION}" >&2
if [[ "$CURRENT_ACTION" == "Block" ]]; then
  echo "==> KILL SWITCH IS CURRENTLY ENGAGED — all traffic is being blocked." >&2
else
  echo "==> Kill switch is currently OFF — traffic flows normally." >&2
fi

if [[ "$ACTION" == "status" ]]; then
  exit 0
fi

TARGET_ACTION="Block"
[[ "$ACTION" == "disable" ]] && TARGET_ACTION="Count"

if [[ "$CURRENT_ACTION" == "$TARGET_ACTION" ]]; then
  echo "Already in the requested state (${TARGET_ACTION}) — nothing to do." >&2
  exit 0
fi

NEW_RULES=$(echo "$GET_OUT" | jq --arg name "$RULE_NAME" --arg target "$TARGET_ACTION" '
  .WebACL.Rules | map(
    if .Name == $name
    then .Action = ({($target): {}})
    else .
    end
  )
')

echo "$GET_OUT" | jq \
  --argjson rules "$NEW_RULES" \
  '{Name: .WebACL.Name, Scope: "CLOUDFRONT", Id: .WebACL.Id,
    DefaultAction: .WebACL.DefaultAction, Description: .WebACL.Description,
    Rules: $rules, VisibilityConfig: .WebACL.VisibilityConfig}' \
  > /tmp/pyvar-waf-update.json

aws wafv2 update-web-acl \
  --region "$REGION" \
  --lock-token "$LOCK_TOKEN" \
  --cli-input-json file:///tmp/pyvar-waf-update.json

rm -f /tmp/pyvar-waf-update.json

if [[ "$ACTION" == "enable" ]]; then
  echo "==> KILL SWITCH ENGAGED. All traffic to pyvar-${ENV_NAME} is now blocked at the edge." >&2
  echo "    Run '$0 disable ${ENV_NAME}' to restore normal traffic." >&2
else
  echo "==> Kill switch disengaged. Normal traffic restored for pyvar-${ENV_NAME}." >&2
fi

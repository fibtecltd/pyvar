#!/usr/bin/env bash
#
# scripts/ops/revoke-api-key.sh: wraps scripts/revoke_api_key.py (list an account's API keys, revoke them).
#
#   scripts/ops/revoke-api-key.sh list --env dev --account-id <external_id>
#   scripts/ops/revoke-api-key.sh revoke --env dev --account-id <external_id> --prefix pyvar_ab12cd --apply
#   scripts/ops/revoke-api-key.sh revoke --env prod --account-id <id> --all-active --yes-all --apply
#
# list is read-only; revoke is real and immediate and needs --apply. --yes-all (every active key of the account) is
# never added for you. With --session-token-env the secret is not needed, so the AWS check is skipped.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="revoke_api_key.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() {
  case "${1:-}" in
    list) echo read ;;
    *) echo change ;;
  esac
}

ops_needs_aws() { # a session token the account already holds needs no signing secret
  local arg
  for arg in "$@"; do
    case "$arg" in --session-token-env | --session-token-env=*) return 1 ;; esac
  done
  return 0
}

ops_main "$@"

#!/usr/bin/env bash
#
# scripts/ops/mint-api-key.sh: wraps scripts/mint_api_key.py (create a durable API key for an existing account).
#
#   KEY=$(scripts/ops/mint-api-key.sh --env dev --account-id <external_id> --name ci-dev --apply)
#   PYVAR_SESSION=<token from the portal> scripts/ops/mint-api-key.sh --env dev --session-token-env PYVAR_SESSION --apply
#
# It creates a credential and has no dry run, so it needs --apply. The key goes to stdout alone, once; every
# message of the wrapper goes to stderr, so the capture holds just the key. With --session-token-env the secret
# is not needed, so the AWS check is skipped.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="mint_api_key.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { echo change; }

ops_needs_aws() { # a session token the account already holds needs no signing secret
  local arg
  for arg in "$@"; do
    case "$arg" in --session-token-env | --session-token-env=*) return 1 ;; esac
  done
  return 0
}

ops_main "$@"

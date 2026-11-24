#!/usr/bin/env bash
#
# scripts/ops/mint-internal-token.sh: wraps scripts/mint_internal_token.py (sign an API token on demand).
#
#   TOKEN=$(scripts/ops/mint-internal-token.sh --env dev --apply)
#   scripts/ops/mint-internal-token.sh --env dev --days 7 --sub load-test-nov --apply
#   scripts/ops/mint-internal-token.sh --decode "$TOKEN"          # reads a token's claims; no AWS, no --apply
#
# Minting creates a credential the API cannot revoke (only its expiry ends it), so it needs --apply and, on prod,
# the typed confirmation. The token goes to stdout alone; every message of the wrapper goes to stderr, so the
# capture holds just the token. --decode needs no secret, no environment and no AWS.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="mint_internal_token.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() {
  local arg
  for arg in "$@"; do
    case "$arg" in --decode | --decode=*)
      echo local
      return 0
      ;;
    esac
  done
  echo change
}

ops_main "$@"

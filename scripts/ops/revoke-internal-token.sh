#!/usr/bin/env bash
#
# scripts/ops/revoke-internal-token.sh: wraps scripts/revoke_internal_token.py (what is outstanding, how to cancel).
#
#   scripts/ops/revoke-internal-token.sh list
#   scripts/ops/revoke-internal-token.sh revoke --fingerprint 6b3f7f --reason "test finished"
#   scripts/ops/revoke-internal-token.sh runbook --env prod
#
# The script touches only the local ledger and prints the emergency runbook: no AWS, no API, no secret. It
# cannot switch a token off (the API has no revocation list for JWTs): `revoke` records the decision and exits 4,
# "recorded, NOT enforced". The wrapper hands that exit code back unchanged.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="revoke_internal_token.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { echo local; }

ops_main "$@"

#!/usr/bin/env bash
#
# scripts/ops/education-grant.sh: wraps scripts/education_grant.py (docs/plan-education-tier.md).
#
#   scripts/ops/education-grant.sh list --env prod
#   scripts/ops/education-grant.sh grant --env dev --email a@uni.ac.uk --months 6 --cohort ucl-risk-2026 --apply
#   scripts/ops/education-grant.sh tidy --env prod                  # counts only
#   scripts/ops/education-grant.sh tidy --env prod --apply          # does it
#   scripts/ops/education-grant.sh suspend-all --env prod --yes-all --apply
#
# list is read-only; tidy has a real dry run; grant, extend, revoke and suspend-all change data and need --apply.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="education_grant.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() {
  case "${1:-}" in
    list) echo read ;;
    tidy) echo dryrun ;;
    *) echo change ;; # grant, extend, revoke, suspend-all, and anything new: the careful reading
  esac
}

ops_main "$@"

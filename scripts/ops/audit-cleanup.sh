#!/usr/bin/env bash
#
# scripts/ops/audit-cleanup.sh: wraps scripts/audit_cleanup.py (delete audit rows older than six years).
#
#   scripts/ops/audit-cleanup.sh --env prod            # dry run: counts what is older than six years
#   scripts/ops/audit-cleanup.sh --env prod --apply    # deletes it, after you confirm
#
# The script is a dry run unless it gets --yes; the wrapper adds --yes only for --apply, after the confirmation.
# The six years are fixed in the API (api/audit_retention.py): there is no period to pass, here or there.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="audit_cleanup.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { echo dryrun; }

ops_main "$@"

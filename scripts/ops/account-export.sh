#!/usr/bin/env bash
#
# scripts/ops/account-export.sh: wraps scripts/account_export.py (a copy of one account's data, one JSON file).
#
#   scripts/ops/account-export.sh --env prod --email a@uni.ac.uk --out ~/exports/ada-2026-11-24.json
#
# The script only reads from the API and writes the one file named by --out (never overwritten), so it has no
# --apply; on prod you confirm by typing the environment. --out is resolved from the folder you run it in.
# The e-mail address is masked wherever the wrapper shows the command.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="account_export.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { echo read; }

ops_main "$@"

#!/usr/bin/env bash
#
# scripts/ops/account-erase.sh: wraps scripts/account_erase.py (erase an account at its holder's request).
#
#   scripts/ops/account-erase.sh --env prod --email a@uni.ac.uk            # dry run: says what it would do
#   scripts/ops/account-erase.sh --env prod --email a@uni.ac.uk --apply    # does it, after you confirm
#
# The script is a dry run unless it gets --yes; the wrapper adds --yes only for --apply, after the confirmation.
# The e-mail address is masked wherever the wrapper shows the command.
# The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="account_erase.py"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { echo dryrun; }

ops_main "$@"

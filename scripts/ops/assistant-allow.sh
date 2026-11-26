#!/usr/bin/env bash
#
# scripts/ops/assistant-allow.sh: wraps scripts/assistant_allow.py (who may ask the typed assistant a question while
# `assistant_allowlist_enabled` is on; docs/assistant-runbook.md).
#
#   scripts/ops/assistant-allow.sh --env prod list
#   scripts/ops/assistant-allow.sh --env prod allow --email a@b.example            # dry run
#   scripts/ops/assistant-allow.sh --env prod allow --email a@b.example --apply    # does it, after you confirm
#   scripts/ops/assistant-allow.sh --env prod clear --apply                        # every account refused at once
#
# `list` only reads; `allow`, `remove` and `clear` are a dry run unless --apply (the wrapper then adds --yes).
# This script's --env, --region and --yes-prod belong to its top-level parser, so they go BEFORE the subcommand,
# and the wrapper puts the --yes-prod it adds there too. The e-mail address is masked wherever the wrapper shows
# the command. The rules are in scripts/ops/_common.sh and scripts/ops/README.md.

OPS_SCRIPT="assistant_allow.py"
OPS_PROD_FLAG_AT="front"
# shellcheck source=scripts/ops/_common.sh
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

ops_mode() { # the subcommand follows the global options (--env prod allow ...), so look for it among the arguments
  local arg
  for arg in "$@"; do
    case "$arg" in
      list)
        echo read
        return 0
        ;;
      allow | remove | clear)
        echo dryrun
        return 0
        ;;
    esac
  done
  echo dryrun # no subcommand given: the script will say so; without --apply nothing can change
}

ops_main "$@"

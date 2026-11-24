#!/usr/bin/env bash
#
# scripts/ops/_common.sh: what every wrapper in this folder shares. It is sourced by the wrappers and is
# not a command of its own.
#
# Reasoning:
# - The operator scripts (education_grant.py, account_erase.py, ...) already read the environment's signing
#   secret from AWS Secrets Manager (`pyvar/<env>/jwt-secret`), with the AWS CLI, and never put it in an
#   argument (scripts/token_tools.py::read_secret_from_aws). A wrapper therefore does NOT fetch or pipe the
#   secret: secret handling stays in that one place. `--secret-stdin` is refused here; run the Python script
#   directly for an offline secret.
# - What a wrapper adds is the part a person forgets: it checks that the AWS CLI is signed in and says which
#   account it is, asks for a typed confirmation before anything that changes data or touches prod, adds
#   `--yes` / `--yes-prod` itself only after that confirmation, and hands back the Python script's exit code
#   unchanged (0 done, 2 refused, 3 secret or AWS not usable, 4 recorded but not enforced, 5 the API refused).
# - It never weakens a guard. The Python script still enforces every rule; a wrapper only decides whether
#   to call it, and with what. `--yes-all` (a mass action) is never added: the person types it.
# - NOTHING the wrapper prints goes to stdout. mint_api_key.py and mint_internal_token.py write the key or the
#   token alone on stdout so that KEY=$(...) works; every message here goes to stderr. The confirmation is
#   read from the terminal (/dev/tty), not from stdin, so a pipe cannot answer it.
# - An --email value is masked wherever the wrapper shows the command: account_erase.py and account_export.py
#   promise never to print the address.
# - This is a convenience against mistakes, not a security boundary: whoever can run the wrapper can run the
#   Python script. The API's own checks are what protect the data.
# - Written to stay within what bash 3.2 (macOS) has, as well as 5.x (only 5.2 was run): no associative arrays, no bare "${array[@]}" of a maybe-empty
#   array under `set -u`.
#
# A wrapper sets OPS_SCRIPT (the file in scripts/), defines ops_mode (and, if it needs, ops_needs_aws), then
# calls `ops_main "$@"`. ops_mode prints one of:
#   read    reads or lists only; asks for confirmation on prod; refuses --apply
#   dryrun  the script has a real dry run: without --apply it runs as that; with --apply the wrapper adds --yes
#   change  changes data and has no dry run: refused without --apply
#   local   touches no AWS and no API (a ledger, a decode); no env needed; refuses --apply
#
# Test hooks (see tests/test_ops_wrappers.py): PYVAR_OPS_PYTHON names the Python to run;
# PYVAR_OPS_CONFIRM_FILE names a file to read the confirmation from instead of /dev/tty.

set -euo pipefail

OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_SCRIPTS="$(cd "$OPS_DIR/.." && pwd)"
OPS_PYTHON="${PYVAR_OPS_PYTHON:-python3}"
OPS_CONFIRM_SOURCE="${PYVAR_OPS_CONFIRM_FILE:-/dev/tty}"
OPS_DEFAULT_REGION="eu-west-1" # scripts/token_tools.py::DEFAULT_REGION

ops_say() { printf '%s\n' "$*" >&2; }

ops_die() { # ops_die <exit code> <message>
  local code="$1"
  shift
  ops_say "refused: $*"
  exit "$code"
}

# A wrapper overrides this to say it needs no AWS for some arguments (a session token already in hand).
ops_needs_aws() { return 0; }

ops_describe() { # the command as it will run, e-mail and token values masked
  local out="python scripts/${OPS_SCRIPT}" mask=no arg quoted
  for arg in "$@"; do
    if [ "$mask" = yes ]; then
      out="$out <masked>"
      mask=no
      continue
    fi
    case "$arg" in
      --email | --decode)
        out="$out $arg"
        mask=yes
        ;;
      --email=*) out="$out --email=<masked>" ;;
      *)
        printf -v quoted '%q' "$arg"
        out="$out $quoted"
        ;;
    esac
  done
  printf '%s' "$out"
}

ops_check_python() {
  command -v "$OPS_PYTHON" >/dev/null 2>&1 || ops_die 3 "Python ('$OPS_PYTHON') not found: set PYVAR_OPS_PYTHON"
  [ -f "$OPS_SCRIPTS/$OPS_SCRIPT" ] || ops_die 3 "scripts/$OPS_SCRIPT not found"
}

ops_check_aws() { # sets $account; says nothing about the secret itself
  local answer
  command -v aws >/dev/null 2>&1 || ops_die 3 "the AWS CLI ('aws') is not installed or not on PATH"
  if ! answer="$(aws sts get-caller-identity --region "$1" --query Account --output text 2>&1)"; then
    ops_die 3 "the AWS CLI is not signed in: ${answer##*$'\n'}"
  fi
  case "$answer" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) account="$answer" ;;
    *) ops_die 3 "the AWS CLI did not return an account id" ;;
  esac
}

ops_confirm() { # ops_confirm <word the person must type>
  local word="$1" reply=""
  # `read` fails on a last line with no newline although it filled $reply, hence the second test.
  if ! { IFS= read -r reply <"$OPS_CONFIRM_SOURCE" || [ -n "$reply" ]; } 2>/dev/null; then
    ops_die 2 "this needs a terminal to confirm it: run it from an interactive shell"
  fi
  [ "$reply" = "$word" ] || ops_die 2 "not confirmed (expected '$word'); nothing was run"
}

ops_main() {
  local -a given=("$@") passed=() final=()
  local apply=no want_help=no env="" region="$OPS_DEFAULT_REGION" mode="" account=""
  local i=0 n=$# arg

  while [ "$i" -lt "$n" ]; do
    arg="${given[$i]}"
    case "$arg" in
      -h | --help)
        want_help=yes
        passed+=("$arg")
        ;;
      --apply) apply=yes ;;
      --yes) ops_die 2 "use --apply: the wrapper adds --yes itself, after you confirm" ;;
      --yes-prod) ;; # dropped: added again only after the confirmation below
      --secret-stdin)
        ops_die 2 "the wrappers read the secret from AWS Secrets Manager; for an offline secret run scripts/${OPS_SCRIPT} directly"
        ;;
      --env)
        i=$((i + 1))
        env="${given[$i]:-}"
        passed+=("$arg" "$env")
        ;;
      --env=*)
        env="${arg#--env=}"
        passed+=("$arg")
        ;;
      --region)
        i=$((i + 1))
        region="${given[$i]:-}"
        passed+=("$arg" "$region")
        ;;
      --region=*)
        region="${arg#--region=}"
        passed+=("$arg")
        ;;
      *) passed+=("$arg") ;;
    esac
    i=$((i + 1))
  done

  ops_check_python
  if [ "$want_help" = yes ]; then
    exec "$OPS_PYTHON" "$OPS_SCRIPTS/$OPS_SCRIPT" ${passed[@]+"${passed[@]}"}
  fi

  mode="$(ops_mode ${given[@]+"${given[@]}"})"
  case "$mode" in
    read | dryrun | change | local) ;;
    *) ops_die 2 "internal error: unknown mode '$mode'" ;;
  esac

  if [ "$apply" = yes ] && { [ "$mode" = read ] || [ "$mode" = local ]; }; then
    ops_die 2 "this command changes nothing: drop --apply"
  fi
  if [ "$mode" = change ] && [ "$apply" = no ]; then
    ops_die 2 "this changes data and has no dry run: add --apply to run it (you will be asked to confirm)"
  fi

  if [ "$mode" != local ]; then
    case "$env" in
      dev | prod) ;;
      "") ops_die 2 "--env is required (dev or prod); there is no default" ;;
      *) ops_die 2 "--env must be dev or prod" ;;
    esac
  fi

  final=(${passed[@]+"${passed[@]}"})
  [ "$mode" = dryrun ] && [ "$apply" = yes ] && final+=(--yes)
  [ "$mode" != local ] && [ "$env" = prod ] && final+=(--yes-prod)

  if [ "$mode" != local ] && ops_needs_aws ${given[@]+"${given[@]}"}; then
    ops_check_aws "$region"
    ops_say "AWS account ${account}, environment ${env}."
  fi

  if [ "$mode" != local ] && { [ "$apply" = yes ] || [ "$env" = prod ]; }; then
    ops_say "About to run:"
    ops_say "  $(ops_describe ${final[@]+"${final[@]}"})"
    [ "$apply" = yes ] && ops_say "This changes data."
    ops_say "Type '${env}' to continue:"
    ops_confirm "$env"
  fi

  exec "$OPS_PYTHON" "$OPS_SCRIPTS/$OPS_SCRIPT" ${final[@]+"${final[@]}"}
}

# scripts/ops: wrappers for the operator scripts

One shell wrapper per operator script in `scripts/`. Each takes the same arguments as its Python script, checks
that the AWS CLI is signed in, asks you to confirm anything that changes data or touches prod, and hands back the
script's own exit code. The Python scripts still enforce every rule; a wrapper only decides whether to call them.

| Wrapper | Runs | Kind |
|---|---|---|
| `education-grant.sh` | `education_grant.py` | `list` reads; `tidy` has a dry run; `grant`, `extend`, `revoke`, `suspend-all` change data |
| `account-erase.sh` | `account_erase.py` | dry run; `--apply` erases |
| `account-export.sh` | `account_export.py` | reads, writes one local JSON file |
| `audit-cleanup.sh` | `audit_cleanup.py` | dry run; `--apply` deletes rows older than six years |
| `mint-api-key.sh` | `mint_api_key.py` | creates a key |
| `revoke-api-key.sh` | `revoke_api_key.py` | `list` reads; `revoke` changes data |
| `mint-internal-token.sh` | `mint_internal_token.py` | creates a token; `--decode` needs no AWS |
| `revoke-internal-token.sh` | `revoke_internal_token.py` | local ledger and runbook only |

```
scripts/ops/account-erase.sh --env prod --email a@uni.ac.uk            # dry run
scripts/ops/account-erase.sh --env prod --email a@uni.ac.uk --apply    # asks you to type: prod
KEY=$(scripts/ops/mint-api-key.sh --env dev --account-id <external_id> --name ci-dev --apply)
```

## Rules

- **The secret.** The scripts read `pyvar/<env>/jwt-secret` from AWS Secrets Manager with the AWS CLI
  (`scripts/token_tools.py`); the wrappers do not fetch or pipe it, so that stays in one place. `--secret-stdin` is
  refused: for an offline secret run the Python script directly.
- **`--apply`.** A command that changes data needs `--apply`. Where the script has a real dry run (`account-erase`,
  `audit-cleanup`, `education-grant tidy`) that is what you get without it, and `--apply` makes the wrapper add
  `--yes`. Where it has none (`grant`, `extend`, `revoke`, `suspend-all`, minting, revoking a key) the wrapper
  refuses without `--apply`. A hand-typed `--yes` is refused.
- **Confirmation.** With `--apply`, or on prod for anything, the wrapper shows the command and asks you to type the
  environment (`dev` or `prod`). It reads the terminal, not stdin, so a pipe cannot answer it; with no terminal it
  refuses. After you confirm it adds `--yes-prod` itself; one you typed is dropped. `--yes-all` is never added.
- **Output.** Everything the wrapper says goes to stderr, so `KEY=$(...)` and `TOKEN=$(...)` capture only the key or
  token. An `--email` value is masked wherever the wrapper shows the command.
- **No AWS needed** for `--decode`, for `revoke-internal-token.sh`, and for the key scripts with
  `--session-token-env` (a session token already in hand).
- **Exit codes** are the script's: 0 done, 2 refused, 3 the secret or AWS is not usable, 4 recorded but not enforced,
  5 the API refused. The wrapper itself uses 2 for a refusal and 3 for AWS or Python not ready.

This is a convenience against mistakes, not a security boundary: whoever can run a wrapper can run the script. The
API's own checks are what protect the data.

## Not wrapped

`scripts/trial_ctl.py` talks to the API's Redis cache, not to Secrets Manager or the API, and has to run where the
API's environment exists (an ECS one-off); a wrapper that checks AWS would be wrong for it. The other scripts in
`scripts/` build, generate or benchmark and are run by developers and CI.

## Tests

`tests/test_ops_wrappers.py` runs the real wrappers with a stub `aws` and a stub Python, so no AWS, API or secret is
involved. Two hooks exist for it: `PYVAR_OPS_PYTHON` (the Python to run) and `PYVAR_OPS_CONFIRM_FILE` (a file to read
the confirmation from instead of the terminal). The wrappers avoid features newer than bash 3.2 (macOS); only bash 5.2 has been run.

# Signing secrets and internal tokens

Status: written 2026-11-16. Covers what `pyvar/dev/jwt-secret` and `pyvar/prod/jwt-secret` are, whether
they should be regenerated, and `scripts/mint_internal_token.py`, which signs tokens on demand.
Everything about the code is checked against master at `7e35bbc` (file and line given); nothing here
was checked against AWS, because this was written without access to it.

## 1. What the two secrets are

They are **signing secrets, not keys.** Each is the HS256 secret that pyvar uses to sign and check
session tokens (JWTs) in one environment. A secret cannot "be" an internal, unlimited key, because the
tier is not a property of the secret: it is a claim (`tier`) inside each token, and whoever holds the
secret can sign a token that claims any tier.

- Created by CDK, one per environment, 64 random letters and digits:
  `pyvar-cdk/stacks/api_stack.py:218` (name `pyvar/<env>/jwt-secret`) and `:221` (length). Separate
  stacks generate separate values, so dev and prod differ by construction.
- Injected into the API containers as `JWT_SECRET`: `api_stack.py:360`. Three Lambdas also read it to
  sign their own service tokens: `pyvar-cdk/lambda/public_data_publisher/handler.py:145`,
  `token_report_publisher/handler.py:67`, `ses_suppression_handler/handler.py:94`, all with tier
  `internal`.
- What an `internal` claim buys: exemption from the rate limits (`api/middleware/rate_limit.py:113`),
  up to 500,000 simulations (`api/middleware/auth.py:70`), and access to the service-only routes
  (`api/routes/internal.py:57` and `:98`).

**Both already work as the signing secret of internal tokens.** Prod: the demo publisher signs an
`internal` token with the prod secret every 15 minutes and the API accepts it (the evidence document
infers that most prod jobs are its). Dev: on 2026-11-14 the W4/W5 agent signed an `internal` token with
the dev secret and the dev API ran its jobs (`docs/p9-aws-evidence-2026-11-13.md`, section 7). So
nothing needs to be generated to make either "an internal key".

To look at the secrets without reading their values (metadata only; needs `secretsmanager:DescribeSecret`):

```
aws secretsmanager describe-secret --secret-id pyvar/prod/jwt-secret --region eu-west-1 \
  --query '{Created:CreatedDate,Changed:LastChangedDate,Rotation:RotationEnabled}'
```

## 2. Should they be regenerated? Not without a reason

Rotating a signing secret is safe but not free:

- Every session token signed with the old value stops working at once. Users sign in again; tokens only
  last 60 minutes anyway (`config.py`, `jwt_expiry_minutes`).
- The API containers read the secret when they start, so they need a new deployment; the Lambdas pick it
  up on their next run. Until the containers restart, the API and the Lambdas disagree.
- API keys (`pyvar_...`) are not affected: they are hashed in the database and their tier is read from it.
- Every token minted with `scripts/mint_internal_token.py` stops working, which is also the only way to
  cancel one early (a JWT has no revocation list).

Reasons that do justify it: a suspected leak of the secret, or a person with read access leaving.

## 3. A gap worth closing (not done)

`config.py:24` falls back to the public string `change-me-in-production` when `JWT_SECRET` is missing.
In AWS the secret is always injected, so the hosted environments are fine, but nothing makes the API
refuse to start outside development with that default or with a short secret. If a task were ever
started without the injection, anyone could sign an `internal` token for it. A start-up check (refuse
when `APP_ENV` is not `development` and the secret is the default or shorter than 32 characters) is a
few lines in `config.py` or the `main.py` start-up; it changes application code, so merging it starts a
pipeline run. It is proposed here and not implemented.

## 4. Signing a token on demand: `scripts/mint_internal_token.py`

```
TOKEN=$(python scripts/mint_internal_token.py --env dev)                 # 1 day, tier internal
python scripts/mint_internal_token.py --env dev --days 7 --sub load-test-nov
python scripts/mint_internal_token.py --env prod --days 1 --yes-prod     # prod needs the flag
python scripts/mint_internal_token.py --env dev --tier free              # a free-tier test token
python scripts/mint_internal_token.py --decode "$TOKEN"                  # claims, expiry, unverified
```

Needs the AWS CLI signed in with permission to read the secret (`secretsmanager:GetSecretValue` on that
one secret). Python standard library only.

| Guard | What it does |
|---|---|
| No default environment | `--env dev` or `--env prod` is required. |
| Prod flag | Signing for prod needs `--yes-prod`. |
| Expiry always present | Default 1 day, ceiling 90 (`--days`); there is no way to ask for a token without `exp`. |
| Secret checks | Refuses an empty or short (under 32 characters) secret and the public default. |
| Secret handling | Read through the AWS CLI into memory, passed on a pipe, never an argument; never printed or written. |
| Output | The token alone on stdout, a one-line summary on stderr, so `TOKEN=$(...)` captures just the token. |
| Ledger | Appends who, when, environment, label, tier, expiry and a 12-character fingerprint of the token to `~/.pyvar/minted-tokens.jsonl` (mode 0600; `--ledger`, `$PYVAR_TOKEN_LEDGER`, `--no-ledger`). Never the token or the secret. |
| Label | `--sub` (3 to 64 characters of a-z, 0-9, `.`, `_`, `-`), generated if omitted, so a token can be told apart in logs and in `var_jobs.user_id`. |

Exit codes: 0 done, 2 refused by a guard or bad arguments, 3 the secret could not be read or is unusable.
`--secret-stdin` takes the secret from standard input instead (offline use, tests).

**What it cannot do.** A token cannot be revoked before it expires; the ledger tells you what is
outstanding, and rotating the secret is the only emergency stop (section 2). Tier `internal` is meant for
Fibtec's own tools, tests and load runs. It is also the only credential the service-only routes check:
`/internal/suppress-email` and `/internal/token-report` test nothing but `tier == "internal"`
(`api/routes/internal.py:57` and `:98`), and the authentication in front of them accepts API keys as well
as session tokens (`api/middleware/auth.py:155`, the tier of a key read from the database). Anyone holding
an `internal` token, or an API key on an account whose tier is `internal`, can mark any e-mail address as
suppressed and so stop sign-in links reaching it. A token is not tied to a person or an account, so it is
the wrong thing to give to a third party: for them the right tool is an account-bound, revocable,
finite-tier API key (`docs/plan-academic-access.md`, `docs/plan-anonymous-plugin-keys.md`).

# pyvar-client

Python SDK for [pyvar.com](https://www.pyvar.com)'s open-source risk computation API —
385 functions across 8 domains, one typed client.

> **Status:** v0.2.0-track, built ahead of its originally planned schedule (see
> `docs/pyvar_release_plan.md` in the main repo). Alpha — the API surface may
> still change before a 1.0 release.

## Install

```bash
pip install pyvar-client
```

## Quick start

```python
from pyvar_client import Client

client = Client(api_key="eyJ...")  # a JWT obtained via pyvar.com registration + email verification

result = client.market_risk.historical_simulation_var(
    returns=[...],  # historical daily log-returns
    portfolio_value=1_000_000,
    confidence_level=0.99,
)
print(result["var_pct"], result["var_abs"])
```

Or as a context manager, which closes the underlying connection pool on exit:

```python
with Client(api_key="eyJ...") as client:
    ...
```

## The one async function: Monte Carlo VaR

Every domain function is synchronous request/response — call it, get the result.
`POST /var/compute` is the one exception: it's a real Monte Carlo job dispatched
to pyvar's Celery/SQS worker fleet, so it returns a `task_id` immediately instead
of a result. `client.var` wraps that:

```python
# Blocks: submits, polls until done, returns the finished result.
result = client.var.compute(
    portfolio_value=1_000_000,
    returns=[...],
    n_simulations=100_000,
)

# Or drive it yourself:
task_id = client.var.submit(portfolio_value=1_000_000, returns=[...])
status = client.var.poll(task_id)  # check once, no blocking
```

Above a simulation-count threshold, the API offloads the full loss distribution
to S3 and returns a `presigned_url` instead of the inline `loss_dist` — `compute()`
returns exactly what the API returned either way; fetching a presigned URL is a
plain `httpx.get()` if you want the raw distribution.

## Errors

Every non-2xx response raises a typed exception, not a generic HTTP error:

| Exception | Status | Notes |
|---|---|---|
| `PyvarAuthError` | 401 | Token missing, invalid, or expired. Register/verify at pyvar.com to get a new one — this client doesn't automate that flow. |
| `PyvarValidationError` | 422 | `.detail` carries the field-level validation errors. |
| `PyvarRateLimitError` | 429 | `.retry_after` (seconds) from the response's `Retry-After` header. |
| `PyvarComputeError` | — | A VaR job (`client.var.compute`) reached `status="failure"` server-side. `.task_id` and `.detail`. |
| `PyvarTimeoutError` | — | A VaR job didn't finish within `poll_timeout_seconds`. `.task_id` — poll it again later, the job may still complete. |
| `PyvarError` | any other 4xx/5xx | Base class for everything above; catch this if you just want "did it fail". |

```python
from pyvar_client import Client, PyvarValidationError, PyvarRateLimitError

try:
    client.market_risk.historical_simulation_var(returns=[...], portfolio_value=1_000_000)
except PyvarValidationError as e:
    print(e.detail)
except PyvarRateLimitError as e:
    print(f"retry after {e.retry_after}s")
```

## Retries

Every synchronous domain function is idempotent (pure compute, no side effects) —
connection errors, timeouts, and 5xx responses are retried automatically with
exponential backoff. `client.var.submit()` is the one call that's **never**
auto-retried: retrying a job submission blindly risks double-submitting real
compute work, since the API has no idempotency-key mechanism to de-duplicate on.
Polling (`client.var.poll()`) is a read, so it retries normally.

## Domains

`client.market_risk`, `client.derivatives`, `client.credit_risk`, `client.portfolio`,
`client.operational_risk`, `client.liquidity_risk`, `client.alm`, `client.regulatory`
— one namespace per domain, one method per function. See
[`portal/functions.json`](https://github.com/fibtecltd/pyvar/blob/master/portal/functions.json)
in the main repo for the full, live list, or just use your editor's autocomplete —
every method is fully typed.

## How the domain methods are generated

385 methods is too much to hand-maintain without drifting from the API (see
`docs/p9-function-catalogue-reconciliation.md` in the main repo for a real
instance of exactly that drift). `pyvar_client/_generated/` is produced by
`codegen/generate.py`, which reads the live OpenAPI schema
(`main.create_app().openapi()`) directly — regenerate after any API schema
change:

```bash
python3 codegen/generate.py
```

This needs the main repo's own dependencies installed (it imports
`main.create_app()` directly), so run it from a checkout with `requirements.txt`
+ `requirements-heavy.txt` installed, not just this package's own runtime deps.

## Development

```bash
pip install -e ".[dev]"
pytest -v --cov=pyvar_client --cov-report=term-missing
black --check --line-length 100 .
isort --check-only --profile black .
ruff check .
```

No real HTTP calls anywhere in the test suite — `httpx.MockTransport` intercepts
every request, so the real retry/error-mapping/auth logic runs against a handler
the tests control, never a live server. See `tests/conftest.py`.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). Same license as the main
[pyvar.com](https://github.com/fibtecltd/pyvar) repository.

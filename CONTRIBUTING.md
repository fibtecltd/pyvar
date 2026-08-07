# Contributing to pyvar

Thanks for considering a contribution. pyvar is built for quant developers
and risk engineers, and we'd like contributing to it to feel familiar if
you've ever implemented a VaR model or read a Basel document — precise,
testable, and honest about where the numbers come from.

**Read `CLAUDE.md` in full before making any changes.** It is the source of
truth for this codebase's architecture, coding rules, and regulatory
constraints, and everything below is a contributor-facing summary of it —
if the two ever disagree, `CLAUDE.md` wins.

---

## Ways to contribute

- **New risk functions** within an existing domain (Market Risk, Derivatives
  & Pricing, Credit Risk, Portfolio Analytics, Operational Risk, Liquidity
  Risk, ALM & Balance Sheet, Regulatory & Compliance).
- **New domains** entirely — see [Proposing a new domain](#proposing-a-new-domain).
- **Bug fixes**, numerical corrections, and performance improvements.
- **Documentation** — citations, limitations, worked examples in
  `tests/validation/`.

---

## Adding a new risk function

Follow this 8-step process for every new function (from `CLAUDE.md` §10):

1. Add the `@njit` kernel to `engine/` (see [Numba JIT rules](#numba-jit-rules-and-why-they-exist) below).
2. Add a public wrapper function with full type hints and a Google-style docstring.
3. Add Pydantic v2 request/response schemas in `schemas/`.
4. Add a Celery task in `tasks/`.
5. Add a FastAPI route in `api/routes/`.
6. Add engine tests in `tests/test_engine.py` verifying numerical properties.
7. Add API tests in `tests/test_api.py` verifying auth, validation, and tier enforcement.
8. Update `CLAUDE.md` §2 (repository layout) with the new files.

After merging, regenerate the function catalogue so `portal/functions.json`
(the canonical, live list of what the API exposes) stays accurate:

```bash
python3 scripts/generate_function_catalog.py
```

---

## Numba JIT rules — and why they exist

Every `@njit` function in `engine/` follows these rules. They're not style
preferences — breaking them causes silent runtime errors or compilation
failures that are painful to debug in a JIT-compiled codebase.

- **Stateless only.** Accept NumPy arrays, scalars, and Python primitives —
  never Pydantic models, dataclasses, or dicts, and never `import` inside an
  `@njit` function. Numba compiles a function's *type signature*, not its
  Python semantics; anything stateful or dynamically typed breaks that
  contract.
- **No dynamic dispatch.** No duck typing, no Python-style polymorphism.
  All array dtypes must be `float64` — never `float32` or `object`. Numba's
  compiler needs a single, fixed type per argument to generate machine code.
- **Pre-draw random numbers before entering the JIT region.** Call
  `np.random.randn(n_sims, horizon)` in pure Python and pass the array in —
  Numba's random API is limited, and pre-drawing keeps the kernel itself
  deterministic and testable.
- **`prange` requires `@njit(parallel=True, cache=True)`.** `cache=True` is
  mandatory — without it, every worker restart pays the ~2s first-call
  compilation cost again. Use `prange`, never plain `range`, in parallel
  kernels.
- **Return only NumPy arrays from `@njit` functions.** Convert to Python
  types (`list`, `dict`, `float`) in the public wrapper, never inside the
  kernel — mixed return types are exactly the kind of thing that silently
  breaks JIT compilation.

---

## Regulatory constraints — read before touching anything marked `[REGULATORY]`

Functions marked `[REGULATORY]` in the codebase implement specific,
citable Basel/FRTB/MiFID II/EMIR requirements — VaR confidence levels,
Expected Shortfall as the FRTB IMA capital metric, the 250-day Basel
traffic-light backtest, and the FRTB P&L Attribution Test thresholds (see
`CLAUDE.md` §4 for the full list). These are not implementation details to
optimize away; they're set by the Basel Committee and similar bodies, and
changing them without review can silently produce numbers that misstate
regulatory capital.

If your change touches regulatory logic:

1. Create a `reg/*` branch.
2. Add a comment referencing the specific Basel/FRTB/MiFID II document and
   section your change is based on.
3. Update tests to cover the changed thresholds.
4. Document the change in `CHANGELOG.md` with the regulatory reference.
5. **`reg/*` branches require a second reviewer before merge** — this is
   not optional, regardless of how confident the change looks.

---

## Running the test suite locally

```bash
# 1. Infrastructure
docker run -d -p 6379:6379 redis
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pyvar postgres

# 2. Database migrations
python scripts/db.py upgrade

# 3. Generate fixture data
python -c "from ingestion.fixtures import generate_fixture_parquet; \
           generate_fixture_parquet('/tmp/pyvar_fixtures.parquet')"

# 4. Run tests with coverage
pytest -v --cov=. --cov-report=term-missing
```

Testing rules that apply to any test you add or change (`CLAUDE.md` §5):

- **Engine tests** (`test_engine.py`) verify numerical correctness — never
  mock the engine functions themselves. At minimum, test that VaR > 0,
  CVaR ≥ VaR, 99% VaR > 95% VaR, that the same seed produces the same
  result, and that absolute VaR scales linearly with portfolio value.
- **API tests** (`test_api.py`) use `httpx.AsyncClient` against
  `create_app()`. Mock Celery's `apply_async` and `AsyncResult`, not the
  engine. Always cover: 202 on submit, 401 without auth, 422 on bad
  params, 403 on tier cap exceeded.
- **Never use real AWS services in tests** — use `moto` for S3/SQS if
  needed, and `ingestion/fixtures.py` for synthetic returns, never real
  market data.
- **80% coverage minimum** before any release.

---

## PR checklist

Before opening a PR, confirm:

- [ ] Follows `CLAUDE.md` in full — Numba rules, regulatory constraints,
      coding rules (§5a: no `l`/`O`/`I` variable names, explicit casts on
      numpy scalar returns, typed `dict[K, V]` annotations, etc.), and code
      style (§6).
- [ ] A numerical correctness test is included for any new/changed engine
      function.
- [ ] Coverage is maintained at 80%+ (`pytest --cov=. --cov-report=term-missing`).
- [ ] `black`, `isort`, and `ruff` are clean.
- [ ] `mypy` is clean.
- [ ] `bandit` shows zero HIGH findings.
- [ ] Commit messages follow the `type(scope): summary` convention
      (`feat(engine): ...`, `fix(api): ...`, `reg(metrics): ...`,
      `infra(cdk): ...` — see `CLAUDE.md` §8).
- [ ] If regulatory logic changed: `reg/*` branch, second reviewer, cited
      source, `CHANGELOG.md` entry.

---

## Proposing a new domain

New domains (beyond the current 8) follow the same layered pattern as an
existing one:

1. Create `schemas/<domain>.py`, `tasks/<domain>_task.py`,
   `api/routes/<domain>.py` — mirror `var.py`'s pattern in each layer.
2. Register the new router in `main.py`.
3. Add a new SQLAlchemy model in `storage/models.py` if new audit fields
   are needed.
4. Generate and apply an Alembic migration.

Before writing code, open a proposal in **GitHub Discussions** describing
the domain's scope and the regulatory/industry sources it's based on —
this is where domain proposals get scoped and agreed before implementation
work starts.

---

## Questions

Open a GitHub Discussion, or reach out at hello@fibtec.co.uk.

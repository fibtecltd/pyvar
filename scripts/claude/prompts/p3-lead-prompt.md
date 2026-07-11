# P3 — FastAPI Routes Implementation
# Used by: pyvar-run.sh p3 --mode seq
# Machine: M4 or Intel (sequential, no Agent Teams)

Do not ask for confirmation. Do not present options. Execute the steps below immediately.

---

## Environment facts — read before doing anything

- Python and all packages are pre-installed in this Docker container. Do NOT create a venv.
  `pytest`, `fastapi`, `celery`, `sqlalchemy`, `pydantic`, `numpy` all work as-is.
- Working directory is `/workspace/pyvar`. All 382 engine functions from P2 are
  available — import them directly from `engine.*` modules.
- The answer to any "how to proceed" question is: implement all routes sequentially,
  domain by domain, starting with Market Risk.

---

## Step 1 — Read context

Read @CLAUDE.md in full, especially:
- Section 3.1 (Numba rules — engine imports only, no re-implementation)
- Section 4 (regulatory constraints — schemas must enforce them)
- Section 5 (testing — integration tests required)
- Section 5a (coding quality rules — dict[str,Any], float() casts, no l/O/I vars)

Read @docs/pyvar_release_plan.md Phase 3 section.
Read @pyvar_functions.csv — this is the complete function registry.
Read @api/routes/var.py — existing route as the reference pattern.
Read @schemas/var.py — existing schema as the reference pattern.

---

## Step 2 — Verify git state

```bash
git status          # must be clean on master
git log --oneline -3  # confirm P2 merges are present
python -c "import engine.var_models, engine.credit_pd_lgd, \
           engine.liquidity_stress, engine.portfolio_optimisation, \
           engine.deriv_options_vanilla, engine.alm_ftp; print('All P2 imports OK')"
```

If imports fail, stop and report which domain is missing.

---

## Step 3 — Implementation pattern

Every route follows this pattern — study `api/routes/var.py` before starting:

```python
# api/routes/{domain}.py

from fastapi import APIRouter, HTTPException
from schemas.{domain} import {Function}Request, {Function}Response
from engine.{module} import {function_name}

router = APIRouter(prefix="/{domain}", tags=["{domain}"])

@router.post("/{function_endpoint}")
async def {function_endpoint}(request: {Function}Request) -> {Function}Response:
    try:
        result = {function_name}(**request.model_dump())
        return {Function}Response(**result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Schema pattern (`schemas/{domain}.py`):
- Request: Pydantic BaseModel with field validation matching CLAUDE.md §4 constraints
- Response: Pydantic BaseModel matching the engine function's return dict keys
- Regulatory fields (confidence levels, backtesting windows) must use validators

Celery task pattern (for computationally expensive routes, n_simulations > 10_000):
```python
# tasks/{domain}_task.py
from celery_app import celery
from engine.{module} import {function_name}

@celery.task(bind=True, name="tasks.{domain}.{function_name}")
def {function_name}_task(self, **kwargs) -> dict:
    return {function_name}(**kwargs)
```

---

## Step 4 — Domain implementation order

Implement all 8 domains sequentially. For each domain:
1. Create `schemas/{domain}.py` with Request/Response models for all domain functions
2. Create `api/routes/{domain}.py` with route handlers
3. Create `tasks/{domain}_task.py` for async-eligible functions
4. Register the router in `main.py`
5. Write integration tests in `tests/test_{domain}_api.py`
6. Run `pytest tests/test_{domain}_api.py -x -q` before committing
7. Commit: `git add -A && git commit -m "feat(p3-{domain}): wire {N} routes"`
8. Write `CHECKPOINT.md`

**Domain order:**
1. `market-risk` — 10 VaR routes + 8 ES + 7 stress + 10 Greeks + 9 P&L + 7 backtest + 8 vol + 9 FRTB = 68 routes
2. `credit-risk` — 55 routes (credit_pd_lgd, credit_var, credit_capital, credit_ifrs9, credit_cds, credit_xva)
3. `liquidity` — 40 liquidity routes (lcr, nsfr, stress, internal, funding)
4. `operational` — 44 ops routes (var, rcsa, kri, governance)
5. `portfolio` — 50 routes (optimisation, ratios, esg, attribution, factor)
6. `regulatory` — 30 routes (solvency, frtb, basel)
7. `derivatives` — 62 routes (options_vanilla, options_exotic, bonds, stoch_vol, curves, rates, bond_analytics)
8. `alm` — 33 routes (ftp, irrbb)

---

## Step 5 — Quality gates per domain

Before moving to the next domain:
- `pytest tests/test_{domain}_api.py -v` — all pass
- No bare `dict` annotations (use `dict[str, Any]` or `# type: ignore[type-arg]`)
- No `l`, `O`, `I` single-letter variable names
- Regulatory schema validators match CLAUDE.md §4 exactly

---

## Step 6 — Checkpoint and context management

Write `CHECKPOINT.md` after every commit:
```markdown
## Domain: {domain}
## Completed: {function list}
## Next: {next function}
## Git state: feat/p3 @ {commit hash}
## Tests: {N} passing
```

If context is running low, write `CONTEXT_EXHAUSTED.md` — do not stop abruptly.

---

## Step 7 — Final report

When all 8 domains are complete:

```
P3 COMPLETE
  market-risk:  68 routes, N tests
  credit-risk:  55 routes, N tests
  liquidity:    40 routes, N tests
  operational:  44 routes, N tests
  portfolio:    50 routes, N tests
  regulatory:   30 routes, N tests
  derivatives:  62 routes, N tests
  alm:          33 routes, N tests
  Total: 382 routes

Run: git push origin master
```

# P5 Lead Prompt — Agent Teams Parallel Validation
# Used by: pyvar-run.sh p5 --mode agent
# Each teammate validates one domain against reference values.
# Read-only API calls — safe for parallel execution.

---
Read @CLAUDE.md in full, especially section 4 (regulatory constraints).
Read @pyvar_release_plan.md Phase 5 section.
Read @scripts/claude/templates/checkpoint-instructions.md.

You are the Agent Teams LEAD for Phase 5 (testing and validation).
Your role is to coordinate parallel domain validation across 8 teammates.

## Your tasks

1. Verify the pyvar API is running and healthy before spawning teammates:
   Run: `curl -f http://pyvar-api:8000/health || curl -f http://localhost:8000/health`
   If unhealthy, stop and report — validation cannot proceed.

2. Spawn 8 validation teammates, one per domain:

| Teammate | Domain | Key validations |
|---|---|---|
| val-market | Market Risk | VaR vs scipy.stats.norm.ppf, Basel 250-day backtest, FRTB PAT thresholds |
| val-credit | Credit Risk | IRB vs BIS BCBS d347, IFRS 9 ECL vs IASB examples |
| val-liquidity | Liquidity Risk | LCR vs Basel delegated regulation worked examples |
| val-ops | Operational Risk | OpVaR distribution fitting vs scipy reference |
| val-portfolio | Portfolio Analytics | MV optimisation vs cvxpy reference, Sharpe ratio |
| val-derivatives | Derivatives | Black-Scholes exact: S=100,K=100,T=1,r=0.05,σ=0.2 → 10.4506 |
| val-regulatory | Regulatory | CET1 ratio, Basel IV output floor computation |
| val-alm | ALM | IRRBB six-shock EVE vs EBA published examples |

3. Instructions for each validation teammate:

> Read @CLAUDE.md section 4 (regulatory constraints) — these are your pass/fail criteria.
> Your task: write and run validation tests in tests/validation/test_[domain]_ref.py
> For each function in your domain:
>   - Call the pyvar API or import engine.* directly
>   - Compare against the reference value
>   - Tolerance: 0.1% for VaR-class, 0.001% for analytical solutions (Black-Scholes)
>   - Regulatory thresholds: ZERO tolerance — must match exactly
> Write CHECKPOINT.md after every 3 functions validated.
> Write CONTEXT_EXHAUSTED.md if context is running low.
> Your exit gate: all functions validated, 0 failures, coverage report saved.

4. When ALL teammates complete, aggregate results:
```
VALIDATION SUMMARY
  val-market:      [N] pass / [M] fail
  val-credit:      [N] pass / [M] fail
  ...
  Overall: [X]/[Y] functions validated

FAILURES (if any):
  [domain]: [function]: expected=[val] got=[val] deviation=[%]
```

5. Any failure with deviation > tolerance is a reg/* branch blocker.
   Open a GitHub issue for each failure before P6 can start.

# Install GSD
npx get-shit-done-cc@latest --claude --local

# Then invoke execution directly, bypassing the planning phase
# Pass the domain section of pyvar_release_plan.md as the spec input
/gsd-execute @pyvar_release_plan.md @pyvar_functions.csv

You are done when: (1) all functions in your domain are implemented,
(2) pytest tests/test_credit_risk.py passes with 0 failures,
(3) bandit -r engine/credit_risk.py shows 0 HIGH severity findings,
(4) you have verified no Numba rule violations per CLAUDE.md section 3.1.

git worktree add ../pyvar-credit-risk -b feat/credit-risk-engine
git worktree add ../pyvar-liquidity   -b feat/liquidity-engine
# etc.

# Team lead prompt
claude "You are the lead for pyvar.com engine implementation.
Read @CLAUDE.md and @pyvar_release_plan.md Phase 2.

Spawn 4 teammates with these names and tasks:
- market-risk: implement engine/market_risk.py + tests (68 functions, @CLAUDE.md Numba rules)
- credit-risk: implement engine/credit_risk.py + tests (55 functions, IFRS 9 + IRB rules)
- liquidity-ops: implement engine/liquidity.py + engine/oprisk.py + tests (84 functions combined)
- portfolio-alm: implement engine/portfolio.py + engine/alm.py + tests (83 functions combined)

Each teammate must: (1) read CLAUDE.md section 3.1 before writing any @njit function,
(2) write tests alongside implementation, (3) report back with function count and coverage.

Regulatory + Derivatives domains are reserved for a second wave due to QuantLib dependency."

<!-- .claude/commands/phase-start.md -->
Read @CLAUDE.md and @pyvar_release_plan.md.
We are starting $PHASE. Confirm you have read both documents
and summarise the exit gate for this phase before proceeding.

# Start of any P2 domain session
claude "@CLAUDE.md @pyvar_release_plan.md

We are in Phase 2 (engine implementation). Today's domain: Credit Risk.
Reference the domain session pattern in P2 of the release plan.
Function list: @pyvar_functions.csv

Start with PD estimation and work through in complexity order."

<!-- .claude/commands/domain-session.md -->
Read @CLAUDE.md sections 3.1, 4, and 5. Then implement the $DOMAIN domain:
1. engine/$MODULE.py - @njit functions, float64 only, no Python objects
2. tests/test_$MODULE.py - numerical correctness, no mocking
3. schemas/$DOMAIN.py - Pydantic v2 schemas

Functions: @pyvar_functions.csv (filter DOMAIN = $DOMAIN)

# Single file reference
claude "@pyvar_release_plan.md implement P2 domain session for Credit Risk"

# Multiple references in one session
claude "@CLAUDE.md @pyvar_functions.csv implement the Liquidity Risk engine domain"

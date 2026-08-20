---
name: Bug report
about: A function returns a wrong result, a route misbehaves, or something crashes
title: "[Bug] "
labels: bug
assignees: ''
---

## Domain

Which of the 8 domains does this affect? (delete the rest)

- Market Risk
- Derivatives & Pricing
- Credit Risk
- Portfolio Analytics
- Operational Risk
- Liquidity Risk
- ALM & Balance Sheet
- Regulatory & Compliance
- Not domain-specific (API/infra/portal)

## Function or endpoint

Name it exactly as it appears in `portal/functions.json` or the route path
(e.g. `POST /api/v1/market-risk/historical_var`).

## What happened

A clear description of the incorrect behaviour — a wrong number, an
unexpected status code, a crash, a stale value.

## Expected behaviour

What you expected instead, and why — a reference calculation, a cited
Basel/FRTB/MiFID II/EMIR source, or a comparison against another tool
(QuantLib, a published worked example, etc.) is the fastest way to a fix.
See `tests/validation/` for the kind of independent reference this
project already checks itself against.

## Minimal reproduction

```json
{
  "portfolio_value": 1000000,
  "confidence_level": 0.99,
  "...": "the exact request body (or Python call) that reproduces this"
}
```

## Environment

- pyvar version / commit SHA:
- Called via: [REST API / local `uvicorn` / Python import]

## Numerical vs. non-numerical

- [ ] This is a numerical correctness issue (wrong VaR, wrong Greek, wrong
      capital figure, etc.) — regulatory-sensitive, see `CLAUDE.md` §4 and
      `CONTRIBUTING.md`'s regulatory-constraints section before proposing a
      fix.
- [ ] This is not a numerical issue (crash, wrong status code, docs, etc.)

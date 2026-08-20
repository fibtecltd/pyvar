---
name: Feature request
about: Propose a new risk function, domain, or platform capability
title: "[Feature] "
labels: enhancement
assignees: ''
---

## What kind of request is this?

- [ ] A new function within an existing domain
- [ ] A new domain entirely (see `CONTRIBUTING.md`'s "Proposing a new
      domain" section — this needs a GitHub Discussion first, not a PR)
- [ ] A platform/infrastructure capability (API, portal, deployment, etc.)

## Domain

If this is a new function or belongs to an existing domain, which one?
(delete the rest)

- Market Risk
- Derivatives & Pricing
- Credit Risk
- Portfolio Analytics
- Operational Risk
- Liquidity Risk
- ALM & Balance Sheet
- Regulatory & Compliance
- N/A (platform-level)

## What's missing, and why does it matter?

Describe the gap. If this implements a specific regulatory requirement or
industry-standard model, cite the source (Basel/FRTB/MiFID II/EMIR
document and section, or the published paper/reference the calculation
comes from) — pyvar treats citations as load-bearing, not decorative (see
`CLAUDE.md` §4).

## Proposed approach (optional)

If you already have a sense of the formula, model, or API shape, sketch
it here. Not required — a well-scoped problem statement is enough to
start a discussion.

## Alternatives considered

Is there an existing pyvar function that's close but not quite right?
Explain the gap.

# pyvar Pro Subscription — Price List Proposal

**Draft, not final.** Prepared at Filippo's request, as a standalone
companion to `docs/proposals/pyvar-monetization-strategy.docx`'s existing
scenario model, which already uses an **illustrative** $65/month Pro
figure "for modelling purposes only, not a commitment." This document
does the opposite: it proposes an actual price, priced against the
*real* tier limits already enforced in the shipped billing code
(`api/middleware/auth.py`, `rate_limit.py`, `config.py`), not a
placeholder. Currency is USD throughout, for the same reason the
monetization scenarios doc gives — the only real, confirmed cost figure
(the $900–1,000/month invoice) is USD-denominated. Needs Filippo's
review before any Stripe Price object is actually created
(`config.py`'s `stripe_price_id_pro` is still unset).

---

## 1. The tiers being priced are already real, not proposed

Three tiers exist today, live in the billing code, not hypothetical:

| Tier | Max simulations/request | Daily request cap | Monthly request cap | Monthly simulation cap |
|---|---|---|---|---|
| **Free** | 10,000 | 10/day | — | — |
| **Pro** | 100,000 | 500/day | 5,000/month | 2,000,000/month |
| **Enterprise** | 500,000 | unlimited | unlimited | unlimited |

Source: `TokenPayload.max_simulations` and `rate_limit_free_daily` /
`rate_limit_pro_daily` / `rate_limit_pro_monthly_requests` /
`rate_limit_pro_monthly_simulations` (`config.py`,
`api/middleware/auth.py`, `api/middleware/rate_limit.py`). A Pro account
that exceeds either monthly cap is **hard-downgraded to Free for the
rest of the billing period**, not charged overage — an explicit,
already-shipped decision (`docs/plan-monetization-implementation.md`
§8), not something this document proposes changing.

This means "tiered by usage" isn't a pricing-strategy choice being made
here — the usage tiers already exist in the enforcement code. What's
missing is a price attached to the middle one.

## 2. What the tiers actually cost pyvar to run

Per `docs/p9-scenario-volume-cost-audit.md` and the Iron Triangle
cost-breakdown chart (`docs/publications/pyvar-iron-triangle-medium-article.md`):

- **Fixed infrastructure baseline: $900–1,000/month**, a real, confirmed
  AWS invoice (2026-08-31) — dominated by VPC endpoints, NAT Gateway,
  ElastiCache, and Aurora/Fargate floors, not by job volume.
- **Marginal compute cost: well under $0.12/month even at 1,000,000
  Monte Carlo scenarios** — two independent benchmarks confirm this is
  sub-cent per scenario, and the fixed baseline is effectively flat
  across 10,000 to 1,000,000 scenarios/month.

The practical consequence for pricing: **Pro's 2,000,000-simulation
monthly cap costs pyvar approximately nothing in incremental compute.**
The entire cost question is "how many Pro subscribers does it take to
cover the fixed floor," not "what does each simulation cost" — the same
conclusion `pyvar-monetization-strategy.docx`'s three scenarios already
reach, restated here as the actual basis for the number below rather
than an aside.

## 3. The proposed price

**Pro: $65/month.**

This confirms, rather than revises, the figure the monetization
scenarios already model — deliberately, so the two documents don't
quietly disagree with each other. The reasoning, independent of that
precedent:

- **Coverage math.** At $65/month, 14 Pro subscribers ($910) cover the
  low end of the real $900–1,000/month fixed-cost range, and 16 ($1,040)
  cover the top — Pro subscriptions alone, with no Enterprise deal or
  grant funding, close the entire fixed-cost gap at roughly 14–16
  subscribers. The monetization
  doc's own Neutral scenario (25 Pro subscribers, one Enterprise deal,
  three pyvar Local nodes, one professional-services engagement) already
  clears fixed cost with a $4,333/month surplus at this price — this
  isn't a number chosen in isolation from that model, it's the same
  number checked against it.
- **What $65/month actually buys**, concretely, not just "higher
  limits": 10x Free's per-request simulation ceiling (100,000 vs.
  10,000), 50x Free's daily request cap (500 vs. 10/day), and a real
  monthly ceiling (5,000 requests, 2,000,000 simulations) Free doesn't
  have at all because Free's own daily cap already bounds it tightly
  enough not to need one.
- **Margin at this price is not thin.** Since marginal compute cost per
  subscriber is sub-cent-scale even at the monthly cap, $65/month is
  overwhelmingly margin once fixed-cost coverage is met by other
  subscribers — the real constraint on Pro pricing is what the market
  will pay, not what serving a Pro account costs.
- **No annual option, deliberately, for now.** The existing Stripe
  integration is monthly-only, no trial — an explicit Phase A decision
  (`docs/plan-monetization-implementation.md`), not an oversight this
  document is silently working around. An annual price (e.g. a
  two-months-free equivalent) is a reasonable Phase B addition, flagged
  here as future scope, not priced or committed to now.

## 4. Free and Enterprise, for completeness

- **Free: $0/month**, unchanged, no card required. 10 requests/day
  across all 385 functions is enough to evaluate the API but not to run
  a real workflow against it — the free tier is explicitly a
  full-access trial surface, not a crippled one (every function is
  available, just rate-limited).
- **Enterprise: still "Contact us," deliberately not a list price.**
  This matches the explicit, already-made decision that Enterprise stays
  a manual sales conversation, not a self-serve price
  (`docs/plan-monetization-implementation.md`). For internal planning
  only — not for publication — the monetization scenarios' own
  illustrative average deal size (~$25,000/year, ~$2,083/month
  amortised) remains a reasonable placeholder for forecasting, unchanged
  by this document.

## 5. What this document does not change

- The hard-downgrade-not-overage policy for Pro accounts exceeding a
  monthly cap.
- Monthly-only billing (no annual tier live yet).
- Enterprise's manual, "Contact us" sales motion.
- The Free tier's existing limits.

Only one thing is new here: an actual $65/month price to attach to
`config.py`'s still-unset `stripe_price_id_pro`, reasoned independently
rather than assumed from the earlier illustrative figure, and found to
agree with it.

---

## Sources

- [`api/middleware/auth.py`](https://github.com/fibtecltd/pyvar/blob/master/api/middleware/auth.py) — `TokenPayload.max_simulations`, the per-tier simulation ceilings in the price-list table.
- [`api/middleware/rate_limit.py`](https://github.com/fibtecltd/pyvar/blob/master/api/middleware/rate_limit.py) — `enforce_compute_rate_limit`, the daily/monthly quota enforcement and exempt-tier logic.
- [`config.py`](https://github.com/fibtecltd/pyvar/blob/master/config.py) — `rate_limit_free_daily`, `rate_limit_pro_daily`, `rate_limit_pro_monthly_requests`, `rate_limit_pro_monthly_simulations`, `stripe_price_id_pro`.
- [`docs/plan-monetization-implementation.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/plan-monetization-implementation.md) — the monthly-only/no-trial/hard-downgrade/manual-Enterprise decisions this document doesn't revisit.
- [`docs/proposals/pyvar-monetization-strategy.docx`](https://github.com/fibtecltd/pyvar/blob/master/docs/proposals/pyvar-monetization-strategy.docx) — the pessimistic/neutral/optimistic scenario model this price is checked against.
- [`docs/p9-scenario-volume-cost-audit.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/p9-scenario-volume-cost-audit.md) — the real cost audit behind §2.
- [`docs/publications/pyvar-iron-triangle-medium-article.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/pyvar-iron-triangle-medium-article.md) — the cost-breakdown chart and real invoice figure.

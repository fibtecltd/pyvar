# Beyond the Bank Risk Desk: Additional Use Cases and Audiences for pyvar

**Draft, not published.** Prepared at Filippo's request, "extending pyvar
use cases" (second half — the first half, extending worked-example depth
within the existing 8 domains, shipped separately as 6 new
`pyvar-jupyter/examples/` notebooks). Every function cited below is
checked directly against `engine/` at drafting time — nothing here
proposes new engineering; it identifies audiences the **already-shipped**
385 functions already serve, that pyvar's current public materials don't
name. See **Sources** at the end.

---

## Why this is worth writing down

Every existing pyvar guide and article is framed around a bank's risk
desk: Basel III/IV capital, FRTB, IRRBB, a trading or credit committee.
That's accurate as far as it goes, but it undersells the codebase. A grep
across `engine/reg_solvency.py`, `reg_mifid_emir.py`, and `credit_ccr.py`
alone turns up regulatory-grade functions for fund managers, insurers,
trading venues, and any EMIR-in-scope counterparty — none of which is "a
bank." The domain skills and Jupyter examples are organised by *risk
type* (market, credit, liquidity...); this document is organised by *who
actually buys or uses it*, which cuts across those domains rather than
adding an eighth one.

None of the six audiences below need a single new function. What they
need is someone to say, in public materials, "this already covers you" —
which today, nothing does.

---

## 1. Fund managers — AIFMD and UCITS, not Basel

**The gap:** every existing use-case description (`portal/guide-claude-plugins.html`'s
own use-case table, the domain skills) frames Portfolio Analytics as a
bank's own book, and Regulatory as Basel/FRTB/MiFID/EMIR/Solvency II —
never AIFMD or UCITS by name, even though both already exist.

**What's already there:** `engine/reg_solvency.py` ships
`aifmd_risk_metrics` (AIFMD Annex IV risk reporting for alternative
investment funds) and `ucits_kiid_risk_indicator` (the UCITS KIID
synthetic risk-and-reward indicator, the 1–7 scale on every UCITS fund
factsheet). Paired with the existing Portfolio Analytics domain — mean-
variance/Black-Litterman/risk-parity optimisation, Brinson attribution,
ESG integration — a fund manager gets portfolio construction *and* the
fund-level regulatory reporting both AIFMD and UCITS require, from the
same API key.

**Who this actually is:** an AIFM (alternative investment fund manager —
hedge fund, private equity, real assets) or a UCITS management company's
risk function, not a bank's trading desk at all. A genuinely different
buyer, with a genuinely different compliance calendar (Annex IV filings,
KIID updates), that today has no reason to think pyvar is relevant to
them.

## 2. Insurers — Solvency II SCR

**The gap:** Solvency II appears once in existing materials, as a single
bullet in the Regulatory skill's description ("running a Solvency II SCR
calculation") — accurate, but a single bullet undersells what's there and
insurers aren't named as an audience anywhere.

**What's already there:** `solvency_ii_scr_market_risk` and
`solvency_ii_scr_credit_risk` (`engine/reg_solvency.py`) — the two
largest sub-modules of the Solvency II Standard Formula SCR, computed
independently and combinable via the standard correlation-matrix
aggregation the regulation specifies (not shipped as a single combined
function here, deliberately — see the module's own docstring on why
market and credit SCR are kept as separable building blocks rather than
one opaque "total SCR" call).

**Who this actually is:** a European (re)insurer's actuarial or risk
function computing standard-formula capital — a market entirely distinct
from Basel-regulated banks, currently addressed nowhere in pyvar's
positioning beyond that one bullet.

## 3. Investment firms and trading venues — MiFID II beyond "transaction reporting"

**The gap:** every existing mention of MiFID II is the same three words,
"MiFID II transaction-reporting scope" — one function out of the nine
`engine/reg_mifid_emir.py` actually ships.

**What's already there, and not currently named anywhere public:**
`mifid_ii_pre_trade_transparency`, `mifid_ii_post_trade_transparency`,
`mifid_ii_best_execution_metric`, `mifid_ii_algorithm_documentation` (RTS
6 algo-trading documentation), plus the EMIR side of the same module —
`emir_clearing_obligation_check`, `emir_margin_requirement`,
`emir_trade_repository_report` — and `sftr_securities_finance_report`
(Securities Financing Transactions Regulation, repo and securities-
lending reporting).

**Who this actually is:** an investment firm, broker-dealer, or trading
venue's compliance function — best-execution monitoring, pre/post-trade
transparency checks, RTS 6 algo documentation — a buyer whose problem
isn't risk *measurement* at all, it's regulatory *reporting and
monitoring*, currently invisible in how pyvar describes itself.

## 4. Any EMIR-in-scope counterparty — including non-bank corporates

**The gap:** EMIR is currently framed as a bank concern (grouped with
Basel/FRTB in every existing mention). EMIR's actual scope is much wider
— any counterparty trading OTC derivatives above the clearing threshold,
bank or not.

**What's already there:** the same EMIR functions as §3
(`emir_clearing_obligation_check`, `emir_margin_requirement`,
`emir_trade_repository_report`) apply identically to a non-financial
corporate hedging FX or commodity exposure with derivatives, once it
crosses EMIR's clearing threshold — a real, distinct compliance
obligation that has nothing to do with being a bank.

**Who this actually is:** a corporate treasury function (an airline
hedging jet fuel, a manufacturer hedging FX) that trades enough OTC
derivatives to be EMIR-in-scope, and currently has no compliance-reporting
tool that isn't either a bank-grade platform priced for banks or a
manual spreadsheet process.

## 5. Structured-products and exotic-derivatives desks

**The gap:** `engine/deriv_options_exotic.py` ships eight distinct exotic
payoff types; existing materials mention "options (vanilla, exotic,
stochastic vol)" as one item in a longer Derivatives-domain description,
which reads as one function among many rather than the eight-payoff
structuring toolkit it actually is.

**What's already there:** digital, barrier, Asian, lookback, American
(LSM), Bermudan, rainbow, and basket option pricers, plus compound
options and the four stochastic-vol models (Heston/SABR/Dupire/rBergomi)
and Variance Gamma/NIG in `engine/deriv_stoch_vol.py` — enough breadth to
structure and price most retail and institutional structured-note payoff
types without a second, specialist vendor.

**Who this actually is:** a structuring desk or a smaller institution
that currently pays for a dedicated exotic-derivatives pricing library
(Numerix, FINCAD, or similar) on top of its main risk platform, not
realising pyvar's own Derivatives domain already covers most of that
payoff space.

## 6. RegTech, audit, and academia — the "independent second opinion" use case

**The gap:** every existing article frames pyvar as a primary risk
engine a firm runs its own book through. It doesn't currently mention
the adjacent use case its own honesty framing (self-found bugs published
openly, 627-assertion validation suite, Apache-2.0 source) makes it
unusually well-suited for: being someone else's *challenger* model.

**What's already there, requiring nothing new:** free-tier access to
all 385 functions, an Apache-2.0 licence, and a public, re-run-per-
release validation suite (`tests/validation/`) cross-checked against
closed-form references and QuantLib — exactly the properties a risk
consultancy or internal audit function needs to independently re-derive
a client's or a business unit's own risk numbers as a challenge, and
exactly the properties a lecturer needs to give students a real,
regulatory-grade engine to work against instead of a toy model.

**Who this actually is:** two distinct groups, tied together by the same
underlying property (an open, checkable, free-to-use engine): risk
consultancies/internal audit functions doing independent model
validation, and academic teaching/research use. Neither is a commercial
Pro-tier prospect on its own in the near term, but both are credibility-
building and community-building in ways the Comparison field of the
NLnet application already leans on without naming this specific use case
explicitly.

---

## What this changes, concretely

None of the above requires new engine code, new schemas, or new API
routes — every function cited is already shipped, tested, and live. What
it suggests, as follow-on work distinct from this document itself:

- The `portal/guide-claude-plugins.html` use-case table (`Skill | Use
  case`) currently names one audience per skill, framed around a bank
  desk. It could gain a second audience column, or a short "who else
  this is for" note per relevant row (Regulatory → also insurers and
  investment firms; Portfolio Analytics → also fund managers; Derivatives
  → also structuring desks) — not proposed as an edit here, since it
  touches an already-live portal page, but the case for it is made above.
- The pricing/monetization work (`docs/proposals/pyvar-monetization-
  strategy.docx`, the new Pro-tier price list) can reasonably assume a
  broader prospective Pro-tier base than "banks" alone once this framing
  is public — relevant context for that document, not incorporated into
  it here without a separate decision on scope.

---

## Sources

- [`engine/reg_solvency.py`](https://github.com/fibtecltd/pyvar/blob/master/engine/reg_solvency.py) — `aifmd_risk_metrics`, `ucits_kiid_risk_indicator`, `solvency_ii_scr_market_risk`, `solvency_ii_scr_credit_risk`.
- [`engine/reg_mifid_emir.py`](https://github.com/fibtecltd/pyvar/blob/master/engine/reg_mifid_emir.py) — the full MiFID II/EMIR/SFTR function set cited in §3–4.
- [`engine/deriv_options_exotic.py`](https://github.com/fibtecltd/pyvar/blob/master/engine/deriv_options_exotic.py), [`deriv_stoch_vol.py`](https://github.com/fibtecltd/pyvar/blob/master/engine/deriv_stoch_vol.py) — the exotic-payoff and stochastic-vol function set cited in §5.
- [`engine/credit_ccr.py`](https://github.com/fibtecltd/pyvar/blob/master/engine/credit_ccr.py) — counterparty credit risk functions, relevant context for §4's EMIR-margin audience.
- [`tests/validation/`](https://github.com/fibtecltd/pyvar/tree/master/tests/validation) — the 627-assertion, 8-domain validation suite underpinning §6's "independent second opinion" claim.
- [`portal/guide-claude-plugins.html`](https://github.com/fibtecltd/pyvar/blob/master/portal/guide-claude-plugins.html), [`docs/publications/assets/tables/plugins-usecase-table.svg`](https://github.com/fibtecltd/pyvar/blob/master/docs/publications/assets/tables/plugins-usecase-table.svg) — the existing, bank-desk-framed use-case table this document extends without editing.
- [`docs/proposals/nlnet-restack-form-answers.md`](https://github.com/fibtecltd/pyvar/blob/master/docs/proposals/nlnet-restack-form-answers.md) — the Comparison field's existing "independent, auditable correctness" framing that §6 draws on directly.

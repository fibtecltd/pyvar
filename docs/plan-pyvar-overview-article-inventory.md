# Inventory for the "what pyvar does" Medium article

Working document for the overview article: all existing pyvar features and use-cases, for two readers at
once, engineers and quant developers on one side, business and finance subject-matter experts on the
other. Everything below carries its source. Items marked **(check)** are not verified from this clone
and need a decision or a check before they go into the article.

---

## 1. The platform in one screen

| Fact | Value | Source |
|---|---|---|
| Functions | 385, in 8 domains | `portal/functions.json` (counted: 385) |
| Licence | Apache-2.0, open source | `LICENSE`, README |
| Hosted API | `https://www.pyvar.com`, free to try | README |
| Compute | NumPy, Numba JIT (84 of the 389 functions in `engine/`, 13 parallel; 4 of the 389 are internal helpers, hence 385 on the API), SciPy, Polars, PyArrow | README |
| Job pipeline | FastAPI, Celery, SQS FIFO, EC2 Spot workers that scale to zero, Aurora Serverless v2, ElastiCache | README, `pyvar-cdk/stacks/` |
| Result delivery | poll `GET /var/result/{id}`, or push over `WS /var/stream/{id}` (stream token, 60 s) | `api/routes/var.py`, streaming article |
| Cost to run the hosted stack | about $900-1,000 a month, mostly fixed infrastructure, not job volume | README (real prod invoice, 2026-08-31) |
| Speed | 371 of 386 example calls have a median under 50 ms in-process (median 5.9 ms); the slowest, rBergomi, about 4 s; 100,000 Monte Carlo paths in about 2-10 s on the job path | `docs/data/streaming-phase0d-latency.csv`; deep-dive and iron-triangle articles |
| First-call cost | `run_monte_carlo_var` 1.083 s cold, 0.007 s warm; workers are pre-baked, so compile cost is not paid per job | technical deep-dive article |
| Tiers | Free 10,000 simulations and 10 calls a day; Pro 100,000 and 500 a day; Enterprise 500,000, unlimited, sales-assisted | `config.py`, REST guide |
| Keys and sign-in | email link or Google; API key `pyvar_...` lasts a year, max 5 active; session token 60 min | README, `config.py` |
| Tests | 1,236 pass in the suite; 8 validation suites with 685 `def test_` functions, each checked against an external reference | `pytest`; `tests/validation/` (counted) |
| AI-assisted build | disclosed, with a `Co-Authored-By: Claude` trailer on commits | README "Use of Generative AI" |

## 2. The eight domains

| Domain | Functions | What a reader should take from it | Standout functions |
|---|---|---|---|
| Market risk | 71 | VaR and Expected Shortfall at the Basel 99% and FRTB 97.5% levels, backtesting, stress, P&L attribution, FRTB capital | `historical_simulation_var`, `historical_expected_shortfall`, `traffic_light_backtesting`, `kupiec_pof_test`, `frtb_ima_aggregate_capital_charge`, `pnl_attribution_test_frtb_pat`, `reverse_stress_testing`, `cvar_decomposition_euler` |
| Derivatives and pricing | 62 | options (vanilla, exotic, Monte Carlo, trees), bonds, curves, swaps, stochastic-volatility models | `black_scholes_european_option`, `american_option_lsm`, `heston_stochastic_volatility_model`, `sabr_volatility_model`, `rough_volatility_rbergomi_model`, `swaption_pricer_black`, `bootstrap_yield_curve` |
| Credit risk | 55 | PD/LGD/EAD, expected and unexpected loss, credit VaR, IRB capital, IFRS 9 ECL, counterparty risk and XVA | `expected_loss_el_computation`, `credit_var_analytical_vasicek`, `irb_advanced_approach_capital`, `ifrs_9_scenario_weighted_ecl`, `standardised_approach_ccr_sa_ccr`, `credit_valuation_adjustment_cva`, `altman_z_score_credit_scoring` |
| Portfolio analytics | 50 | optimisation, risk-adjusted returns, factor models, attribution, drawdown, ESG | `mean_variance_optimisation`, `black_litterman_model`, `risk_parity_portfolio`, `fama_french_5_factor_model`, `return_attribution_brinson`, `sharpe_ratio`, `maximum_drawdown` |
| Operational risk | 44 | Basel SMA, loss distribution approach, RCSA, KRIs, scenarios, cyber, model and vendor risk | `basel_standardised_measurement_sma`, `loss_distribution_approach_lda`, `operational_var_opvar`, `kri_threshold_breach_detection`, `cyber_risk_loss_estimation`, `third_party_vendor_risk` |
| Liquidity risk | 40 | LCR, NSFR, HQLA, cash-flow ladders, stress, survival horizon, intraday, ILAAP | `liquidity_coverage_ratio_lcr`, `net_stable_funding_ratio_nsfr`, `survival_horizon_calculator`, `liquidity_var_liqvar`, `ilaap_stress_testing_framework` |
| ALM and balance sheet | 33 | interest-rate risk in the banking book, EVE and NII, gaps, behavioural models, funds transfer pricing | `irrbb_six_standard_rate_shocks`, `economic_value_of_equity_eve`, `duration_gap_analysis`, `repricing_gap_analysis`, `non_maturity_deposit_stability`, `funds_transfer_pricing_ftp` |
| Regulatory and compliance | 30 | capital ratios and buffers, the Basel IV output floor, ICAAP and SREP, EMIR, SFTR, MiFID II, Solvency II, UCITS, AIFMD | `basel_iii_cet1_ratio`, `basel_iv_output_floor`, `combined_buffer_requirement`, `icaap_capital_assessment`, `emir_margin_requirement`, `solvency_ii_scr_market_risk`, `ucits_kiid_risk_indicator` |

Regulatory frameworks named in the code and docs: Basel III and IV, FRTB (SA and IMA), IRRBB, IFRS 9,
CRR2, ICAAP, ILAAP, SREP, EMIR, SFTR, MiFID II, Solvency II, UCITS, AIFMD.

## 3. Ways in

| Surface | For whom | How | Source |
|---|---|---|---|
| REST API | any language, integrators | `POST /api/v1/<domain>/<function>`, JSON in and out; `curl` is enough | REST guide |
| `pyvar-client` 0.3.0 | Python developers | `pip install pyvar-client`; one typed method per function, error classes, retries, a `pyvar` CLI | client guide |
| `pyvar-jupyter` 0.1.0 | analysts and quants in notebooks | `%pyvar` and `%%pyvar` magics; nine worked notebooks, one per domain | Jupyter guide, domain-examples article |
| Claude Code plugins, 14 | anyone who prefers to ask in plain language | 8 domain skills, 5 architecture skills, 1 MCP server | `marketplace.json`, plugins articles |
| `pyvar-mcp` 0.2.1 | AI-agent workflows | 387 tools (385 functions plus 2 generic ones), `uvx pyvar-mcp` | `docs/plugin-examples.md` |
| `pyvar-local` | institutions whose data may not leave the building | the engine and a CLI in a Docker image, no API key, no network | local-release article |
| `pyvar-full` | teams that want the whole platform on their own infrastructure | `docker compose up`: API, worker, Redis, Postgres, migrations | full-docker article |
| Streaming | dashboards and UIs that wait on a Monte Carlo job | `WS /var/stream/{id}`; token from `POST /var/stream-token/{id}` | streaming article |
| Dashboard and Streamlit UI | people who want to click | API keys on the dashboard; `ui/app.py` parameter UI | `portal/dashboard.html`, `ui/app.py` |

The same call returns the same result on every surface: `docs/plugin-examples.md` runs one expected-loss
call through REST, the client, the notebook magic and MCP and fails if they differ (expected loss 9,000
on a 1,000,000 exposure at 2% PD and 45% LGD).

## 4. Verified worked examples (reuse these, not invented numbers)

All come from `docs/plugin-examples.md`, produced by `scripts/generate_plugin_examples.py` against the
real application with synthetic inputs and fixed seeds. They are safe to quote with their inputs.

| Persona question | Call | Result worth quoting |
|---|---|---|
| "What is my one-day 99% VaR on a 10m book, and my FRTB ES?" | `historical_simulation_var`, `historical_expected_shortfall` | 99% VaR 238,046 (2.38%), CVaR 290,838; 97.5% ES 245,467 over 13 tail days of 500 |
| "Is my VaR model any good?" | `traffic_light_backtesting`, `basel_capital_addon_multiplier`, `kupiec_pof_test` | 7 breaches in 250 days: Basel yellow zone, multiplier 3.65, Kupiec LR 5.50 against 3.84 (p = 0.019), model rejected |
| "What capital does a 50m corporate loan need?" | `expected_loss_el_computation`, `credit_var_analytical_vasicek` | EL 450,000 (0.9%); Vasicek 99.9% credit VaR 3,967,401; unexpected loss 3,517,401 |
| "Which of three borrowers is in distress?" | `altman_z_score_credit_scoring` | Z 3.061 safe, 2.667 grey, 0.18 distress, with the five ratios returned so it can be checked by hand |
| "Do we meet LCR and NSFR?" | `liquidity_coverage_ratio_lcr`, `net_stable_funding_ratio_nsfr` | LCR 109.1% (120m HQLA over 110m net outflows), NSFR 106.5% |
| "How long does the buffer last?" | `survival_horizon_calculator` | survives 10 full days, exhausted during day 11 |
| "What does Basel SMA capital look like?" | `basel_standardised_measurement_sma` | 3bn Business Indicator: BIC 420m, capital 227,356,439 with no losses; a 12bn bank with a 2.5bn loss component 1,965,924,206 |
| "Where are our KRIs breaching?" | `kri_threshold_breach_detection` | 14 failed trades is red, 9.5 amber; a falling straight-through rate flagged in the right direction |
| "How should we weight this portfolio?" | `minimum_variance_portfolio`, `risk_parity_portfolio` | min variance 3.79% volatility concentrated in two assets; risk parity equal risk contributions at 5.36% |
| "How did the strategy perform?" | `sharpe_ratio`, `sortino_ratio`, `maximum_drawdown` | Sharpe 0.69, Sortino 0.99, maximum drawdown 29.6% with peak and trough dates |
| "Are we above the capital minimums?" | `basel_iii_cet1_ratio`, `combined_buffer_requirement`, `basel_iii_leverage_ratio` | CET1 12.68% (8.18% over the minimum), combined buffer 4.5% = 1.845bn, leverage 3.63% |
| "Does the output floor bind?" | `basel_iv_output_floor` | floor 72.5% of 41bn = 29.725bn, above the 28bn internal figure, so RWA rises by 1.725bn |
| "What is this option worth, and its Greeks?" | `black_scholes_european_option`, `black_scholes_greeks` | call 4.9371, put 7.8580, put-call parity holds to four places |
| "How much does the bond move if rates rise 50bp?" | `bond_pricer_fixed_coupon`, `modified_duration`, `convexity` | price 96.1027, duration 7.9191; estimate -3.7148 against a full reprice of -3.7163 |
| "What does a rate shock do to equity value?" | `duration_gap_analysis`, `irrbb_six_standard_rate_shocks` | +200bp moves EVE by -177.6m (22.2% of 800m equity); worst of the six BCBS shocks is 9.1% of Tier 1, under the 15% outlier test |

Reproducibility (a point for both readers): two runs with seed 42 are bit-identical, VaR scales linearly
with portfolio value, 99% VaR exceeds 95% VaR, CVaR is at least VaR; more paths tighten the estimate
(spread 0.00231 at 1,000 paths, 0.00014 at 1,000,000).

## 5. Personas and what each one gets

| Persona | The question they bring | Domains and surfaces |
|---|---|---|
| Quant developer or risk engineer | "Give me a tested, fast, scriptable calculator, and let me read the formula." | all domains; `pyvar-client`, notebooks, REST; the engine is readable Apache-2.0 source; seeds make runs reproducible |
| Market-risk manager | "Show me VaR and ES at the regulatory levels, then prove the model is backtested." | market risk; the backtesting chain; FRTB charges and the P&L attribution test |
| Credit-risk analyst | "What are expected and unexpected loss, ECL and counterparty exposure?" | credit risk; IRB, IFRS 9, SA-CCR, XVA |
| Treasurer, ALM and liquidity | "Are we within LCR, NSFR and the IRRBB outlier test, and for how long would the buffer hold?" | liquidity and ALM; ILAAP, six BCBS shocks, FTP |
| Operational-risk and GRC lead | "What is our SMA capital, and which indicators are breaching?" | operational risk; RCSA, KRIs, scenarios, cyber, vendor |
| Compliance and regulatory reporting | "Do we clear the ratios and buffers, and are our reports valid?" | regulatory; Basel IV floor, ICAAP, EMIR, SFTR, MiFID II, Solvency II, UCITS |
| Portfolio manager or researcher | "Optimise, attribute and explain performance." | portfolio analytics; Black-Litterman, factor models, Brinson |
| Valuation or derivatives desk | "Price this, and give me the Greeks and the curve." | derivatives; trees, Monte Carlo, stochastic volatility, curves |
| CFO, COO or head of risk (the buyer) | "What does it cost, can we audit it, can the data stay inside?" | open source, no per-seat licence, free tier, `pyvar-local` and `pyvar-full`, an audit table of every job, about $900-1,000 a month to run the hosted stack |
| Anyone working with an AI assistant | "Ask in plain language and get a computed number, not an explanation." | the 14 Claude plugins and `pyvar-mcp` |

## 6. Trust: what to say, and what not to say

What the repository supports:
- **External reference validation.** 8 suites; every assertion compares a function against an independent
  reference (closed form, scipy, a cited BCBS, IFRS or EBA formula, or a hand calculation), never against
  its own output. Regulatory boundaries are checked with zero tolerance (CET1 4.5%, leverage 3%, output
  floor 72.5%, the 250-day Basel window, green below 5, yellow 5-9, red 10 or more).
- **Honesty about gaps.** Each suite lists its known limitations. Examples: `icaap_capital_assessment`
  and `pillar_2b_stress_buffer` have no published formula to check (the rules mandate the assessment, not
  a calculation); `downturn_lgd_adjustment` uses a 1.25x multiplier where EBA/GL/2019/03 specifies an
  additive +15 percentage points.
- **A real bug story.** The first Solvency II draft understated required capital by about 79%, and was
  caught by the validation suite before production (build-story article).
- **Disclosure.** AI-assisted build is stated in the README; the disclaimer says outputs are not
  regulatory, financial or legal advice and are not a substitute for a firm's own model validation.

Do not write:
- "regulatory-grade" or "Basel-compliant" without the caveat that pyvar is **not independently
  validated for regulatory use** (README). Prefer "cross-validated against published formulas".
- anything quoted from the portal's domain pages: `portal/domain-*.html` carry illustrative outputs with
  invented sterling figures (for example "delta_eve: -£14,200,000"). They are mock-ups, not results.
- commit counts, until they are taken from a full clone (see section 8).

## 7. Operations and architecture, for the engineer lane

- The Numba kernels follow strict rules (stateless, float64, pre-drawn random numbers, `cache=True`); the
  first call compiles, so workers are pre-baked and warmed up.
- Async job pipeline: FastAPI, Celery over SQS FIFO with `task_acks_late` so a reclaimed Spot instance
  does not lose a job; workers scale to zero and cost nothing when the queue is empty (a cold start takes
  about 2.5 to 3 minutes on dev).
- Large results (above 10,000 simulations) go to S3 as Parquet and come back as a presigned URL.
- Security: keys stored as SHA-256 only; tier read from the database; stream tokens that carry an audience
  and expire in 60 s; input validation at the edge (confidence level outside 0.90-0.9999 is a 422).
- Cost: dominated by fixed infrastructure; Monte Carlo compute is sub-cent per scenario.

## 8. Existing articles, and what the overview should not repeat

| Article | Covers | In the overview |
|---|---|---|
| Build story | how it was built with Claude Code; the Solvency II bug | one paragraph in the trust section, link |
| Technical deep dive | Numba, Spot workers, scale-to-zero | link from the engineer lane |
| Iron triangle | cost, speed, accuracy | link |
| Post-launch lessons | what broke in two weeks | skip, or one line |
| REST guide, client guide, Jupyter guide, domain examples | the surfaces in depth | one row each in the "ways in" table, linked |
| 14 plugins, plugin examples, end to end, "pyvar Today" | the Claude surface | one row, linked |
| pyvar Local, pyvar Full | self-hosting | one row each, linked |
| Streaming | WebSocket result delivery | one row, linked |

## 9. Things to fix or decide before writing

1. **Commit counts disagree.** README: 222 of 677 commits; build story: 649 commits, 131 co-authored. This
   clone is shallow (66 commits), so neither can be checked here. Avoid, or verify on a full clone.
2. **Stale HTML title.** `medium-ready/pyvar-plugins-live-recent-updates-medium-article.html` has the
   `<title>` "13 Live Plugins" while its headline says 14.
3. **Validation counts.** The iron-triangle article says 627 assertions across 8 suites; counting
   `def test_` today gives 685. Pick one definition and state it.
4. **Pro price.** It is a Stripe price ID, not in the repository. The article needs the price, or should
   not state one.
5. **Hosted URL and streaming.** Examples in the streaming article use `dev.pyvar.com` by decision. For
   the overview, say which URL to show (`www.pyvar.com`) and whether streaming is mentioned as live.
6. **Illustrative portal figures** should be corrected or labelled as mock-ups on the site itself.

## 10. Angles and figures to consider

Angles (pick one for the hook):
- *The same number, three ways:* one VaR call as a quant (three lines of Python), as a risk manager (a
  backtesting verdict) and as a CFO (a cost and audit line).
- *385 questions your risk function gets asked:* the eight domains as eight desks, one real question each.
- *The calculator you can read:* every formula and regulatory constant is a line of code; what that means
  for an engineer who must trust it and a finance lead who must defend it.

Figures that can be drawn from repository data, in the house style:
- the eight domains as a map with their function counts (385 from `functions.json`);
- a persona-by-domain grid (who reaches for what);
- the latency spread (371 of 386 under 50 ms, `streaming-phase0d-latency.csv`);
- "one call, five surfaces" (`docs/publications/assets/three_surfaces.png` exists);
- header tiles: 385 functions, 8 domains, 14 plugins, 3 Python packages.

Open questions for Filippo:
1. How much weight for each lane (engineers, business), and the title tone.
2. Whether to name the Pro price, and which URL to show.
3. How prominent the AI-assisted build should be.
4. One long article (about 2,500 words) or this one plus three short follow-ups per persona.

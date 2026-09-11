# Claude Code plugin marketplace — per-plugin submission content

**Prepared per `docs/plan-plugin-marketplace-status-and-submission.md` §3**
("if the mechanism turns out to be per-plugin: work through the remaining
12 (or 13) plugins using the same submission form"). Drafted proactively —
before the open question of whether `claude-plugins-community`'s submission
form wants one entry per plugin or one entry for the whole
`pyvar-marketplace` bundle is resolved — so it's ready the moment that's
confirmed, rather than blocking on it. If the bundle-level submission (see
`docs/proposals/marketplace-submission-content.md`) already covers
everything, this file simply isn't needed; nothing here contradicts it.

Every field below is pulled verbatim from this repository's own
already-committed, already-`claude plugin validate`-passing source —
`.claude/skills/*/SKILL.md` frontmatter, `plugins/*/.claude-plugin/plugin.json`
— not re-authored, so it can never drift from what's actually shipped.

**Shared across all 14 entries:**
- **Owner:** Fibtec Limited (https://fibtec.co.uk)
- **Repository:** https://github.com/fibtecltd/pyvar
- **Homepage:** https://pyvar.com
- **Licence:** Apache-2.0
- **Marketplace context (mention if the form allows a "part of" field):**
  ships as part of the `pyvar-marketplace` self-hosted marketplace
  (`.claude-plugin/marketplace.json`), installable today via
  `/plugin marketplace add fibtecltd/pyvar` regardless of this submission's
  outcome.

---

## 1. The 13 skill plugins

Every skill is **pure instructional content** — a `SKILL.md` reference file
teaching Claude domain conventions, function signatures, and regulatory
constants. **Security/trust disclosure, identical for all 13:** no code
execution, no network access, no external dependencies, no data collection
of any kind. Nothing a skill teaches Claude to do reaches outside the
conversation except via a REST call the user makes themselves (directly, or
through `pyvar-mcp`, submitted separately below).

### pyvar-market-risk
- **One-line pitch:** Activate for any market risk computation: VaR,
  Expected Shortfall, stress testing, Greeks, P&L attribution, backtesting,
  volatility modelling, or FRTB capital calculations. Covers 68 functions
  across 8 sub-domains.
- **Category/tags:** `market-risk`, `VaR`, `ES`, `greeks`, `stress-test`,
  `backtesting`, `FRTB`, `GARCH`, `volatility`, `PCA`, `monte-carlo`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/market-risk

### pyvar-credit-risk
- **One-line pitch:** Activate for credit risk: PD/LGD/EAD, IRB/SA capital,
  XVA, IFRS 9 ECL, CDS pricing, credit portfolio models, CCR, or credit
  scoring. Covers 55 functions across 10 sub-domains.
- **Category/tags:** `credit-risk`, `PD`, `LGD`, `EAD`, `IRB`, `XVA`, `CVA`,
  `IFRS9`, `ECL`, `CDS`, `CCR`, `SA-CCR`, `KMV`, `Merton`, `scoring`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/credit-risk

### pyvar-liquidity-risk
- **One-line pitch:** Activate for liquidity risk: LCR, NSFR, cash flow
  ladders, stress scenarios, ILAAP metrics, funding risk, intraday
  liquidity, or liquidity VaR. Covers 40 functions across 8 sub-domains.
- **Category/tags:** `liquidity-risk`, `LCR`, `NSFR`, `HQLA`, `cash-flow`,
  `ILAAP`, `survival-horizon`, `funding-risk`, `intraday`, `stress-test`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/liquidity-risk

### pyvar-operational-risk
- **One-line pitch:** Activate for operational risk: LDA, AMA, SMA capital,
  RCSA, KRI monitoring, scenario analysis, BEICF, cyber/model/IT/vendor
  risk, or OpRisk reporting. Covers 44 functions across 9 sub-domains.
- **Category/tags:** `operational-risk`, `LDA`, `AMA`, `SMA`, `OpVaR`,
  `RCSA`, `KRI`, `BEICF`, `scenario-analysis`, `cyber-risk`, `model-risk`,
  `EVT`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/operational-risk

### pyvar-portfolio-analytics
- **One-line pitch:** Activate for portfolio construction, optimisation,
  performance attribution, factor models, risk analytics, ESG integration,
  or drawdown analysis. Covers 50 functions across 7 sub-domains.
- **Category/tags:** `portfolio`, `optimisation`, `markowitz`,
  `black-litterman`, `risk-parity`, `sharpe`, `attribution`, `brinson`,
  `factor-model`, `FF5`, `PCA`, `HMM`, `ESG`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/portfolio-analytics

### pyvar-regulatory
- **One-line pitch:** Activate for regulatory capital, prudential
  reporting, MiFID II, EMIR, Basel III/IV, FRTB, ICAAP/SREP, Solvency II,
  or CRR2 calculations. Covers 30 functions across 7 regulatory frameworks.
- **Category/tags:** `regulatory`, `Basel-III`, `Basel-IV`, `FRTB`,
  `MiFID-II`, `EMIR`, `SFTR`, `ICAAP`, `SREP`, `CET1`, `Solvency-II`, `CRR2`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/regulatory

### pyvar-derivatives
- **One-line pitch:** Activate for derivatives pricing: options (vanilla,
  exotic, stochastic vol), fixed income, yield curves, interest rate
  derivatives, short-rate models, FX derivatives, or any instrument
  valuation task. Covers 62 functions across 9 sub-domains.
- **Category/tags:** `derivatives`, `options`, `Black-Scholes`, `Heston`,
  `SABR`, `Dupire`, `LSM`, `bonds`, `IRS`, `CDS`, `FX`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/derivatives

### pyvar-alm
- **One-line pitch:** Activate for ALM and balance sheet: duration gap,
  NII simulation, EVE, IRRBB (six shocks), repricing gap, NMD behavioural
  models, prepayment, FTP, or ALM stress testing. Covers 33 functions
  across 7 sub-domains.
- **Category/tags:** `ALM`, `NII`, `EVE`, `IRRBB`, `duration`,
  `repricing-gap`, `NMD`, `prepayment`, `FTP`, `convexity`, `basis-risk`,
  `pipeline-risk`, `balance-sheet`, `ICAAP`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/alm

### pyvar-arch-api-gateway
- **One-line pitch:** Activate when building or modifying pyvar's API
  gateway layer: FastAPI route design, Pydantic request/response models,
  JWT authentication, rate limiting, orjson serialisation, or OpenAPI
  schema generation.
- **Category/tags:** `fastapi`, `pydantic`, `JWT`, `orjson`,
  `rate-limiting`, `OpenAPI`, `CORS`, `middleware`, `authentication`,
  `api-gateway`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/arch/api-gateway

### pyvar-arch-data-ingestion
- **One-line pitch:** Activate when working on pyvar's data ingestion
  layer: Polars lazy scanning, filter pushdown, Parquet I/O, Arrow IPC,
  schema validation, or converting subscriber market data into
  pyvar-ready formats.
- **Category/tags:** `polars`, `pyarrow`, `parquet`, `arrow-ipc`,
  `data-ingestion`, `lazy-scan`, `filter-pushdown`, `schema`, `etl`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/arch/data-ingestion

### pyvar-arch-compute
- **One-line pitch:** Activate when implementing or optimising pyvar
  compute workers: NumPy vectorisation, Numba JIT for Monte Carlo loops,
  SciPy optimisation, Dask distributed DataFrames, or Ray multi-node
  scale-out. Also covers the Celery + Redis task queue dispatch pattern.
- **Category/tags:** `numpy`, `numba`, `scipy`, `dask`, `ray`, `celery`,
  `redis`, `JIT`, `monte-carlo`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/arch/compute

### pyvar-arch-storage
- **One-line pitch:** Activate when working on pyvar's storage layer:
  Redis result cache, PostgreSQL schema design, SQLAlchemy ORM models,
  PyArrow + S3/MinIO object storage, Parquet scenario files, or result
  TTL management.
- **Category/tags:** `redis`, `postgresql`, `sqlalchemy`, `s3`, `minio`,
  `parquet`, `arrow-ipc`, `storage`, `cache`, `orm`, `object-storage`,
  `result-store`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/arch/storage

### pyvar-arch-observability
- **One-line pitch:** Activate when working on pyvar's observability or
  security layer: Prometheus metrics, Grafana dashboards, Sentry error
  tracking, Bandit static analysis, input validation hardening, or
  security scanning of financial computation code.
- **Category/tags:** `prometheus`, `grafana`, `sentry`, `bandit`,
  `observability`, `monitoring`, `security-scanning`
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/arch/observability

---

## 2. pyvar-mcp (the 14th plugin — different disclosure shape)

- **One-line pitch:** MCP server exposing all 385 pyvar.com risk functions
  (VaR, credit, derivatives, liquidity, operational risk, portfolio
  analytics, ALM, regulatory) as Claude Code tools, via the live pyvar API.
- **Category/tags:** `finance`, `risk-management`, `mcp-server`,
  `quantitative-finance`, `api`
- **Security/trust disclosure** (reused verbatim from
  `docs/proposals/marketplace-submission-content.md`, the one place this
  detail already lives — not re-derived here):
  - Only external dependency is the pyvar REST API itself
    (`https://www.pyvar.com`, or a self-hosted instance) — no third-party
    services, no telemetry, no analytics.
  - **Data sent:** whatever parameters the user explicitly provides to a
    function call, over HTTPS with the user's own API key — exactly as if
    they had called the REST API directly. No portfolio or position data
    retained beyond pyvar's documented job-result TTL (VaR jobs only; the
    other 384 functions are synchronous with no persistence).
  - **Auth:** a free-tier pyvar API key, provided by the user during
    install via the plugin's `userConfig` (`sensitive: true`, never
    committed to source control — see `plugins/mcp/.claude-plugin/plugin.json`).
  - **One documented manual step:** Python dependencies (`mcp`, `anyio`)
    require a one-time `pip install -e plugins/mcp`, documented in
    `plugins/mcp/README.md` — flagged for transparency, not glossed over.
  - Open source, Apache-2.0-licensed, publicly auditable — every tool's
    behaviour is generated from and traceable to the actual REST API
    route it calls.
- **Link:** https://github.com/fibtecltd/pyvar/tree/master/plugins/mcp

---

## 3. What's still explicitly open (per the plan doc, unchanged by this file)

This content exists so it's ready to paste — it does not resolve any of
`docs/plan-plugin-marketplace-status-and-submission.md` §2's three open
questions (submission scope, review outcome, the MIT-correction decision
on the already-submitted `pyvar-mcp` form). Only Filippo can check the
authenticated submission form(s) to answer those.

# Figures for the plugin-examples article

Twelve images, in reading order, for `docs/publications/pyvar-plugin-examples-medium-article.md`. The HTML in `../../medium-ready/` already embeds them; use this list to drag each file to its position if Medium does not carry an image across on paste. Medium takes PNG/JPG only (no SVG).

Regenerate every image with `python scripts/generate_plugin_figures.py` (needs `matplotlib`); the numbers come from the same runs as `docs/plugin-examples.md`.

This list is derived from the article's image markers (file, alt text, caption, position).

## 1. `plugin-examples-header.png`

- **Where:** under the title and subtitle
- **Caption:** Eight of the twenty-eight results in this article, each produced by a real pyvar call.
- **Alt text:** Fourteen plugins, twenty-eight worked examples. Eight domain tiles show real results: 99% VaR 2.38%, expected loss 450,000, LCR 109.1%, SMA capital 227m, Sharpe ratio 0.69, CET1 ratio 12.68%, Black-Scholes call 4.9371, change in EVE minus 177.6m.

## 2. `plugin-examples-overview.png`

- **Where:** in the introduction, right after: “A plugin list tells you what exists. This article shows what each one does. Every plugin g…”
- **Caption:** Figure 1. The fourteen plugins and what they connect to. The eight domain plugins and the MCP server are two routes to the same API; the five architecture plugins document the layers behind it.
- **Alt text:** Diagram: you ask in Claude Code; eight domain plugins and the pyvar-mcp server both end at the pyvar.com REST API with 385 functions, which is served by five platform layers documented by the five architecture plugins.

## 3. `plugin-examples-var-es-tail.png`

- **Where:** in pyvar-market-risk, right after: “The 99% VaR is 2.38% of the book, 238,046. `historical_expected_shortfall` at the FRTB lev…”
- **Caption:** Figure 2. The 13 shaded days are the tail the Expected Shortfall averages; the markers show where the 99% VaR and the 97.5% ES fall.
- **Alt text:** Histogram of 500 daily returns with the 13 worst days shaded; vertical markers show the 99% VaR of 2.38 percent and the 97.5% expected shortfall of 2.45 percent.

## 4. `plugin-examples-backtest-breaches.png`

- **Where:** in pyvar-market-risk, right after: “A 99% VaR should be breached about 2.5 times in 250 days. Seven breaches is yellow, carrie…”
- **Caption:** Figure 3. Seven breaches put the model in the Basel yellow zone, with a capital multiplier of 3.65.
- **Alt text:** Bar chart of 250 daily returns against a 99% VaR line at minus 1.51 percent with seven breaches marked, above a Basel traffic-light strip showing seven breaches in the yellow zone and a capital multiplier of 3.65.

## 5. `plugin-examples-vasicek-loss.png`

- **Where:** in pyvar-credit-risk, right after: “Expected loss is 0.02 × 0.45 × 50,000,000 = 450,000. The Vasicek 99.9% loss is 3,967,401, …”
- **Caption:** Figure 4. Expected loss is priced; the distance from it to the 99.9% loss is what capital has to absorb.
- **Alt text:** Vasicek loss distribution for a 50 million exposure: expected loss of 450,000 and 99.9% credit VaR of 3,967,401, with the unexpected loss between them marked as economic capital.

## 6. `plugin-examples-liquidity-survival.png`

- **Where:** in pyvar-liquidity-risk, right after: “Cumulative outflows reach 94m after day 10 and 101m after day 11: the buffer survives ten …”
- **Caption:** Figure 5. Cumulative outflow crosses the 100m HQLA line during day 11.
- **Alt text:** Bar chart of cumulative net outflow over 12 days against a 100 million HQLA line; bars for days 11 and 12 (101m and 107m) exceed the line; ten full days are survived.

## 7. `plugin-examples-bond-price-yield.png`

- **Where:** in pyvar-derivatives, right after: “The two agree to within 0.0015 of price.”
- **Caption:** Figure 6. Duration alone drifts away from the true price curve; adding convexity tracks it, and at +50bp it lands within 0.0015.
- **Alt text:** Left: bond price against yield with duration-only and duration-plus-convexity approximations. Right: after a 50 basis point rise, full reprice 92.3864, duration plus convexity 92.3879, duration only 92.2975.

## 8. `plugin-examples-irrbb-shocks.png`

- **Where:** in pyvar-alm, right after: “The worst scenario is the parallel-up shock, at −81.9m, which is 9.1% of 900m of Tier 1 ca…”
- **Caption:** Figure 7. Parallel up is the worst of the six shocks at −81.9m, 9.1% of Tier 1, against the 15% outlier line at −135m.
- **Alt text:** Horizontal bar chart of the change in economic value of equity under six rate shocks; parallel up is the worst at minus 81.9 million, well inside the minus 135 million line that marks 15 percent of Tier 1 capital.

## 9. `plugin-examples-gateway-path.png`

- **Where:** in pyvar-arch-api-gateway, right after: “The JWT carries the tier, and the tier's simulation cap — 10,000 free, 100,000 pro, 500,00…”
- **Caption:** Figure 8. The order of the checks on the VaR endpoint. Domain endpoints run the first three, then the engine.
- **Alt text:** Flow chart of six checks on POST /api/v1/var/compute with their outcomes: JWT authentication 401, daily quota 429, request validation 422, result cache 200, tier simulation cap 403, audit row and dispatch 202.

## 10. `plugin-examples-compute-convergence.png`

- **Where:** in pyvar-arch-compute, right after: “More paths buy a tighter estimate at a cost that grows with the path count. The 10-day VaR…”
- **Caption:** Figure 9. The same data as the spreads above, in percentage points with the fraction in brackets: 0.231 (0.00231) at 1,000 paths, 0.014 (0.00014) at 1,000,000.
- **Alt text:** Scatter chart of the 99% VaR from five seeds at simulation counts from 1,000 to 1,000,000 on a log axis; the spread narrows from 0.231 percentage points to 0.014.

## 11. `plugin-examples-async-var-flow.png`

- **Where:** in pyvar-arch-storage, right after: “**Large results go to S3.** Above 10,000 simulations the worker writes the full result to …”
- **Caption:** Figure 10. The full life of a VaR job, from the POST to the polled result.
- **Alt text:** Sequence diagram of the asynchronous VaR path: client posts, API validates and writes an audit row, dispatches via a queue and returns 202; the worker runs the Monte Carlo and writes the result to Redis and, above 10,000 paths, to S3; the client polls and receives the result with a presigned link.

## 12. `plugin-examples-mcp-call-flow.png`

- **Where:** in Part three: pyvar-mcp, right after: “A missing parameter is caught before any request is made; an out-of-range value is rejecte…”
- **Caption:** Figure 11. One call, three failure paths. Each failure comes back as a readable tool result flagged is_error.
- **Alt text:** Flow chart of one MCP call: three entry tools reach the catalogue lookup and a required-parameter check inside pyvar-mcp, then an HTTPS request to the REST API; unknown function, missing parameter and API rejection return errors, and success returns JSON.

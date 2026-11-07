"""plugins/mcp/pyvar_mcp/_generated/derivatives.py — GENERATED, do not edit by hand.

The derivatives tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
repo root). Source: portal/functions.json -- see that script for the mapping.
"""

from __future__ import annotations

from typing import Any

# Each entry: domain, function_name (== the API's function name), tool_name (the
# MCP tool name -- currently identical to function_name; kept as a separate field
# in case a future disambiguation strategy needs to diverge the two), path (the
# real POST endpoint, relative to the API base URL), summary, description, and
# input_schema (JSON Schema, mapped directly from functions.json's params list).
FUNCTIONS: list[dict[str, Any]] = [
    {
        "description": "Allows early exercise at every time step. The price must be >= the "
        "European\n"
        "price of the same option.\n"
        "\n"
        "Note: the continuation value at each exercise date is fit by quadratic "
        "OLS\n"
        "regression on in-the-money paths rather than evaluated from a closed-form\n"
        "formula, and the opt-in Greeks use a spot bump roughly 30x larger than\n"
        "this module's smooth-payoff pricers because that regression-based\n"
        "exercise decision is discontinuous in spot.\n"
        "\n"
        "Deliberately has no qmc option (task #15 Phase 2 evaluated and rejected\n"
        "it for this function specifically -- see _price_by_qmc_replicates'\n"
        "docstring). Randomized-QMC replicates work cleanly for "
        "asian_option_pricer\n"
        "and lookback_option_pricer (simple path-average / path-extremum\n"
        "estimators) but introduce a real, non-vanishing pricing bias here: LSM's\n"
        "backward-induction step fits a cross-sectional OLS regression of\n"
        "continuation value against in-the-money paths at each exercise date, and\n"
        "that regression implicitly assumes the sampled points are independent.\n"
        "Scrambled Sobol paths are deliberately correlated (that correlation is\n"
        "exactly what gives QMC its variance reduction elsewhere), which biases\n"
        "the regression fit and, through it, the exercise decision. Measured at\n"
        "S=K=100, r=5%, sigma=20%, tau=1, n_steps=50 against a 200k-path plain-MC\n"
        "reference (~6.024): plain MC at n_simulations=6,000/20,000 is biased by\n"
        "only +0.03-0.04 (LSM's well-known small-sample low bias), while QMC\n"
        "replicates at the same total budget were biased by +0.08 to +0.31\n"
        "depending on replicate count/size -- shrinking as per-replicate path\n"
        "count grows into the thousands, but not vanishing by n_simulations=20k\n"
        "the way it does for Asian/lookback. Revisit only with a fix for the\n"
        "underlying regression-bias interaction (e.g. an in-sample/out-of-sample\n"
        "split for the regression fit), not by retuning replicate count alone.",
        "domain": "derivatives",
        "function_name": "american_option_lsm",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_bump_reprice_greeks``) "
                    "on the same pre-drawn "
                    "normals used for the "
                    "base price. Uses a "
                    "materially larger spot "
                    "bump than the "
                    "smooth-payoff products "
                    "(see "
                    "``_LSM_GREEKS_BUMP_REL_SPOT`` "
                    "for why) -- "
                    "delta/gamma are "
                    "therefore somewhat "
                    "coarser here than for "
                    "Asian/lookback, by "
                    "construction, not "
                    "oversight. Costs 8 "
                    "extra LSM reprices "
                    "(each as expensive as "
                    "the base price -- this "
                    "is the most expensive "
                    "Greeks call in this "
                    "module; consider a "
                    "smaller n_simulations "
                    "for greeks=True "
                    "requests if used "
                    "behind a "
                    "request-latency "
                    "budget). Defaults to "
                    "False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {"default": 50, "description": "Exercise dates.", "type": "integer"},
                "option_type": {
                    "default": "put",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 41, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/american_option_lsm",
        "summary": "American option price via Longstaff-Schwartz Monte Carlo (LSM).",
        "tool_name": "american_option_lsm",
    },
    {
        "description": "The averaging reduces volatility, so an Asian option is worth less than "
        "the\n"
        "corresponding vanilla European option.",
        "domain": "derivatives",
        "function_name": "asian_option_pricer",
        "input_schema": {
            "properties": {
                "average_type": {
                    "default": "arithmetic",
                    "description": '``"arithmetic"`` ' "(only).",
                    "type": "string",
                },
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_asian_greeks_bump_reprice``) "
                    "on the same pre-drawn "
                    "normals used for the "
                    "base price, so the "
                    "bump noise cancels "
                    "against the base run's "
                    "noise instead of "
                    "adding to it. Costs 8 "
                    "extra reprices at the "
                    "same "
                    "n_simulations/n_steps. "
                    "Not supported together "
                    "with qmc=True. "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {
                    "default": 100,
                    "description": "Averaging observation " "count.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "qmc": {
                    "default": False,
                    "description": "Use randomized "
                    "quasi-Monte Carlo "
                    "(scrambled Sobol "
                    "replicates, see "
                    "``_price_by_qmc_replicates``) "
                    "instead of plain MC for a "
                    "lower-variance estimate "
                    "at the same "
                    "n_simulations. Defaults "
                    "to False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 21, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/asian_option_pricer",
        "summary": "Arithmetic-average Asian option price via Monte Carlo.",
        "tool_name": "asian_option_pricer",
    },
    {
        "description": "The spread equating the bond's net present value to an annuity of the\n"
        "swap's fixed-leg PV01: ``ASW = (PV_bond − reference_price) / annuity``,\n"
        "expressed in basis points.\n"
        "\n"
        "By default (``use_market_price=False``), ``reference_price`` is\n"
        "``face_value`` (par) — this reproduces the function's original,\n"
        "par-referenced behaviour exactly and is unchanged for any existing\n"
        "caller. Set ``use_market_price=True`` to use the bond's actual dirty\n"
        "price instead, matching the standard market convention (O'Kane, 2000,\n"
        '"Introduction to Asset Swaps", Lehman Brothers): the spread is only\n'
        "equal to the par-referenced figure when the bond happens to trade at\n"
        "par, so for any bond away from par the market-convention spread and\n"
        "the par-referenced spread differ.",
        "domain": "derivatives",
        "function_name": "asset_swap_spread",
        "input_schema": {
            "properties": {
                "bond_price": {
                    "description": "Bond dirty price. "
                    "Used as the "
                    "reference price "
                    "only when "
                    "``use_market_price=True``; "
                    "otherwise accepted "
                    "but ignored (the "
                    "default preserves "
                    "this function's "
                    "original "
                    "par-referenced "
                    "behaviour).",
                    "type": "number",
                },
                "cashflows": {"description": "Bond cashflows.", "type": "object"},
                "face_value": {
                    "default": 100.0,
                    "description": "Par value. Used as "
                    "the reference "
                    "price when "
                    "``use_market_price=False`` "
                    "(the default).",
                    "type": "number",
                },
                "frequency": {
                    "default": 2,
                    "description": "Payment frequency " "per year.",
                    "type": "integer",
                },
                "swap_rates": {
                    "description": "Per-period swap " "zero rate " "(decimal).",
                    "type": "object",
                },
                "times": {"description": "Cashflow times (years).", "type": "object"},
                "use_market_price": {
                    "default": False,
                    "description": "If True, use "
                    "``bond_price`` "
                    "(the actual "
                    "dirty price) "
                    "as the "
                    "reference "
                    "price "
                    "instead of "
                    "``face_value``. "
                    "Default "
                    "False "
                    "preserves "
                    "prior "
                    "behaviour "
                    "exactly.",
                    "type": "boolean",
                },
            },
            "required": ["bond_price", "cashflows", "times", "swap_rates"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/asset_swap_spread",
        "summary": "Par-par asset-swap spread.",
        "tool_name": "asset_swap_spread",
    },
    {
        "description": "modelled rebate leg.\n"
        "\n"
        "Uses the in-out parity ``knock-in + knock-out = vanilla`` for the *pure*\n"
        "(no-rebate) option legs, so any of the four standard combinations is\n"
        "supported. A nonzero ``rebate`` adds the standard Reiner-Rubinstein cash\n"
        "rebate term on top of that pure leg: for a knock-in, the rebate is paid\n"
        'at expiry if the barrier is never touched (the "E" term below); for a\n'
        "knock-out, the rebate is paid at the moment the barrier is touched (the\n"
        '"F" term below) -- the standard two rebate conventions (Haug, *The\n'
        'Complete Guide to Option Pricing Formulas*, "Standard Barrier Options").\n'
        "\n"
        "Note: only the general Reiner-Rubinstein building blocks (A/B/C/D) are\n"
        "shown here — which combination prices the knock-in leg depends on\n"
        "``option_type``, ``barrier_type``, and whether strike exceeds barrier.",
        "domain": "derivatives",
        "function_name": "barrier_option_pricer",
        "input_schema": {
            "properties": {
                "barrier": {"description": "Barrier level.", "type": "number"},
                "barrier_type": {
                    "default": "down-and-out",
                    "description": "One of "
                    "``down-and-out``, "
                    "``down-and-in``, "
                    "``up-and-out``, "
                    "``up-and-in``.",
                    "type": "string",
                },
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "rebate": {
                    "default": 0.0,
                    "description": "Cash amount paid if "
                    "the option ends up "
                    "worthless because of "
                    "the barrier -- at "
                    "expiry (no touch) for "
                    "a knock-in, at the "
                    "touch time for a "
                    "knock-out. 0 (default) "
                    "reproduces the "
                    "no-rebate price.",
                    "type": "number",
                },
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "barrier", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/barrier_option_pricer",
        "summary": "Single-barrier option price (Reiner-Rubinstein closed form), with a",
        "tool_name": "barrier_option_pricer",
    },
    {
        "description": "Diversification means the basket option is worth no more than the "
        "weighted\n"
        "sum of single-asset options.",
        "domain": "derivatives",
        "function_name": "basket_option_pricer",
        "input_schema": {
            "properties": {
                "correlation": {
                    "description": "Asset correlation " "matrix (SPD).",
                    "type": "object",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute per-asset "
                    "delta/gamma/vega and "
                    "scalar theta/rho via "
                    "bump-and-reprice (see "
                    "``_multi_asset_bump_reprice_greeks``) "
                    "on the same pre-drawn "
                    "normals used for the "
                    "base price. Delta/ "
                    "gamma/vega are "
                    "diagonal only (each "
                    "asset bumped "
                    "independently; no "
                    "cross-asset terms). "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 71, "description": "RNG seed.", "type": "integer"},
                "sigmas": {"description": "Volatility per asset.", "type": "object"},
                "spots": {"description": "Initial prices per " "asset.", "type": "object"},
                "strike": {"description": "Strike on the weighted " "basket.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
                "weights": {"description": "Basket weights per " "asset.", "type": "object"},
            },
            "required": ["spots", "weights", "strike", "rate", "sigmas", "tau", "correlation"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/basket_option_pricer",
        "summary": "Basket option price via Monte Carlo on a weighted sum of assets.",
        "tool_name": "basket_option_pricer",
    },
    {
        "description": "Early exercise is allowed only on an evenly-spaced subset of the time "
        "grid.\n"
        "Price lies between the European and American values.\n"
        "\n"
        "Note: uses the same Longstaff-Schwartz regression-based exercise decision\n"
        "as ``american_option_lsm`` (no closed form), restricted to an\n"
        "evenly-spaced subset of roughly ``n_steps / exercise_dates`` grid points.",
        "domain": "derivatives",
        "function_name": "bermudan_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "exercise_dates": {
                    "default": 4,
                    "description": "Number of " "allowed " "exercise dates " "(>= 1).",
                    "type": "integer",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_bump_reprice_greeks``). "
                    "Same LSM "
                    "regression-boundary "
                    "caveat as "
                    "american_option_lsm "
                    "applies -- uses the "
                    "same larger spot bump "
                    "(``_LSM_GREEKS_BUMP_REL_SPOT``), "
                    "verified empirically "
                    "for this function too "
                    "(see "
                    "``_bump_reprice_greeks``'s "
                    "docstring). Defaults "
                    "to False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {
                    "default": 48,
                    "description": "Total time-grid steps "
                    "(multiple of "
                    "exercise_dates "
                    "ideally).",
                    "type": "integer",
                },
                "option_type": {
                    "default": "put",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 51, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bermudan_option_pricer",
        "summary": "Bermudan option price via LSM with discrete exercise dates.",
        "tool_name": "bermudan_option_pricer",
    },
    {
        "description": "Handles European and American exercise. European prices converge to\n"
        "Black-Scholes as ``n_steps`` grows.",
        "domain": "derivatives",
        "function_name": "binomial_tree_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "n_steps": {
                    "default": 500,
                    "description": "Number of binomial " "steps (>= 1).",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {
                    "description": "Continuously-compounded " "risk-free rate.",
                    "type": "number",
                },
                "sigma": {"description": "Volatility (annualised, " "> 0).", "type": "number"},
                "spot": {"description": "Underlying spot price.", "type": "number"},
                "strike": {"description": "Strike price.", "type": "number"},
                "style": {
                    "default": "european",
                    "description": '``"european"`` or ' '``"american"``.',
                    "type": "string",
                },
                "tau": {"description": "Time to maturity in years " "(> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/binomial_tree_option_pricer",
        "summary": "Cox-Ross-Rubinstein binomial tree option price.",
        "tool_name": "binomial_tree_option_pricer",
    },
    {
        "description": "``Call = S e^{-qτ} N(d1) − K e^{-rτ} N(d2)``; the put follows by parity.\n"
        "When ``tau == 0`` the intrinsic value is returned (zero-time limit) and "
        "when\n"
        "``sigma == 0`` the discounted-forward intrinsic value is returned.",
        "domain": "derivatives",
        "function_name": "black_scholes_european_option",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {
                    "description": "Continuously-compounded " "risk-free rate.",
                    "type": "number",
                },
                "sigma": {"description": "Volatility (annualised, " ">= 0).", "type": "number"},
                "spot": {"description": "Underlying spot price.", "type": "number"},
                "strike": {"description": "Strike price.", "type": "number"},
                "tau": {"description": "Time to maturity in years " "(>= 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/black_scholes_european_option",
        "summary": "Black-Scholes-Merton price of a European option.",
        "tool_name": "black_scholes_european_option",
    },
    {
        "description": "Returns delta, gamma, vega, theta (per year) and rho. Gamma and vega are\n"
        "identical for calls and puts.",
        "domain": "derivatives",
        "function_name": "black_scholes_greeks",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {
                    "description": "Continuously-compounded " "risk-free rate.",
                    "type": "number",
                },
                "sigma": {"description": "Volatility (annualised, " "> 0).", "type": "number"},
                "spot": {"description": "Underlying spot price.", "type": "number"},
                "strike": {"description": "Strike price.", "type": "number"},
                "tau": {"description": "Time to maturity in years " "(> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/black_scholes_greeks",
        "summary": "Closed-form Black-Scholes first-order Greeks.",
        "tool_name": "black_scholes_greeks",
    },
    {
        "description": "Price falls as yield rises (inverse relationship), and equals par when "
        "the\n"
        "coupon rate equals the yield.",
        "domain": "derivatives",
        "function_name": "bond_pricer_fixed_coupon",
        "input_schema": {
            "properties": {
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {"description": "Redemption (par) " "value.", "type": "number"},
                "frequency": {
                    "default": 2,
                    "description": "Coupon payments per " "year.",
                    "type": "integer",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "yield_rate": {
                    "description": "Annual yield to "
                    "maturity (decimal, "
                    "compounded "
                    "``frequency``).",
                    "type": "number",
                },
            },
            "required": ["face_value", "coupon_rate", "yield_rate", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bond_pricer_fixed_coupon",
        "summary": "Price a fixed-coupon bond by discounting its cashflows at a flat yield.",
        "tool_name": "bond_pricer_fixed_coupon",
    },
    {
        "description": "Each coupon is ``(reference_rate + spread) / frequency · face``. On a "
        "reset\n"
        "date with discount rates equal to the reference rates, an FRN prices near\n"
        "par plus the PV of the spread.\n"
        "\n"
        "The coupon schedule actually priced is derived from\n"
        "``len(reference_rates)`` (``discount_rates`` must match that length).\n"
        "``maturity`` must be consistent with ``len(reference_rates) / frequency``\n"
        "— a caller-supplied ``maturity`` that implies a different number of\n"
        "periods is rejected rather than silently ignored.",
        "domain": "derivatives",
        "function_name": "bond_pricer_floating_rate",
        "input_schema": {
            "properties": {
                "discount_rates": {
                    "description": "Per-period " "zero discount " "rate (decimal, " "annualised).",
                    "type": "object",
                },
                "face_value": {"description": "Redemption (par) " "value.", "type": "number"},
                "frequency": {
                    "default": 4,
                    "description": "Coupon payments per " "year.",
                    "type": "integer",
                },
                "maturity": {
                    "description": "Time to maturity in "
                    "years. Must equal "
                    "``len(reference_rates) "
                    "/ frequency`` (see "
                    "note above).",
                    "type": "number",
                },
                "reference_rates": {
                    "description": "Projected "
                    "forward index "
                    "rate per "
                    "period "
                    "(decimal). "
                    "Its length "
                    "sets the "
                    "number of "
                    "coupon "
                    "periods "
                    "priced.",
                    "type": "object",
                },
                "spread": {
                    "description": "Quoted margin over the " "index (decimal).",
                    "type": "number",
                },
            },
            "required": ["face_value", "reference_rates", "spread", "discount_rates", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bond_pricer_floating_rate",
        "summary": "Price a floating-rate note (FRN) from projected forward rates.",
        "tool_name": "bond_pricer_floating_rate",
    },
    {
        "description": "Sequentially solves for each discount factor so each par bond prices to "
        "par,\n"
        "then converts discount factors to continuously-compounded zero rates.",
        "domain": "derivatives",
        "function_name": "bootstrap_yield_curve",
        "input_schema": {
            "properties": {
                "face_value": {
                    "default": 1.0,
                    "description": "Par value " "(defaults to 1).",
                    "type": "number",
                },
                "frequency": {
                    "default": 1,
                    "description": "Coupon frequency " "per year.",
                    "type": "integer",
                },
                "maturities": {
                    "description": "Maturities in "
                    "years, ascending, "
                    "evenly spaced by "
                    "1/freq.",
                    "type": "object",
                },
                "par_rates": {
                    "description": "Par coupon rate per " "maturity (decimal).",
                    "type": "object",
                },
            },
            "required": ["par_rates", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/bootstrap_yield_curve",
        "summary": "Bootstrap zero (spot) rates from par-coupon bond rates.",
        "tool_name": "bootstrap_yield_curve",
    },
    {
        "description": "A callable bond is worth no more than the equivalent straight bond — the\n"
        "embedded call belongs to the issuer.\n"
        "\n"
        "Note: the short-rate tree is a simplified multiplicative lattice with\n"
        "fixed 0.5/0.5 branch probabilities, not a Black-Derman-Toy tree "
        "calibrated\n"
        "to an initial term structure, and the coupon is added at every node on\n"
        "every step.",
        "domain": "derivatives",
        "function_name": "callable_bond_pricer",
        "input_schema": {
            "properties": {
                "call_price": {
                    "description": "Price at which the " "issuer may call " "(per face).",
                    "type": "number",
                },
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {"description": "Par value.", "type": "number"},
                "frequency": {
                    "default": 1,
                    "description": "Coupon payments per " "year (tree steps " "per year).",
                    "type": "integer",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "rate_vol": {"description": "Short-rate " "volatility.", "type": "number"},
                "short_rate": {
                    "description": "Current short rate " "(continuous, " "annual).",
                    "type": "number",
                },
            },
            "required": [
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "call_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/callable_bond_pricer",
        "summary": "Price a callable bond (issuer's option) on a short-rate binomial tree.",
        "tool_name": "callable_bond_pricer",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "cap_floor_pricer",
        "input_schema": {
            "properties": {
                "accruals": {"description": "Year-fraction per " "period.", "type": "object"},
                "discount_factors": {
                    "description": "Discount " "factor per " "payment " "date.",
                    "type": "object",
                },
                "expiries": {"description": "Fixing time per " "caplet (years).", "type": "object"},
                "forward_rates": {
                    "description": "Forward rate " "per caplet " "period.",
                    "type": "object",
                },
                "notional": {"description": "Notional.", "type": "number"},
                "option_type": {
                    "default": "cap",
                    "description": '``"cap"`` or ' '``"floor"``.',
                    "type": "string",
                },
                "strike": {"description": "Common strike " "(decimal).", "type": "number"},
                "vols": {"description": "Black vol per caplet.", "type": "object"},
            },
            "required": [
                "notional",
                "forward_rates",
                "strike",
                "vols",
                "expiries",
                "accruals",
                "discount_factors",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cap_floor_pricer",
        "summary": "Price an interest-rate cap/floor as a strip of caplets/floorlets.",
        "tool_name": "cap_floor_pricer",
    },
    {
        "description": "A caplet is a call on the forward rate; a floorlet is a put. Caplet +\n"
        "floorlet (same strike) replicate a payer FRA (put-call parity).",
        "domain": "derivatives",
        "function_name": "caplet_floorlet_pricer_black",
        "input_schema": {
            "properties": {
                "accrual": {
                    "description": "Year-fraction of the " "accrual period.",
                    "type": "number",
                },
                "discount_factor": {
                    "description": "Discount " "factor to " "payment.",
                    "type": "number",
                },
                "expiry": {"description": "Time to caplet fixing " "(years).", "type": "number"},
                "forward_rate": {
                    "description": "Forward " "LIBOR/index rate " "(decimal).",
                    "type": "number",
                },
                "notional": {"description": "Notional.", "type": "number"},
                "option_type": {
                    "default": "caplet",
                    "description": '``"caplet"`` or ' '``"floorlet"``.',
                    "type": "string",
                },
                "strike": {"description": "Cap/floor strike " "(decimal).", "type": "number"},
                "vol": {
                    "description": "Black volatility of the " "forward rate.",
                    "type": "number",
                },
            },
            "required": [
                "notional",
                "forward_rate",
                "strike",
                "vol",
                "expiry",
                "accrual",
                "discount_factor",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/caplet_floorlet_pricer_black",
        "summary": "Price a single caplet/floorlet under the Black (lognormal) model.",
        "tool_name": "caplet_floorlet_pricer_black",
    },
    {
        "description": "At ``tau_choose`` the holder picks call or put (same strike/expiry). By\n"
        "put-call parity the value is a call plus a put on a reduced-maturity\n"
        "underlying: ``C(S,K,T) + P(S, K e^{-r(T-t)}·..., t)``. Worth at least the\n"
        "more valuable of the embedded call and put.",
        "domain": "derivatives",
        "function_name": "chooser_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Common strike.", "type": "number"},
                "tau_choose": {"description": "Time to the choice " "date.", "type": "number"},
                "tau_expiry": {
                    "description": "Time to expiry (> " "tau_choose).",
                    "type": "number",
                },
            },
            "required": ["spot", "strike", "rate", "sigma", "tau_choose", "tau_expiry"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/chooser_option_pricer",
        "summary": "Simple chooser option price (closed form).",
        "tool_name": "chooser_option_pricer",
    },
    {
        "description": "Supports the four standard compound types (call/put on call/put). See\n"
        "``_geske_compound_price`` for the exact d-term algebra and its citation.",
        "domain": "derivatives",
        "function_name": "compound_option_pricer",
        "input_schema": {
            "properties": {
                "compound_type": {
                    "default": "call-on-call",
                    "description": "``call-on-call``, "
                    "``call-on-put``, "
                    "``put-on-call``, "
                    "``put-on-put``.",
                    "type": "string",
                },
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "on the exact "
                    "closed-form price "
                    "(deterministic -- no "
                    "Monte Carlo noise to "
                    "correlate away). theta "
                    "bumps ``tau_compound`` "
                    "(the compound leg's "
                    "own time to expiry) "
                    "while holding "
                    "``tau_underlying`` "
                    "fixed -- i.e. both the "
                    "compound's remaining "
                    "life and the "
                    "underlying option's "
                    "residual tenor from "
                    "that later date shrink "
                    "together, the usual "
                    '"time passing today" '
                    "interpretation. "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 200000,
                    "description": "Unused by the "
                    "closed-form "
                    "price; retained "
                    "for "
                    "backward-compatible "
                    "call signatures "
                    "(was the MC "
                    "path count "
                    "before this "
                    "function "
                    "switched from "
                    "Monte Carlo to "
                    "the exact Geske "
                    "formula -- see "
                    "``_compound_option_pricer_mc`` "
                    "for that "
                    "retained "
                    "reference "
                    "implementation).",
                    "type": "integer",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {
                    "default": 81,
                    "description": "Unused by the "
                    "closed-form price; "
                    "retained for the same "
                    "reason as "
                    "``n_simulations``.",
                    "type": "integer",
                },
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike_compound": {
                    "description": "Strike of the " "compound " "option " "(premium " "paid).",
                    "type": "number",
                },
                "strike_underlying": {
                    "description": "Strike of " "the " "underlying " "option.",
                    "type": "number",
                },
                "tau_compound": {
                    "description": "Time to the " "compound option " "expiry.",
                    "type": "number",
                },
                "tau_underlying": {
                    "description": "Time to the "
                    "underlying "
                    "option expiry "
                    "(> "
                    "tau_compound).",
                    "type": "number",
                },
            },
            "required": [
                "spot",
                "strike_underlying",
                "strike_compound",
                "rate",
                "sigma",
                "tau_compound",
                "tau_underlying",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/compound_option_pricer",
        "summary": "Compound option (option-on-option) price via the Geske (1979) closed form.",
        "tool_name": "compound_option_pricer",
    },
    {
        "description": "Value = max(straight bond floor, conversion value), a simple but standard\n"
        "lower-bound decomposition. The convertible is always worth at least its\n"
        "conversion value and at least its bond floor.\n"
        "\n"
        "Note: this lower-bound decomposition does not model conversion\n"
        "optionality, equity volatility, or embedded call/put features of a real\n"
        "convertible bond.",
        "domain": "derivatives",
        "function_name": "convertible_bond_pricer",
        "input_schema": {
            "properties": {
                "conversion_ratio": {
                    "description": "Shares " "received per " "bond on " "conversion.",
                    "type": "number",
                },
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {"description": "Par value.", "type": "number"},
                "frequency": {
                    "default": 2,
                    "description": "Coupon payments per " "year.",
                    "type": "integer",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "stock_price": {"description": "Current share " "price.", "type": "number"},
                "yield_rate": {
                    "description": "Straight-bond " "discount yield " "(decimal).",
                    "type": "number",
                },
            },
            "required": [
                "face_value",
                "coupon_rate",
                "yield_rate",
                "maturity",
                "conversion_ratio",
                "stock_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/convertible_bond_pricer",
        "summary": "Price a convertible bond via the bond-floor + conversion-value maximum.",
        "tool_name": "convertible_bond_pricer",
    },
    {
        "description": "option-free bonds).\n"
        "\n"
        "``C = Σ cf_k · t_k(t_k + 1/m) · (1+y/m)^{-(m t_k + 2)} / P``.",
        "domain": "derivatives",
        "function_name": "convexity",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
                "yield_rate": {"description": "Annual yield " "(decimal).", "type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/convexity",
        "summary": "Bond convexity — the second-order yield sensitivity (always >= 0 for",
        "tool_name": "convexity",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ√r dW``. The square-root diffusion keeps ``r >= 0``. "
        "The\n"
        "Feller condition ``2κθ ≥ σ²`` guarantees strict positivity.\n"
        "\n"
        "The Monte Carlo path uses the exact non-central chi-squared CIR\n"
        "transition distribution (Broadie-Kaya / Glasserman §3.4;\n"
        "``_cir_paths_exact_terminal``), not an Euler discretisation -- there is\n"
        "no discretisation bias here at any ``n_steps``, unlike the (retained,\n"
        "non-production) full-truncation Euler scheme in ``_cir_paths_euler``.",
        "domain": "derivatives",
        "function_name": "cox_ingersoll_ross_model",
        "input_schema": {
            "properties": {
                "kappa": {"description": "Mean-reversion speed (> " "0).", "type": "number"},
                "maturity": {"description": "Bond maturity in " "years (> 0).", "type": "number"},
                "n_simulations": {"default": 50000, "description": "MC paths.", "type": "integer"},
                "n_steps": {
                    "default": 100,
                    "description": "MC time steps (exact "
                    "scheme -- affects "
                    "only path "
                    "granularity, not "
                    "terminal-distribution "
                    "accuracy).",
                    "type": "integer",
                },
                "r0": {"description": "Initial short rate (>= 0).", "type": "number"},
                "seed": {"default": 102, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "theta": {"description": "Long-run mean (> 0).", "type": "number"},
            },
            "required": ["r0", "kappa", "theta", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cox_ingersoll_ross_model",
        "summary": "CIR model: closed-form ZCB price + simulated (non-negative) short rate.",
        "tool_name": "cox_ingersoll_ross_model",
    },
    {
        "description": "accrual-midpoint default settlement.\n"
        "\n"
        "Survival ``Q(t)=e^{−λt}``. Default losses -- and the accrued premium a\n"
        "protection buyer owes if default falls inside a coupon period -- are\n"
        "both settled at each period's ACCRUAL MIDPOINT\n"
        "``t_mid,i = (t_{i−1}+t_i)/2``, discounted at ``DF(t_mid,i)``, following\n"
        "the standard ISDA/JPMorgan reduced-form CDS convention also implemented\n"
        "by QuantLib's ``MidPointCdsEngine`` (which settles the same way by\n"
        "default: ``settlesAccrual=True``, ``paysAtDefaultTime=True`` --\n"
        "confirmed by inspecting its NPV decomposition directly, since this is\n"
        "exactly what ``tests/validation/test_derivatives_ref.py`` cross-checks\n"
        "against). The regular coupon cashflow -- paid only while the name has\n"
        "survived to the period end -- is unaffected: ``spread · τ · Σ DF(t_i) ·\n"
        "Q(t_i)``.\n"
        "\n"
        "Protection leg = ``(1−R) · Σ DF(t_mid,i) · (Q_{i−1} − Q_i)``.\n"
        "Accrual-on-default rebate = ``spread · Σ (t_mid,i − t_{i−1}) ·\n"
        "DF(t_mid,i) · (Q_{i−1} − Q_i)``, added to the premium leg. The par\n"
        "spread zeroes the swap value.",
        "domain": "derivatives",
        "function_name": "credit_default_swap_cds_pricer",
        "input_schema": {
            "properties": {
                "discount_rate": {
                    "description": "Flat continuous " "discount rate.",
                    "type": "number",
                },
                "frequency": {
                    "default": 4,
                    "description": "Premium payment " "frequency per year.",
                    "type": "integer",
                },
                "hazard_rate": {
                    "description": "Constant hazard " "rate λ (decimal).",
                    "type": "number",
                },
                "maturity": {"description": "CDS maturity in " "years.", "type": "number"},
                "notional": {"description": "CDS notional.", "type": "number"},
                "recovery_rate": {"description": "Recovery rate R " "in [0, 1).", "type": "number"},
                "spread": {
                    "description": "Contractual spread " "(decimal, annual).",
                    "type": "number",
                },
            },
            "required": [
                "notional",
                "spread",
                "hazard_rate",
                "recovery_rate",
                "maturity",
                "discount_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/credit_default_swap_cds_pricer",
        "summary": "Price a CDS via a flat-hazard-rate reduced-form model with",
        "tool_name": "credit_default_swap_cds_pricer",
    },
    {
        "description": "Values each leg in its own currency (coupons + final notional), converts "
        "the\n"
        "foreign leg at the FX spot, and nets. Pay-domestic = pay the domestic "
        "leg,\n"
        "receive the foreign leg.",
        "domain": "derivatives",
        "function_name": "cross_currency_swap_pricer",
        "input_schema": {
            "properties": {
                "accruals": {
                    "description": "Year-fraction per " "period (shared " "schedule).",
                    "type": "object",
                },
                "df_dom": {
                    "description": "Domestic discount " "factors per payment " "date.",
                    "type": "object",
                },
                "df_for": {
                    "description": "Foreign discount " "factors per payment " "date.",
                    "type": "object",
                },
                "fixed_rate_dom": {
                    "description": "Domestic fixed " "rate " "(decimal).",
                    "type": "number",
                },
                "fixed_rate_for": {
                    "description": "Foreign fixed " "rate " "(decimal).",
                    "type": "number",
                },
                "fx_spot": {
                    "description": "Spot FX (domestic per " "1 unit foreign).",
                    "type": "number",
                },
                "notional_dom": {"description": "Domestic " "notional.", "type": "number"},
                "notional_for": {"description": "Foreign " "notional.", "type": "number"},
                "pay_domestic": {
                    "default": True,
                    "description": "Direction flag.",
                    "type": "boolean",
                },
            },
            "required": [
                "notional_dom",
                "notional_for",
                "fixed_rate_dom",
                "fixed_rate_for",
                "df_dom",
                "df_for",
                "accruals",
                "fx_spot",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/cross_currency_swap_pricer",
        "summary": "Price a fixed-fixed cross-currency swap (with notional exchange).",
        "tool_name": "cross_currency_swap_pricer",
    },
    {
        "description": "``Call = payout · e^{-rτ} N(d2)``, ``Put = payout · e^{-rτ} N(-d2)``.",
        "domain": "derivatives",
        "function_name": "digital_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "payout": {
                    "default": 1.0,
                    "description": "Cash payout if in the " "money.",
                    "type": "number",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/digital_option_pricer",
        "summary": "Cash-or-nothing digital (binary) option price.",
        "tool_name": "digital_option_pricer",
    },
    {
        "description": "Prices ``(S + a)`` as a lognormal with vol scaled by ``S/(S+a)`` — a "
        "simple\n"
        "way to interpolate between lognormal (a=0) and normal-like dynamics. "
        "Reduces\n"
        "exactly to Black-Scholes when ``displacement == 0``.",
        "domain": "derivatives",
        "function_name": "displaced_diffusion_model",
        "input_schema": {
            "properties": {
                "displacement": {
                    "description": "Shift ``a`` " "applied to spot " "and strike.",
                    "type": "number",
                },
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "sigma": {
                    "description": "Lognormal volatility of " "the displaced process.",
                    "type": "number",
                },
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau", "displacement"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/displaced_diffusion_model",
        "summary": "Displaced-diffusion (shifted lognormal) European option price.",
        "tool_name": "displaced_diffusion_model",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "duration_macaulay",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
                "yield_rate": {"description": "Annual yield " "(decimal).", "type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/duration_macaulay",
        "summary": "Macaulay duration — PV-weighted average time to cashflows (in years).",
        "tool_name": "duration_macaulay",
    },
    {
        "description": "Computed by central difference of the price function at ±0.5bp.",
        "domain": "derivatives",
        "function_name": "dv01_pvbp",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
                "yield_rate": {"description": "Annual yield " "(decimal).", "type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/dv01_pvbp",
        "summary": "DV01 / PVBP — price change for a 1 basis-point yield move.",
        "tool_name": "dv01_pvbp",
    },
    {
        "description": "``D_eff = (P− − P+) / (2 · P0 · Δy)`` — model-agnostic, so it captures\n"
        "embedded optionality (callable/puttable) that analytic duration misses.",
        "domain": "derivatives",
        "function_name": "effective_duration",
        "input_schema": {
            "properties": {
                "price_base": {"description": "Price at the base " "yield.", "type": "number"},
                "price_down": {"description": "Price after " "−``yield_shock``.", "type": "number"},
                "price_up": {"description": "Price after " "+``yield_shock``.", "type": "number"},
                "yield_shock": {
                    "description": "Size of the " "parallel yield " "shock (decimal).",
                    "type": "number",
                },
            },
            "required": ["price_base", "price_up", "price_down", "yield_shock"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/effective_duration",
        "summary": "Effective duration from re-priced bond values under a parallel shock.",
        "tool_name": "effective_duration",
    },
    {
        "description": "``notional · (equity_return − funding·τ) · DF`` to the equity receiver.",
        "domain": "derivatives",
        "function_name": "equity_swap_pricer",
        "input_schema": {
            "properties": {
                "accrual": {"description": "Year-fraction.", "type": "number"},
                "discount_factor": {
                    "description": "Discount " "factor to " "payment.",
                    "type": "number",
                },
                "equity_return": {
                    "description": "Period equity " "total return " "(decimal).",
                    "type": "number",
                },
                "funding_rate": {
                    "description": "Funding rate " "(decimal, " "annual).",
                    "type": "number",
                },
                "notional": {"description": "Reference notional.", "type": "number"},
                "receive_equity": {
                    "default": True,
                    "description": "Direction " "flag.",
                    "type": "boolean",
                },
            },
            "required": ["notional", "equity_return", "funding_rate", "accrual", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/equity_swap_pricer",
        "summary": "Value an equity swap leg (equity return vs funding).",
        "tool_name": "equity_swap_pricer",
    },
    {
        "description": "``Value = notional · (forward − fra_rate) · accrual · DF(end)``. Zero "
        "value\n"
        "when the contracted FRA rate equals the projected forward.",
        "domain": "derivatives",
        "function_name": "forward_rate_agreement_fra",
        "input_schema": {
            "properties": {
                "discount_factor": {
                    "description": "Discount " "factor to the " "settlement " "(end) date.",
                    "type": "number",
                },
                "end": {"description": "Accrual end in years (> " "start).", "type": "number"},
                "forward_rate": {
                    "description": "Projected " "forward rate " "over [start, " "end] (decimal).",
                    "type": "number",
                },
                "fra_rate": {
                    "description": "Contracted (fixed) " "FRA rate (decimal).",
                    "type": "number",
                },
                "notional": {"description": "Contract notional.", "type": "number"},
                "start": {"description": "Accrual start in years.", "type": "number"},
            },
            "required": ["notional", "fra_rate", "forward_rate", "start", "end", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/forward_rate_agreement_fra",
        "summary": "Mark-to-market value of a forward rate agreement (long = pay fixed).",
        "tool_name": "forward_rate_agreement_fra",
    },
    {
        "description": "``F = S · e^{(r_dom − r_for)·τ}``. If a contracted forward is supplied, "
        "the\n"
        "MtM value (domestic ccy) of a long-foreign position is\n"
        "``notional · (F − contracted) · e^{−r_dom·τ}``.",
        "domain": "derivatives",
        "function_name": "fx_forward_pricer",
        "input_schema": {
            "properties": {
                "contracted_forward": {
                    "description": "Optional " "contracted " "forward " "rate for " "MtM.",
                    "type": "object",
                },
                "notional": {
                    "default": 1.0,
                    "description": "Foreign-currency " "notional.",
                    "type": "number",
                },
                "rate_domestic": {
                    "description": "Domestic " "continuous " "rate.",
                    "type": "number",
                },
                "rate_foreign": {"description": "Foreign " "continuous rate.", "type": "number"},
                "spot": {"description": "Spot FX (domestic per 1 " "foreign).", "type": "number"},
                "tau": {"description": "Time to delivery (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "rate_domestic", "rate_foreign", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/fx_forward_pricer",
        "summary": "FX forward rate and mark-to-market via covered interest-rate parity.",
        "tool_name": "fx_forward_pricer",
    },
    {
        "description": "Black-Scholes with the foreign rate acting as a continuous dividend "
        "yield:\n"
        "``Call = S e^{−r_for τ} N(d1) − K e^{−r_dom τ} N(d2)``. Satisfies FX\n"
        "put-call parity ``C − P = S e^{−r_for τ} − K e^{−r_dom τ}``.",
        "domain": "derivatives",
        "function_name": "fx_option_pricer_garman_kohlhagen",
        "input_schema": {
            "properties": {
                "notional": {
                    "default": 1.0,
                    "description": "Foreign-currency " "notional.",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate_domestic": {
                    "description": "Domestic " "continuous " "rate.",
                    "type": "number",
                },
                "rate_foreign": {"description": "Foreign " "continuous rate.", "type": "number"},
                "sigma": {"description": "FX volatility (> 0).", "type": "number"},
                "spot": {"description": "Spot FX (domestic per 1 " "foreign).", "type": "number"},
                "strike": {"description": "Strike FX.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate_domestic", "rate_foreign", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/fx_option_pricer_garman_kohlhagen",
        "summary": "Garman-Kohlhagen FX option price.",
        "tool_name": "fx_option_pricer_garman_kohlhagen",
    },
    {
        "description": "Prices via the single-integral representation using the characteristic\n"
        "function. As ``sigma`` (vol-of-vol) → 0 with ``v0 = theta`` the price "
        "tends\n"
        "to Black-Scholes with constant vol ``sqrt(theta)``.",
        "domain": "derivatives",
        "function_name": "heston_stochastic_volatility_model",
        "input_schema": {
            "properties": {
                "kappa": {"description": "Mean-reversion speed of " "variance.", "type": "number"},
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "rho": {
                    "description": "Spot/variance correlation " "in [-1, 1].",
                    "type": "number",
                },
                "sigma": {
                    "description": "Volatility of variance " "(vol-of-vol).",
                    "type": "number",
                },
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
                "theta": {"description": "Long-run variance.", "type": "number"},
                "v0": {"description": "Initial variance.", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau", "v0", "kappa", "theta", "sigma", "rho"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/heston_stochastic_volatility_model",
        "summary": "Heston stochastic-volatility European option price (semi-analytic).",
        "tool_name": "heston_stochastic_volatility_model",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ dW`` — the extended-Vasicek form; with a constant θ "
        "the\n"
        "closed-form ZCB price coincides with Vasicek. Returns the analytic bond\n"
        "price and a Monte Carlo cross-check.\n"
        "\n"
        "Note: with ``theta_const`` held constant this function literally "
        "delegates\n"
        "to ``vasicek_interest_rate_model`` — it is not a genuine time-dependent\n"
        "Hull-White model calibrated to fit an observed market forward curve.",
        "domain": "derivatives",
        "function_name": "hull_white_short_rate_model",
        "input_schema": {
            "properties": {
                "kappa": {"description": "Mean-reversion speed (> " "0).", "type": "number"},
                "maturity": {"description": "Bond maturity " "(years, > 0).", "type": "number"},
                "n_simulations": {"default": 50000, "description": "MC paths.", "type": "integer"},
                "n_steps": {"default": 100, "description": "MC time steps.", "type": "integer"},
                "r0": {"description": "Initial short rate.", "type": "number"},
                "seed": {"default": 103, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "theta_const": {
                    "default": 0.03,
                    "description": "Constant " "mean-reversion " "level.",
                    "type": "number",
                },
            },
            "required": ["r0", "kappa", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/hull_white_short_rate_model",
        "summary": "Hull-White one-factor model with a constant mean-reversion level.",
        "tool_name": "hull_white_short_rate_model",
    },
    {
        "description": "Coupons and principal accrete with cumulative inflation; the resulting\n"
        "nominal cashflows are discounted at the real yield (the standard\n"
        "real-cashflow / real-yield convention).",
        "domain": "derivatives",
        "function_name": "inflation_linked_bond_pricer",
        "input_schema": {
            "properties": {
                "face_value": {"description": "Base (un-indexed) " "par value.", "type": "number"},
                "frequency": {
                    "default": 2,
                    "description": "Coupon payments per " "year.",
                    "type": "integer",
                },
                "inflation_rate": {
                    "description": "Assumed annual " "inflation " "(decimal).",
                    "type": "number",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "real_coupon_rate": {
                    "description": "Annual real " "coupon rate " "(decimal).",
                    "type": "number",
                },
                "real_yield": {"description": "Annual real yield " "(decimal).", "type": "number"},
            },
            "required": [
                "face_value",
                "real_coupon_rate",
                "real_yield",
                "maturity",
                "inflation_rate",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/inflation_linked_bond_pricer",
        "summary": "Price an inflation-linked (real) bond with index-uplifted principal.",
        "tool_name": "inflation_linked_bond_pricer",
    },
    {
        "description": "Float leg PV = ``notional · Σ fwd_i · τ_i · DF_i``; fixed leg PV =\n"
        "``notional · fixed · Σ τ_i · DF_i``. Swap value to the payer is\n"
        "``float − fixed``. The par (break-even) fixed rate is also returned.",
        "domain": "derivatives",
        "function_name": "interest_rate_swap_irs_pricer",
        "input_schema": {
            "properties": {
                "accruals": {"description": "Year-fraction per " "period.", "type": "object"},
                "discount_factors": {
                    "description": "Discount " "factor per " "payment " "date.",
                    "type": "object",
                },
                "fixed_rate": {"description": "Fixed-leg rate " "(decimal).", "type": "number"},
                "forward_rates": {
                    "description": "Projected float " "index rate per " "period " "(decimal).",
                    "type": "object",
                },
                "notional": {"description": "Swap notional.", "type": "number"},
                "pay_fixed": {
                    "default": True,
                    "description": "True for payer swap " "(long float), False " "for receiver.",
                    "type": "boolean",
                },
            },
            "required": ["notional", "fixed_rate", "forward_rates", "discount_factors", "accruals"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/interest_rate_swap_irs_pricer",
        "summary": "Price a vanilla fixed-vs-float interest-rate swap.",
        "tool_name": "interest_rate_swap_irs_pricer",
    },
    {
        "description": "Evolves a vector of forward LIBOR rates under the spot measure with the\n"
        "standard log-normal BGM drift, discretised via the Glasserman-Zhao\n"
        "predictor-corrector Euler scheme (see\n"
        "``_lmm_terminal_rates_predictor_corrector``). Returns the mean terminal\n"
        "forward curve; rates stay positive (log-normal dynamics).\n"
        "\n"
        "The drift for rate ``i`` sums over ``j = 0..i`` inclusive (including rate\n"
        "``i`` itself), evaluated from a single consistent rate vector at each of\n"
        "the predictor and corrector stages -- not a sequential same-step\n"
        "overwrite (see ``_lmm_terminal_rates_sequential_euler`` for the retained,\n"
        "non-production former scheme).",
        "domain": "derivatives",
        "function_name": "lmm_bgm_rate_model",
        "input_schema": {
            "properties": {
                "forward_rates": {
                    "description": "Initial forward " "rates per tenor " "(decimal, > 0).",
                    "type": "object",
                },
                "horizon": {"description": "Simulation horizon " "(years, > 0).", "type": "number"},
                "n_simulations": {
                    "default": 20000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {
                    "default": 20,
                    "description": "Time steps to the " "horizon.",
                    "type": "integer",
                },
                "seed": {"default": 104, "description": "RNG seed.", "type": "integer"},
                "tenor": {
                    "description": "Accrual length of each " "forward (years).",
                    "type": "number",
                },
                "vols": {"description": "Lognormal vol per " "forward rate.", "type": "object"},
            },
            "required": ["forward_rates", "vols", "tenor", "horizon"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/lmm_bgm_rate_model",
        "summary": "LIBOR Market Model (BGM) forward-rate Monte Carlo simulation.",
        "tool_name": "lmm_bgm_rate_model",
    },
    {
        "description": "Uses finite differences of the Dupire equation\n"
        "``σ_loc² = (∂C/∂T + r K ∂C/∂K) / (½ K² ∂²C/∂K²)`` on the supplied grid,\n"
        "covering the FULL grid: central differences in strike at interior\n"
        "points, one-sided (forward/backward) 2nd-order-accurate differences at\n"
        "the two strike boundaries (exact non-uniform-grid Fornberg-style 3-point\n"
        "stencils -- exact for any quadratic, verified against hand-differentiated\n"
        "polynomials), and a forward/backward difference in maturity at the\n"
        "first/last maturity respectively (interior maturities also use the\n"
        "forward difference toward the next maturity).",
        "domain": "derivatives",
        "function_name": "local_volatility_dupire_model",
        "input_schema": {
            "properties": {
                "call_surface": {
                    "description": "``(len(maturities), " "len(strikes))`` " "call prices.",
                    "type": "object",
                },
                "maturities": {
                    "description": "1-D ascending " "maturity grid " "(years).",
                    "type": "object",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "spot": {
                    "description": "Underlying spot "
                    "(validation only; not "
                    "used in the formula).",
                    "type": "number",
                },
                "strikes": {"description": "1-D ascending strike " "grid.", "type": "object"},
            },
            "required": ["strikes", "maturities", "call_surface", "rate", "spot"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/local_volatility_dupire_model",
        "summary": "Dupire local volatility surface from a call-price surface.",
        "tool_name": "local_volatility_dupire_model",
    },
    {
        "description": "Floating-strike: call pays ``S_T − min`` (>= 0), put pays ``max − S_T``.\n"
        "Fixed-strike: call pays ``max − K``, put pays ``K − min``. Always >= the\n"
        "corresponding vanilla payoff.",
        "domain": "derivatives",
        "function_name": "lookback_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_bump_reprice_greeks``) "
                    "on the same pre-drawn "
                    "normals used for the "
                    "base price. The "
                    "path-average/extremum "
                    "payoff here is smooth "
                    "in spot (unlike the "
                    "LSM products below), "
                    "so this uses the same "
                    "small bump sizes as "
                    "asian_option_pricer. "
                    "Not supported together "
                    "with qmc=True. "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {
                    "default": 100,
                    "description": "Monitoring frequency.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "qmc": {
                    "default": False,
                    "description": "Use randomized "
                    "quasi-Monte Carlo "
                    "(scrambled Sobol "
                    "replicates, see "
                    "``_price_by_qmc_replicates``) "
                    "instead of plain MC for a "
                    "lower-variance estimate "
                    "at the same "
                    "n_simulations. Defaults "
                    "to False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 31, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike (fixed-strike " "only).", "type": "number"},
                "strike_type": {
                    "default": "floating",
                    "description": '``"floating"`` or ' '``"fixed"``.',
                    "type": "string",
                },
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/lookback_option_pricer",
        "summary": "Lookback option price via Monte Carlo.",
        "tool_name": "lookback_option_pricer",
    },
    {
        "description": "Approximates the percentage price change for a 1-unit yield move:\n"
        "``ΔP/P ≈ −D_mod · Δy``.",
        "domain": "derivatives",
        "function_name": "modified_duration",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
                "yield_rate": {"description": "Annual yield " "(decimal).", "type": "number"},
            },
            "required": ["cashflows", "times", "yield_rate"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/modified_duration",
        "summary": "Modified duration = Macaulay duration / (1 + y/m).",
        "tool_name": "modified_duration",
    },
    {
        "description": "Randoms are pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3); the JIT "
        "kernel\n"
        "only consumes the pre-drawn standard-normal array.",
        "domain": "derivatives",
        "function_name": "monte_carlo_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of Monte " "Carlo paths.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {
                    "description": "Continuously-compounded " "risk-free rate.",
                    "type": "number",
                },
                "seed": {
                    "default": 12345,
                    "description": "RNG seed for " "determinism.",
                    "type": "integer",
                },
                "sigma": {"description": "Volatility (annualised, " "> 0).", "type": "number"},
                "spot": {"description": "Underlying spot price.", "type": "number"},
                "strike": {"description": "Strike price.", "type": "number"},
                "tau": {"description": "Time to maturity in years " "(> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/monte_carlo_option_pricer",
        "summary": "Monte Carlo price of a European option (terminal GBM payoff).",
        "tool_name": "monte_carlo_option_pricer",
    },
    {
        "description": "Parameters: ``beta0`` (level), ``beta1`` (slope), ``beta2`` (curvature),\n"
        "``tau`` (decay). ``beta0 + beta1`` is the instantaneous short rate and\n"
        "``beta0`` is the asymptotic long rate.",
        "domain": "derivatives",
        "function_name": "nelson_siegel_curve_fit",
        "input_schema": {
            "properties": {
                "maturities": {
                    "description": "Observed " "maturities in " "years (> 0).",
                    "type": "object",
                },
                "tau_init": {
                    "default": 1.5,
                    "description": "Initial guess for " "the decay parameter.",
                    "type": "number",
                },
                "yields": {
                    "description": "Observed yields " "(decimal) at those " "maturities.",
                    "type": "object",
                },
            },
            "required": ["maturities", "yields"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/nelson_siegel_curve_fit",
        "summary": "Fit a Nelson-Siegel curve to observed yields.",
        "tool_name": "nelson_siegel_curve_fit",
    },
    {
        "description": "Adds a second curvature hump (``beta3``, ``tau2``) to Nelson-Siegel, "
        "giving\n"
        "a closer fit to longer/more complex term structures.",
        "domain": "derivatives",
        "function_name": "nelson_siegel_svensson_curve",
        "input_schema": {
            "properties": {
                "maturities": {
                    "description": "Observed " "maturities in " "years (> 0).",
                    "type": "object",
                },
                "tau1_init": {
                    "default": 1.5,
                    "description": "Initial first decay " "parameter.",
                    "type": "number",
                },
                "tau2_init": {
                    "default": 8.0,
                    "description": "Initial second " "decay parameter.",
                    "type": "number",
                },
                "yields": {"description": "Observed yields " "(decimal).", "type": "object"},
            },
            "required": ["maturities", "yields"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/nelson_siegel_svensson_curve",
        "summary": "Fit the Nelson-Siegel-Svensson (six-parameter) curve.",
        "tool_name": "nelson_siegel_svensson_curve",
    },
    {
        "description": "NIG is Brownian motion subordinated by an inverse-Gaussian process. The\n"
        "drift is corrected so the discounted spot is a martingale.",
        "domain": "derivatives",
        "function_name": "normal_inverse_gaussian_model",
        "input_schema": {
            "properties": {
                "alpha": {
                    "default": 15.0,
                    "description": "Tail heaviness (> " "|beta|).",
                    "type": "number",
                },
                "beta": {"default": -5.0, "description": "Skewness parameter.", "type": "number"},
                "delta": {
                    "default": 0.5,
                    "description": "Scale (> 0). NOT the "
                    "Greek delta (spot "
                    "sensitivity) -- an "
                    "unfortunate name "
                    "collision with this "
                    "model's own parameter; "
                    "see ``greeks`` below.",
                    "type": "number",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "Greek-delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_levy_bump_reprice_greeks``). "
                    '"vega" here is '
                    "sensitivity to this "
                    "function's ``delta`` "
                    "PARAMETER (the IG "
                    "subordinator's scale, "
                    "this model's closest "
                    "analogue to a "
                    "volatility level) -- "
                    "not to ``alpha`` or "
                    "``beta``, which are "
                    "held fixed. The output "
                    'dict\'s ``"delta"`` '
                    "key is the Greek (spot "
                    "sensitivity); it is "
                    "unrelated to the "
                    "``delta`` parameter "
                    "above despite the "
                    "shared name. "
                    "Greek-delta/rho reuse "
                    "the base run's IG "
                    "subordinator directly "
                    "(spot/rate bumps don't "
                    'touch it). Both "vega" '
                    "(bumping the ``delta`` "
                    "parameter) and the "
                    'Greek "theta" (bumping '
                    "tau) DO change the "
                    "subordinator's (mu, "
                    "lambda), so each draws "
                    "its own shared "
                    "``(normal, uniform)`` "
                    "pair once and maps it "
                    "through the IG "
                    "inverse-transform "
                    "(``_ig_from_randoms``) "
                    "at the +/- bumped (mu, "
                    "lambda) -- the same "
                    "common-random-numbers "
                    "technique "
                    "variance_gamma_model "
                    "uses for its own "
                    "tau-dependent Gamma "
                    "subordinator, verified "
                    "there to cut "
                    "seed-to-seed noise by "
                    "~65x vs. an "
                    "independent redraw at "
                    "each bumped value. "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 11, "description": "RNG seed.", "type": "integer"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/normal_inverse_gaussian_model",
        "summary": "Normal Inverse Gaussian European option price via Monte Carlo.",
        "tool_name": "normal_inverse_gaussian_model",
    },
    {
        "description": "Finds the constant spread added to the short rate on the pricing tree "
        "that\n"
        "reprices the callable bond to its market price — stripping out the "
        "embedded\n"
        "option so spreads are comparable across bonds.\n"
        "\n"
        "Note: the spread is root-found (Brent's method) against\n"
        "``callable_bond_pricer``'s tree price rather than expressed in closed\n"
        "form — the equation above is the condition the solver satisfies, not an\n"
        "explicit OAS formula.",
        "domain": "derivatives",
        "function_name": "oas_option_adjusted_spread",
        "input_schema": {
            "properties": {
                "call_price": {
                    "description": "Issuer call strike " "(per face).",
                    "type": "number",
                },
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {"description": "Par value.", "type": "number"},
                "frequency": {
                    "default": 1,
                    "description": "Coupon payments / " "tree steps per " "year.",
                    "type": "integer",
                },
                "market_price": {
                    "description": "Observed market " "price of the " "callable bond.",
                    "type": "number",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "rate_vol": {"description": "Short-rate " "volatility.", "type": "number"},
                "short_rate": {
                    "description": "Current short rate " "(continuous, " "annual).",
                    "type": "number",
                },
            },
            "required": [
                "market_price",
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "call_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/oas_option_adjusted_spread",
        "summary": "Option-adjusted spread of a callable bond.",
        "tool_name": "oas_option_adjusted_spread",
    },
    {
        "description": "OIS swaps pay annually against compounded overnight; the discount curve "
        "is\n"
        "bootstrapped exactly as for par swaps (single-curve OIS-discounting).",
        "domain": "derivatives",
        "function_name": "ois_curve_sonia_sofr",
        "input_schema": {
            "properties": {
                "frequency": {
                    "default": 1,
                    "description": "Fixed-leg payment " "frequency per year.",
                    "type": "integer",
                },
                "maturities": {
                    "description": "Maturities in " "years, ascending.",
                    "type": "object",
                },
                "ois_rates": {
                    "description": "Quoted OIS rate per " "maturity (decimal).",
                    "type": "object",
                },
            },
            "required": ["ois_rates", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/ois_curve_sonia_sofr",
        "summary": "Build an OIS (SONIA/SOFR) discount curve from quoted OIS swap rates.",
        "tool_name": "ois_curve_sonia_sofr",
    },
    {
        "description": "Net cashflow = ``notional · (compounded_overnight − fixed) · accrual``,\n"
        "discounted. Zero value when the compounded rate equals the fixed rate.",
        "domain": "derivatives",
        "function_name": "overnight_index_swap_ois",
        "input_schema": {
            "properties": {
                "accrual": {"description": "Year-fraction of the " "period.", "type": "number"},
                "compounded_rate": {
                    "description": "Realised/projected "
                    "compounded "
                    "overnight "
                    "rate "
                    "(decimal).",
                    "type": "number",
                },
                "discount_factor": {
                    "description": "Discount " "factor to " "payment.",
                    "type": "number",
                },
                "fixed_rate": {"description": "Fixed OIS rate " "(decimal).", "type": "number"},
                "notional": {"description": "Swap notional.", "type": "number"},
                "pay_fixed": {
                    "default": True,
                    "description": "True if paying " "fixed (receiving " "floating).",
                    "type": "boolean",
                },
            },
            "required": ["notional", "fixed_rate", "compounded_rate", "accrual", "discount_factor"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/overnight_index_swap_ois",
        "summary": "Value a single-period overnight index swap.",
        "tool_name": "overnight_index_swap_ois",
    },
    {
        "description": "A puttable bond is worth at least the equivalent straight bond — the\n"
        "embedded put belongs to the holder.\n"
        "\n"
        "Note: uses the same simplified multiplicative short-rate lattice as\n"
        "``callable_bond_pricer`` — fixed 0.5/0.5 branch probabilities, not\n"
        "calibrated to a market curve.",
        "domain": "derivatives",
        "function_name": "puttable_bond_pricer",
        "input_schema": {
            "properties": {
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {"description": "Par value.", "type": "number"},
                "frequency": {
                    "default": 1,
                    "description": "Coupon payments per " "year (tree steps " "per year).",
                    "type": "integer",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "put_price": {
                    "description": "Price at which the " "holder may put (per " "face).",
                    "type": "number",
                },
                "rate_vol": {"description": "Short-rate " "volatility.", "type": "number"},
                "short_rate": {
                    "description": "Current short rate " "(continuous, " "annual).",
                    "type": "number",
                },
            },
            "required": [
                "face_value",
                "coupon_rate",
                "short_rate",
                "rate_vol",
                "maturity",
                "put_price",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/puttable_bond_pricer",
        "summary": "Price a puttable bond (holder's option) on a short-rate binomial tree.",
        "tool_name": "puttable_bond_pricer",
    },
    {
        "description": "Payoff references the max (best-of) or min (worst-of) of the terminal "
        "asset\n"
        "prices against the strike.",
        "domain": "derivatives",
        "function_name": "rainbow_option_pricer",
        "input_schema": {
            "properties": {
                "correlation": {
                    "description": "Asset correlation " "matrix (SPD).",
                    "type": "object",
                },
                "greeks": {
                    "default": False,
                    "description": "Also compute per-asset "
                    "delta/gamma/vega and "
                    "scalar theta/rho via "
                    "bump-and-reprice (see "
                    "``_multi_asset_bump_reprice_greeks``) "
                    "on the same pre-drawn "
                    "normals used for the "
                    "base price. Delta/ "
                    "gamma/vega are "
                    "diagonal only (each "
                    "asset bumped "
                    "independently; no "
                    "cross-asset terms). "
                    "Defaults to False so "
                    "existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rainbow_type": {
                    "default": "best-of",
                    "description": '``"best-of"`` or ' '``"worst-of"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 61, "description": "RNG seed.", "type": "integer"},
                "sigmas": {"description": "Volatility per asset.", "type": "object"},
                "spots": {"description": "Initial prices per " "asset.", "type": "object"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spots", "strike", "rate", "sigmas", "tau", "correlation"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/rainbow_option_pricer",
        "summary": "Rainbow (best-of / worst-of) option price via Monte Carlo.",
        "tool_name": "rainbow_option_pricer",
    },
    {
        "description": "A rough-volatility model with Hurst exponent ``H < 0.5``. Randoms are\n"
        "pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3).\n"
        "\n"
        "Three independent numerical-correctness bugs were fixed here (task #18,\n"
        "found via the Tier 3 #2 test-reference audit and its follow-up\n"
        "verification -- see _rbergomi_volterra_driver, "
        "_rbergomi_discrete_variance\n"
        "and _rbergomi_paths' docstrings/comments for each in detail):\n"
        "\n"
        "1. The fractional driver froze each increment's weight at the moment it\n"
        "   was drawn instead of recomputing it (as a gap to the current time) at\n"
        "   every later step -- right marginal variance, wrong autocovariance,\n"
        "   invisible to any test that only checks a single time point.\n"
        "2. The martingale correction used the CONTINUUM-limit variance\n"
        "   (``t^(2H)``), which the naive discrete Riemann sum undershoots\n"
        "   substantially at this model's default ``n_steps`` -- pulling\n"
        "   ``E[var_t]`` well below ``xi``.\n"
        "3. The variance applied to a given step's price shock was computed using\n"
        "   that SAME step's own Brownian draw rather than a value predictable\n"
        '   from strictly prior information -- correlating "random" volatility\n'
        "   with the shock it should be independent of and breaking the\n"
        "   risk-neutral drift (``E[S_T] != S0*exp(rT)``; put-call parity was off\n"
        "   by more than 15, not a rounding-level miss).\n"
        "\n"
        "Verified (not merely believed) via three checks the code lacked before:\n"
        "an exact hand-computable impulse-response test on the fractional driver\n"
        "(bug 1), an ``eta -> 0`` reduction to flat-vol Black-Scholes (bugs 2 & 3\n"
        "together -- degenerate case has no vol-of-vol to expose either), and\n"
        "put-call parity at the model's actual default parameters (bug 3\n"
        "specifically, since parity holds regardless of how the volatility itself\n"
        "is modelled).",
        "domain": "derivatives",
        "function_name": "rough_volatility_rbergomi_model",
        "input_schema": {
            "properties": {
                "control_variate": {
                    "default": False,
                    "description": "Use a "
                    "Heston-companion "
                    "control "
                    "variate (task "
                    "#15 Phase 3) "
                    "for a "
                    "lower-variance "
                    "estimate at "
                    "the same "
                    "n_simulations. "
                    "Defaults to "
                    "False so "
                    "existing "
                    "callers/results "
                    "are "
                    "unaffected. A "
                    "companion "
                    "Heston path "
                    "is simulated "
                    "on the SAME "
                    "pre-drawn "
                    "z_v/z_s "
                    "normals (that "
                    "shared "
                    "randomness is "
                    "what makes it "
                    "correlated "
                    "with the "
                    "rBergomi "
                    "payoff -- an "
                    "independently-drawn "
                    "Heston path "
                    "would be a "
                    "useless "
                    "control). The "
                    "companion "
                    "uses "
                    "v0=theta=xi, "
                    "sigma=eta, "
                    "the same rho, "
                    "and an "
                    "internally-fixed "
                    "kappa (see "
                    "``_HESTON_CV_KAPPA``) "
                    "chosen purely "
                    "to maximise "
                    "that "
                    "correlation "
                    "-- rBergomi "
                    "has no "
                    "mean-reversion-speed "
                    "parameter of "
                    "its own, so "
                    "there's no "
                    '"natural" '
                    "kappa to "
                    "inherit. The "
                    "companion's "
                    "known EXACT "
                    "price comes "
                    "from the "
                    "existing "
                    "semi-analytic "
                    "heston_stochastic_volatility_model; "
                    "the optimal "
                    "control-variate "
                    "coefficient "
                    "beta is "
                    "estimated "
                    "from the "
                    "sample "
                    "covariance/variance "
                    "of the two "
                    "payoff series "
                    "(standard "
                    "practice, not "
                    "a fixed "
                    "beta=1 "
                    "subtraction). "
                    "Verified "
                    "empirically "
                    "across two "
                    "parameter "
                    "regimes (this "
                    "model's "
                    "defaults, and "
                    "a second "
                    "regime with "
                    "different "
                    "strike/ "
                    "tau/xi/eta/hurst/rho) "
                    "that this "
                    "gives a real "
                    "~2x-6x "
                    "variance "
                    "reduction "
                    "with no "
                    "measurable "
                    "bias -- "
                    "weaker than "
                    "Phase 2's QMC "
                    "result on the "
                    "exotic-option "
                    "kernels, but "
                    "genuine, "
                    "because "
                    "rBergomi's "
                    "actual "
                    "rough-volatility "
                    "dynamics are "
                    "structurally "
                    "quite "
                    "different "
                    "from Heston's "
                    "Markovian CIR "
                    "process (that "
                    "structural "
                    "gap is "
                    "exactly why "
                    "the "
                    "correlation "
                    "-- and "
                    "therefore the "
                    "achievable "
                    "variance "
                    "reduction -- "
                    "isn't "
                    "larger).",
                    "type": "boolean",
                },
                "eta": {"default": 1.5, "description": "Vol-of-vol parameter.", "type": "number"},
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_bump_reprice_greeks``) "
                    "on the same pre-drawn "
                    "z_v/z_s used for the "
                    'base price. "vega" '
                    "here is sensitivity to "
                    "``xi`` (the "
                    "forward-variance "
                    "level, this model's "
                    "primary volatility "
                    "parameter) -- NOT to "
                    "``eta`` (vol-of-vol) "
                    "or ``hurst``, which "
                    "are structural "
                    "parameters outside the "
                    "standard 5-Greek scope "
                    "and are held fixed. "
                    'The Greek "rho" '
                    "(sensitivity to the "
                    "risk-free rate) is "
                    "unrelated to this "
                    "model's own ``rho`` "
                    "parameter (spot/vol "
                    "correlation, also held "
                    "fixed) -- an "
                    "unfortunate but "
                    "standard name "
                    "collision, not a bug. "
                    "Not supported together "
                    "with "
                    "control_variate=True "
                    "(the control-variate "
                    "coefficient and the "
                    "analytic Heston "
                    "reference price would "
                    "both need re-deriving "
                    "at every bumped "
                    "scenario; deferred "
                    "rather than done "
                    "partially). Defaults "
                    "to False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "hurst": {
                    "default": 0.1,
                    "description": "Hurst exponent in (0, " "0.5).",
                    "type": "number",
                },
                "n_simulations": {
                    "default": 50000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "n_steps": {
                    "default": 50,
                    "description": "Time-discretisation " "steps.",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "rho": {
                    "default": -0.7,
                    "description": "Spot/vol correlation in " "[-1, 1].",
                    "type": "number",
                },
                "seed": {"default": 2024, "description": "RNG seed.", "type": "integer"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
                "xi": {"default": 0.04, "description": "Forward variance level.", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/rough_volatility_rbergomi_model",
        "summary": "Rough Bergomi (rBergomi) European option price via Monte Carlo.",
        "tool_name": "rough_volatility_rbergomi_model",
    },
    {
        "description": "Returns the Black implied volatility for the given strike under the SABR\n"
        "dynamics. At-the-money it reduces to the well-known ATM SABR vol.",
        "domain": "derivatives",
        "function_name": "sabr_volatility_model",
        "input_schema": {
            "properties": {
                "alpha": {"description": "Initial volatility " "level (> 0).", "type": "number"},
                "beta": {"description": "CEV exponent in [0, 1].", "type": "number"},
                "forward": {"description": "Forward price/rate.", "type": "number"},
                "nu": {"description": "Vol-of-vol (>= 0).", "type": "number"},
                "rho": {"description": "Correlation in [-1, 1].", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["forward", "strike", "tau", "alpha", "beta", "rho", "nu"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/sabr_volatility_model",
        "summary": "SABR implied (lognormal/Black) volatility via Hagan's expansion.",
        "tool_name": "sabr_volatility_model",
    },
    {
        "description": "Prices an option on ``S1 − S2`` by reducing it to a Black-76 option on "
        "the\n"
        "ratio with an effective volatility. Exact when ``strike == 0`` "
        "(Margrabe).\n"
        "Inputs are treated as forwards (Black-76); the value is discounted once.",
        "domain": "derivatives",
        "function_name": "spread_option_kirk_approximation",
        "input_schema": {
            "properties": {
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "rho": {"description": "Correlation in [-1, 1].", "type": "number"},
                "sigma1": {"description": "Volatility of asset 1.", "type": "number"},
                "sigma2": {"description": "Volatility of asset 2.", "type": "number"},
                "spot1": {"description": "First-asset forward " "price.", "type": "number"},
                "spot2": {"description": "Second-asset forward " "price.", "type": "number"},
                "strike": {"description": "Spread strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
            },
            "required": ["spot1", "spot2", "strike", "rate", "sigma1", "sigma2", "rho", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/spread_option_kirk_approximation",
        "summary": "Spread option price via Kirk's approximation.",
        "tool_name": "spread_option_kirk_approximation",
    },
    {
        "description": "For each tenor, ``swap_rate = (1 − DF(T)) / (Σ τ · DF)`` — the fixed rate\n"
        "that makes a par swap have zero value.",
        "domain": "derivatives",
        "function_name": "swap_rate_curve",
        "input_schema": {
            "properties": {
                "discount_factors": {
                    "description": "Discount "
                    "factor per "
                    "maturity "
                    "(descending "
                    "in (0, 1]).",
                    "type": "object",
                },
                "frequency": {
                    "default": 1,
                    "description": "Fixed-leg payment " "frequency per year.",
                    "type": "integer",
                },
                "maturities": {
                    "description": "Maturities in " "years, ascending.",
                    "type": "object",
                },
            },
            "required": ["discount_factors", "maturities"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swap_rate_curve",
        "summary": "Par swap rates implied by a discount-factor curve.",
        "tool_name": "swap_rate_curve",
    },
    {
        "description": "``Price = annuity · Black(forward_swap_rate, strike, vol, expiry)``. A "
        "payer\n"
        "swaption is a call on the swap rate; a receiver swaption is a put.",
        "domain": "derivatives",
        "function_name": "swaption_pricer_black",
        "input_schema": {
            "properties": {
                "annuity": {
                    "description": "PV of a 1-unit fixed " "annuity (level / " "PVBP).",
                    "type": "number",
                },
                "expiry": {"description": "Time to swaption " "expiry (years).", "type": "number"},
                "forward_swap_rate": {
                    "description": "Forward par " "swap rate " "(decimal).",
                    "type": "number",
                },
                "notional": {"description": "Swap notional.", "type": "number"},
                "option_type": {
                    "default": "payer",
                    "description": '``"payer"`` or ' '``"receiver"``.',
                    "type": "string",
                },
                "strike": {"description": "Strike swap rate " "(decimal).", "type": "number"},
                "vol": {"description": "Black volatility of the " "swap rate.", "type": "number"},
            },
            "required": ["notional", "forward_swap_rate", "strike", "vol", "expiry", "annuity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swaption_pricer_black",
        "summary": "Price a European swaption under the Black model.",
        "tool_name": "swaption_pricer_black",
    },
    {
        "description": "Computes the SABR lognormal vol for the (forward, strike, expiry) point "
        "via\n"
        "Hagan's expansion, then plugs it into the Black swaption formula.",
        "domain": "derivatives",
        "function_name": "swaption_pricer_sabr",
        "input_schema": {
            "properties": {
                "alpha": {"description": "SABR initial vol level.", "type": "number"},
                "annuity": {"description": "PV of a 1-unit fixed " "annuity.", "type": "number"},
                "beta": {"description": "SABR CEV exponent in [0, " "1].", "type": "number"},
                "expiry": {"description": "Time to expiry " "(years).", "type": "number"},
                "forward_swap_rate": {
                    "description": "Forward par " "swap rate " "(decimal).",
                    "type": "number",
                },
                "notional": {"description": "Swap notional.", "type": "number"},
                "nu": {"description": "SABR vol-of-vol.", "type": "number"},
                "option_type": {
                    "default": "payer",
                    "description": '``"payer"`` or ' '``"receiver"``.',
                    "type": "string",
                },
                "rho": {"description": "SABR correlation.", "type": "number"},
                "strike": {"description": "Strike swap rate " "(decimal).", "type": "number"},
            },
            "required": [
                "notional",
                "forward_swap_rate",
                "strike",
                "expiry",
                "annuity",
                "alpha",
                "beta",
                "rho",
                "nu",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/swaption_pricer_sabr",
        "summary": "Price a swaption using a SABR-implied Black volatility.",
        "tool_name": "swaption_pricer_sabr",
    },
    {
        "description": "The total-return receiver gets the asset's total return and pays a "
        "financing\n"
        "rate (e.g. SOFR + spread): ``notional · (asset_return − financing·τ) · "
        "DF``.",
        "domain": "derivatives",
        "function_name": "total_return_swap_trs",
        "input_schema": {
            "properties": {
                "accrual": {"description": "Year-fraction.", "type": "number"},
                "asset_return": {
                    "description": "Period total " "return of the " "reference asset " "(decimal).",
                    "type": "number",
                },
                "discount_factor": {
                    "description": "Discount " "factor to " "payment.",
                    "type": "number",
                },
                "financing_rate": {
                    "description": "Financing rate " "(decimal, " "annual).",
                    "type": "number",
                },
                "notional": {"description": "Reference notional.", "type": "number"},
                "receive_total_return": {
                    "default": True,
                    "description": "Direction " "flag.",
                    "type": "boolean",
                },
            },
            "required": [
                "notional",
                "asset_return",
                "financing_rate",
                "accrual",
                "discount_factor",
            ],
            "type": "object",
        },
        "path": "/api/v1/derivatives/total_return_swap_trs",
        "summary": "Value a total-return swap leg.",
        "tool_name": "total_return_swap_trs",
    },
    {
        "description": "Up/middle/down branching converges to Black-Scholes for European options.\n"
        "Handles American exercise.",
        "domain": "derivatives",
        "function_name": "trinomial_tree_option_pricer",
        "input_schema": {
            "properties": {
                "div_yield": {
                    "default": 0.0,
                    "description": "Continuous dividend " "yield.",
                    "type": "number",
                },
                "n_steps": {
                    "default": 300,
                    "description": "Number of tree steps " "(>= 1).",
                    "type": "integer",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {
                    "description": "Continuously-compounded " "risk-free rate.",
                    "type": "number",
                },
                "sigma": {"description": "Volatility (annualised, " "> 0).", "type": "number"},
                "spot": {"description": "Underlying spot price.", "type": "number"},
                "strike": {"description": "Strike price.", "type": "number"},
                "style": {
                    "default": "european",
                    "description": '``"european"`` or ' '``"american"``.',
                    "type": "string",
                },
                "tau": {"description": "Time to maturity in years " "(> 0).", "type": "number"},
            },
            "required": ["spot", "strike", "rate", "sigma", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/trinomial_tree_option_pricer",
        "summary": "Boyle trinomial tree option price.",
        "tool_name": "trinomial_tree_option_pricer",
    },
    {
        "description": "Note: the ``theta`` parameter here is the VG skew parameter\n"
        "(subordinated-drift), unrelated to the Greek theta (time decay)\n"
        "optionally returned when ``greeks=True``.\n"
        "\n"
        "Time-changes Brownian motion by a Gamma subordinator (mean 1, variance\n"
        "``nu``). The martingale drift correction ``omega`` is computed in closed\n"
        "form so the discounted spot is a martingale.",
        "domain": "derivatives",
        "function_name": "variance_gamma_model",
        "input_schema": {
            "properties": {
                "greeks": {
                    "default": False,
                    "description": "Also compute "
                    "delta/gamma/vega/theta/rho "
                    "via bump-and-reprice "
                    "(see "
                    "``_levy_bump_reprice_greeks``). "
                    '"vega" here is '
                    "sensitivity to "
                    "``sigma`` (the "
                    "diffusion volatility, "
                    "this model's direct "
                    "Black-Scholes-like vol "
                    "parameter). The Greek "
                    '"theta" (time decay, '
                    "in the output dict) is "
                    "unrelated to this "
                    "function's own "
                    "``theta`` parameter "
                    "(skew) above, which "
                    "stays fixed. "
                    "delta/vega/rho reuse "
                    "the base run's Gamma "
                    "subordinator directly "
                    "(spot/sigma/rate bumps "
                    "don't change its shape "
                    "parameter). theta (the "
                    "Greek) needs a "
                    "subordinator at ``tau "
                    "+/- d_tau``, and the "
                    "Gamma subordinator's "
                    "shape parameter IS "
                    "``tau/nu`` -- so it "
                    "can't just reuse the "
                    "base draw the way "
                    "GBM-based normals can "
                    "under a tau bump. "
                    "Verified empirically "
                    "that independently "
                    "redrawing it at each "
                    "bumped tau gives ~65x "
                    "more seed-to-seed "
                    "noise in theta than "
                    "the alternative "
                    "shipped here: drawing "
                    "ONE shared uniform "
                    "array and mapping it "
                    "through the Gamma "
                    "inverse-CDF at "
                    "``(tau+d_tau)/nu`` and "
                    "``(tau-d_tau)/nu`` "
                    "respectively, which "
                    "keeps the two bumped "
                    "subordinators tightly "
                    "(positively) "
                    "correlated with each "
                    "other the same way "
                    "common random numbers "
                    "correlate every other "
                    "Greek in this "
                    "codebase. Defaults to "
                    "False so existing "
                    "callers/results are "
                    "unaffected.",
                    "type": "boolean",
                },
                "n_simulations": {
                    "default": 100000,
                    "description": "Number of " "paths.",
                    "type": "integer",
                },
                "nu": {
                    "default": 0.2,
                    "description": "Variance rate of the Gamma " "subordinator (> 0).",
                    "type": "number",
                },
                "option_type": {
                    "default": "call",
                    "description": '``"call"`` or ' '``"put"``.',
                    "type": "string",
                },
                "rate": {"description": "Risk-free rate " "(continuous).", "type": "number"},
                "seed": {"default": 7, "description": "RNG seed.", "type": "integer"},
                "sigma": {"default": 0.2, "description": "Diffusion volatility.", "type": "number"},
                "spot": {"description": "Underlying spot.", "type": "number"},
                "strike": {"description": "Strike.", "type": "number"},
                "tau": {"description": "Time to maturity (years, " "> 0).", "type": "number"},
                "theta": {
                    "default": -0.1,
                    "description": "Drift of the "
                    "subordinated Brownian "
                    "motion (skew). NOT the "
                    "Greek theta (time "
                    "decay) -- an "
                    "unfortunate name "
                    "collision with this "
                    "model's own parameter; "
                    "see ``greeks`` below.",
                    "type": "number",
                },
            },
            "required": ["spot", "strike", "rate", "tau"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/variance_gamma_model",
        "summary": "Variance Gamma European option price via Monte Carlo.",
        "tool_name": "variance_gamma_model",
    },
    {
        "description": "``dr = κ(θ−r)dt + σ dW``. The affine ZCB price is ``P = A·e^{−B·r0}``. "
        "The\n"
        "short rate is Gaussian (can go negative).",
        "domain": "derivatives",
        "function_name": "vasicek_interest_rate_model",
        "input_schema": {
            "properties": {
                "kappa": {"description": "Mean-reversion speed (> " "0).", "type": "number"},
                "maturity": {"description": "Bond maturity in " "years (> 0).", "type": "number"},
                "n_simulations": {"default": 50000, "description": "MC paths.", "type": "integer"},
                "n_steps": {"default": 100, "description": "MC time steps.", "type": "integer"},
                "r0": {"description": "Initial short rate.", "type": "number"},
                "seed": {"default": 101, "description": "RNG seed.", "type": "integer"},
                "sigma": {"description": "Volatility (> 0).", "type": "number"},
                "theta": {"description": "Long-run mean.", "type": "number"},
            },
            "required": ["r0", "kappa", "theta", "sigma", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/vasicek_interest_rate_model",
        "summary": "Vasicek model: closed-form zero-coupon bond price + simulated short rate.",
        "tool_name": "vasicek_interest_rate_model",
    },
    {
        "description": "Builds the cashflow stream truncated at ``call_date`` with redemption at\n"
        "``call_price`` and solves for the yield.",
        "domain": "derivatives",
        "function_name": "yield_to_call",
        "input_schema": {
            "properties": {
                "call_date": {
                    "description": "Time to the call " "date in years.",
                    "type": "number",
                },
                "call_price": {
                    "description": "Redemption price " "at the call date.",
                    "type": "number",
                },
                "coupon_rate": {
                    "description": "Annual coupon " "rate (decimal).",
                    "type": "number",
                },
                "face_value": {
                    "description": "Par value (for " "coupon sizing).",
                    "type": "number",
                },
                "frequency": {
                    "default": 2,
                    "description": "Coupon payments per " "year.",
                    "type": "integer",
                },
                "price": {"description": "Observed dirty price.", "type": "number"},
            },
            "required": ["price", "face_value", "coupon_rate", "call_price", "call_date"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/yield_to_call",
        "summary": "Yield to call — yield assuming redemption at the first call date.",
        "tool_name": "yield_to_call",
    },
    {
        "description": "Solved by Brent root-finding. Recovers the input yield exactly when "
        "``price``\n"
        "was produced by :func:`engine.deriv_bonds.bond_pricer_fixed_coupon`.",
        "domain": "derivatives",
        "function_name": "yield_to_maturity",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "price": {"description": "Observed dirty price.", "type": "number"},
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
            },
            "required": ["price", "cashflows", "times"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/yield_to_maturity",
        "summary": "Yield to maturity — the flat rate that discounts cashflows to ``price``.",
        "tool_name": "yield_to_maturity",
    },
    {
        "description": "Solves for ``z`` such that ``Σ cf_k (1 + (zero_k + z)/m)^{-m t_k} = "
        "price``.",
        "domain": "derivatives",
        "function_name": "z_spread_calculator",
        "input_schema": {
            "properties": {
                "cashflows": {"description": "Cashflow amounts.", "type": "object"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "price": {"description": "Observed dirty price.", "type": "number"},
                "times": {"description": "Cashflow times in " "years.", "type": "object"},
                "zero_rates": {
                    "description": "Zero (spot) rate " "per cashflow " "(decimal, " "annualised).",
                    "type": "object",
                },
            },
            "required": ["price", "cashflows", "times", "zero_rates"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/z_spread_calculator",
        "summary": "Z-spread — constant spread over the zero curve that reprices the bond.",
        "tool_name": "z_spread_calculator",
    },
    {
        "description": "",
        "domain": "derivatives",
        "function_name": "zero_coupon_bond_pricer",
        "input_schema": {
            "properties": {
                "face_value": {"description": "Redemption (par) " "value.", "type": "number"},
                "frequency": {
                    "default": 2,
                    "description": "Compounding " "frequency per year.",
                    "type": "integer",
                },
                "maturity": {"description": "Time to maturity in " "years.", "type": "number"},
                "yield_rate": {"description": "Annual yield " "(decimal).", "type": "number"},
            },
            "required": ["face_value", "yield_rate", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/zero_coupon_bond_pricer",
        "summary": "Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.",
        "tool_name": "zero_coupon_bond_pricer",
    },
]

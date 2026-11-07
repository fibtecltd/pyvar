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
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 50, "type": "integer"},
                "option_type": {"default": "put", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 41, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "average_type": {"default": "arithmetic", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "qmc": {"default": False, "type": "boolean"},
                "rate": {"type": "number"},
                "seed": {"default": 21, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "bond_price": {"type": "number"},
                "cashflows": {"type": "object"},
                "face_value": {"default": 100.0, "type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "swap_rates": {"type": "object"},
                "times": {"type": "object"},
                "use_market_price": {"default": False, "type": "boolean"},
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
                "barrier": {"type": "number"},
                "barrier_type": {"default": "down-and-out", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rebate": {"default": 0.0, "type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "correlation": {"type": "object"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 71, "type": "integer"},
                "sigmas": {"type": "object"},
                "spots": {"type": "object"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "weights": {"type": "object"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "exercise_dates": {"default": 4, "type": "integer"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 48, "type": "integer"},
                "option_type": {"default": "put", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 51, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "n_steps": {"default": 500, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "style": {"default": "european", "type": "string"},
                "tau": {"type": "number"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "yield_rate": {"type": "number"},
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
                "discount_rates": {"type": "object"},
                "face_value": {"type": "number"},
                "frequency": {"default": 4, "type": "integer"},
                "maturity": {"type": "number"},
                "reference_rates": {"type": "object"},
                "spread": {"type": "number"},
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
                "face_value": {"default": 1.0, "type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
                "par_rates": {"type": "object"},
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
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturity": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
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
                "accruals": {"type": "object"},
                "discount_factors": {"type": "object"},
                "expiries": {"type": "object"},
                "forward_rates": {"type": "object"},
                "notional": {"type": "number"},
                "option_type": {"default": "cap", "type": "string"},
                "strike": {"type": "number"},
                "vols": {"type": "object"},
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
                "accrual": {"type": "number"},
                "discount_factor": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_rate": {"type": "number"},
                "notional": {"type": "number"},
                "option_type": {"default": "caplet", "type": "string"},
                "strike": {"type": "number"},
                "vol": {"type": "number"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau_choose": {"type": "number"},
                "tau_expiry": {"type": "number"},
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
                "compound_type": {"default": "call-on-call", "type": "string"},
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 200000, "type": "integer"},
                "rate": {"type": "number"},
                "seed": {"default": 81, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike_compound": {"type": "number"},
                "strike_underlying": {"type": "number"},
                "tau_compound": {"type": "number"},
                "tau_underlying": {"type": "number"},
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
                "conversion_ratio": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "stock_price": {"type": "number"},
                "yield_rate": {"type": "number"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
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
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 102, "type": "integer"},
                "sigma": {"type": "number"},
                "theta": {"type": "number"},
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
                "discount_rate": {"type": "number"},
                "frequency": {"default": 4, "type": "integer"},
                "hazard_rate": {"type": "number"},
                "maturity": {"type": "number"},
                "notional": {"type": "number"},
                "recovery_rate": {"type": "number"},
                "spread": {"type": "number"},
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
                "accruals": {"type": "object"},
                "df_dom": {"type": "object"},
                "df_for": {"type": "object"},
                "fixed_rate_dom": {"type": "number"},
                "fixed_rate_for": {"type": "number"},
                "fx_spot": {"type": "number"},
                "notional_dom": {"type": "number"},
                "notional_for": {"type": "number"},
                "pay_domestic": {"default": True, "type": "boolean"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "payout": {"default": 1.0, "type": "number"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "displacement": {"type": "number"},
                "div_yield": {"default": 0.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
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
                "price_base": {"type": "number"},
                "price_down": {"type": "number"},
                "price_up": {"type": "number"},
                "yield_shock": {"type": "number"},
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
                "accrual": {"type": "number"},
                "discount_factor": {"type": "number"},
                "equity_return": {"type": "number"},
                "funding_rate": {"type": "number"},
                "notional": {"type": "number"},
                "receive_equity": {"default": True, "type": "boolean"},
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
                "discount_factor": {"type": "number"},
                "end": {"type": "number"},
                "forward_rate": {"type": "number"},
                "fra_rate": {"type": "number"},
                "notional": {"type": "number"},
                "start": {"type": "number"},
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
                "contracted_forward": {"type": "object"},
                "notional": {"default": 1.0, "type": "number"},
                "rate_domestic": {"type": "number"},
                "rate_foreign": {"type": "number"},
                "spot": {"type": "number"},
                "tau": {"type": "number"},
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
                "notional": {"default": 1.0, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate_domestic": {"type": "number"},
                "rate_foreign": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "kappa": {"type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "theta": {"type": "number"},
                "v0": {"type": "number"},
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
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 103, "type": "integer"},
                "sigma": {"type": "number"},
                "theta_const": {"default": 0.03, "type": "number"},
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
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "inflation_rate": {"type": "number"},
                "maturity": {"type": "number"},
                "real_coupon_rate": {"type": "number"},
                "real_yield": {"type": "number"},
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
                "accruals": {"type": "object"},
                "discount_factors": {"type": "object"},
                "fixed_rate": {"type": "number"},
                "forward_rates": {"type": "object"},
                "notional": {"type": "number"},
                "pay_fixed": {"default": True, "type": "boolean"},
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
                "forward_rates": {"type": "object"},
                "horizon": {"type": "number"},
                "n_simulations": {"default": 20000, "type": "integer"},
                "n_steps": {"default": 20, "type": "integer"},
                "seed": {"default": 104, "type": "integer"},
                "tenor": {"type": "number"},
                "vols": {"type": "object"},
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
                "call_surface": {"type": "object"},
                "maturities": {"type": "object"},
                "rate": {"type": "number"},
                "spot": {"type": "number"},
                "strikes": {"type": "object"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "qmc": {"default": False, "type": "boolean"},
                "rate": {"type": "number"},
                "seed": {"default": 31, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "strike_type": {"default": "floating", "type": "string"},
                "tau": {"type": "number"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "times": {"type": "object"},
                "yield_rate": {"type": "number"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 12345, "type": "integer"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "maturities": {"type": "object"},
                "tau_init": {"default": 1.5, "type": "number"},
                "yields": {"type": "object"},
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
                "maturities": {"type": "object"},
                "tau1_init": {"default": 1.5, "type": "number"},
                "tau2_init": {"default": 8.0, "type": "number"},
                "yields": {"type": "object"},
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
                "alpha": {"default": 15.0, "type": "number"},
                "beta": {"default": -5.0, "type": "number"},
                "delta": {"default": 0.5, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 11, "type": "integer"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "market_price": {"type": "number"},
                "maturity": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
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
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
                "ois_rates": {"type": "object"},
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
                "accrual": {"type": "number"},
                "compounded_rate": {"type": "number"},
                "discount_factor": {"type": "number"},
                "fixed_rate": {"type": "number"},
                "notional": {"type": "number"},
                "pay_fixed": {"default": True, "type": "boolean"},
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
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 1, "type": "integer"},
                "maturity": {"type": "number"},
                "put_price": {"type": "number"},
                "rate_vol": {"type": "number"},
                "short_rate": {"type": "number"},
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
                "correlation": {"type": "object"},
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rainbow_type": {"default": "best-of", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 61, "type": "integer"},
                "sigmas": {"type": "object"},
                "spots": {"type": "object"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "control_variate": {"default": False, "type": "boolean"},
                "eta": {"default": 1.5, "type": "number"},
                "greeks": {"default": False, "type": "boolean"},
                "hurst": {"default": 0.1, "type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 50, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"default": -0.7, "type": "number"},
                "seed": {"default": 2024, "type": "integer"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "xi": {"default": 0.04, "type": "number"},
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
                "alpha": {"type": "number"},
                "beta": {"type": "number"},
                "forward": {"type": "number"},
                "nu": {"type": "number"},
                "rho": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "rho": {"type": "number"},
                "sigma1": {"type": "number"},
                "sigma2": {"type": "number"},
                "spot1": {"type": "number"},
                "spot2": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
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
                "discount_factors": {"type": "object"},
                "frequency": {"default": 1, "type": "integer"},
                "maturities": {"type": "object"},
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
                "annuity": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_swap_rate": {"type": "number"},
                "notional": {"type": "number"},
                "option_type": {"default": "payer", "type": "string"},
                "strike": {"type": "number"},
                "vol": {"type": "number"},
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
                "alpha": {"type": "number"},
                "annuity": {"type": "number"},
                "beta": {"type": "number"},
                "expiry": {"type": "number"},
                "forward_swap_rate": {"type": "number"},
                "notional": {"type": "number"},
                "nu": {"type": "number"},
                "option_type": {"default": "payer", "type": "string"},
                "rho": {"type": "number"},
                "strike": {"type": "number"},
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
                "accrual": {"type": "number"},
                "asset_return": {"type": "number"},
                "discount_factor": {"type": "number"},
                "financing_rate": {"type": "number"},
                "notional": {"type": "number"},
                "receive_total_return": {"default": True, "type": "boolean"},
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
                "div_yield": {"default": 0.0, "type": "number"},
                "n_steps": {"default": 300, "type": "integer"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "sigma": {"type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "style": {"default": "european", "type": "string"},
                "tau": {"type": "number"},
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
                "greeks": {"default": False, "type": "boolean"},
                "n_simulations": {"default": 100000, "type": "integer"},
                "nu": {"default": 0.2, "type": "number"},
                "option_type": {"default": "call", "type": "string"},
                "rate": {"type": "number"},
                "seed": {"default": 7, "type": "integer"},
                "sigma": {"default": 0.2, "type": "number"},
                "spot": {"type": "number"},
                "strike": {"type": "number"},
                "tau": {"type": "number"},
                "theta": {"default": -0.1, "type": "number"},
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
                "kappa": {"type": "number"},
                "maturity": {"type": "number"},
                "n_simulations": {"default": 50000, "type": "integer"},
                "n_steps": {"default": 100, "type": "integer"},
                "r0": {"type": "number"},
                "seed": {"default": 101, "type": "integer"},
                "sigma": {"type": "number"},
                "theta": {"type": "number"},
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
                "call_date": {"type": "number"},
                "call_price": {"type": "number"},
                "coupon_rate": {"type": "number"},
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
                "times": {"type": "object"},
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
                "cashflows": {"type": "object"},
                "frequency": {"default": 2, "type": "integer"},
                "price": {"type": "number"},
                "times": {"type": "object"},
                "zero_rates": {"type": "object"},
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
                "face_value": {"type": "number"},
                "frequency": {"default": 2, "type": "integer"},
                "maturity": {"type": "number"},
                "yield_rate": {"type": "number"},
            },
            "required": ["face_value", "yield_rate", "maturity"],
            "type": "object",
        },
        "path": "/api/v1/derivatives/zero_coupon_bond_pricer",
        "summary": "Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.",
        "tool_name": "zero_coupon_bond_pricer",
    },
]

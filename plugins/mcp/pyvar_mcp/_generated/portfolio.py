"""plugins/mcp/pyvar_mcp/_generated/portfolio.py — GENERATED, do not edit by hand.

The portfolio tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": "``0.5 * sum(|w_i - b_i|)``; 0 means identical to benchmark, 1 means fully\n"
        "differentiated (Cremers & Petajisto).",
        "domain": "portfolio",
        "function_name": "active_share",
        "input_schema": {
            "properties": {"benchmark_weights": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "benchmark_weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/active_share",
        "summary": "Active share — fraction of holdings differing from the benchmark.",
        "tool_name": "active_share",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "average_drawdown",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/average_drawdown",
        "summary": "Average drawdown — mean of the drawdown series magnitude.",
        "tool_name": "average_drawdown",
    },
    {
        "description": "Combines the CAPM-implied equilibrium returns ``Π = λ Σ w_mkt`` with\n"
        "investor views ``P E[r] = Q`` to produce posterior expected returns and "
        "the\n"
        "corresponding mean-variance weights.",
        "domain": "portfolio",
        "function_name": "black_litterman_model",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "market_weights": {"type": "object"},
                "omega": {"type": "object"},
                "p_matrix": {"type": "object"},
                "q_views": {"type": "object"},
                "risk_aversion": {"default": 2.5, "type": "number"},
                "tau": {"default": 0.05, "type": "number"},
            },
            "required": ["market_weights", "cov_matrix", "p_matrix", "q_views"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/black_litterman_model",
        "summary": "Black-Litterman posterior expected returns and weights.",
        "tool_name": "black_litterman_model",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "calmar_ratio",
        "input_schema": {
            "properties": {
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/calmar_ratio",
        "summary": "Calmar ratio — annualised return over maximum drawdown.",
        "tool_name": "calmar_ratio",
    },
    {
        "description": "Computes the Weighted Average Carbon Intensity (WACI) -- this leg matches\n"
        "TCFD's WACI definition regardless of mode.\n"
        "\n"
        "By default (``company_total_emissions``/``company_value`` omitted,\n"
        "unchanged prior behaviour) ``total_financed_emissions`` scales\n"
        "revenue-intensity by invested value per holding, which does NOT match\n"
        "the ownership-share method used by the TCFD/PCAF financed-emissions\n"
        "standards.\n"
        "\n"
        "Supplying BOTH ``company_total_emissions`` (each holding's investee\n"
        "company's total absolute Scope 1+2 emissions, tCO2e) and\n"
        "``company_value`` (each company's total enterprise value -- PCAF's EVIC,\n"
        "enterprise value including cash, or market cap -- same currency unit as\n"
        "``portfolio_value``) switches to the PCAF ownership-share method\n"
        '(Partnership for Carbon Accounting Financials, "The Global GHG\n'
        'Accounting and Reporting Standard for the Financial Industry", Part A,\n'
        "2020; the same method TCFD's 2017 recommendations point to for financed\n"
        "emissions):\n"
        "\n"
        "    ownership_share_i = invested_i / company_value_i\n"
        "    financed_emissions_i = ownership_share_i * company_total_emissions_i\n"
        "\n"
        "where ``invested_i = weights_i * portfolio_value`` is the investor's\n"
        "outstanding amount in company i. Unlike the default (revenue-intensity\n"
        "x invested-value) leg, this correctly represents \"the investor's\n"
        "proportional share of the company's own total emissions\" rather than an\n"
        "intensity-scaled quantity with no ownership interpretation -- an\n"
        "investor's ownership share can never legitimately attribute more than\n"
        "the company's own total emissions (verified in tests).",
        "domain": "portfolio",
        "function_name": "carbon_footprint_attribution",
        "input_schema": {
            "properties": {
                "asset_names": {"type": "object"},
                "carbon_intensities": {"type": "object"},
                "company_total_emissions": {"type": "object"},
                "company_value": {"type": "object"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "carbon_intensities", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/carbon_footprint_attribution",
        "summary": "Carbon footprint attribution (WACI and financed emissions).",
        "tool_name": "carbon_footprint_attribution",
    },
    {
        "description": "Extends Fama-French 3-factor with the momentum (WML/MOM) factor.",
        "domain": "portfolio",
        "function_name": "carhart_4_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/carhart_4_factor_model",
        "summary": "Carhart 4-factor regression (MKT, SMB, HML, MOM).",
        "tool_name": "carhart_4_factor_model",
    },
    {
        "description": "``HHI = sum(w_i^2)`` on absolute weights normalised to sum to 1. Ranges "
        "from\n"
        "``1/n`` (equal weight) to 1 (single holding). The effective number of\n"
        "holdings is ``1/HHI``.",
        "domain": "portfolio",
        "function_name": "concentration_risk_hhi",
        "input_schema": {
            "properties": {"weights": {"type": "object"}},
            "required": ["weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/concentration_risk_hhi",
        "summary": "Concentration risk via the Herfindahl-Hirschman Index (HHI).",
        "tool_name": "concentration_risk_hhi",
    },
    {
        "description": "The mean of the worst ``(1 - confidence_level)`` fraction of drawdowns —\n"
        "the drawdown analogue of Expected Shortfall (Chekhlov, Uryasev, "
        "Zabarankin).",
        "domain": "portfolio",
        "function_name": "conditional_drawdown_at_risk",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.95, "type": "number"},
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/conditional_drawdown_at_risk",
        "summary": "Conditional Drawdown at Risk (CDaR).",
        "tool_name": "conditional_drawdown_at_risk",
    },
    {
        "description": "Builds the correlation distance ``sqrt(2(1 - rho))`` and performs\n"
        "single-linkage agglomerative clustering down to ``n_clusters`` groups —\n"
        "grouping assets that co-move.\n"
        "\n"
        "The merge itself is delegated to ``scipy.cluster.hierarchy.linkage``\n"
        "(``method='single'``) followed by ``fcluster(..., criterion='maxclust')``\n"
        "rather than a hand-rolled merge loop; this is the same single-linkage\n"
        "algorithm (repeatedly merge the two clusters whose minimum pairwise\n"
        "distance is smallest), just computed by SciPy's tested implementation.\n"
        "Cluster *membership* is therefore identical to the earlier hand-rolled\n"
        "version — only the arbitrary integer cluster-id labelling can differ.",
        "domain": "portfolio",
        "function_name": "correlation_clustering",
        "input_schema": {
            "properties": {
                "n_clusters": {"default": 2, "type": "integer"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/correlation_clustering",
        "summary": "Correlation-based clustering of assets.",
        "tool_name": "correlation_clustering",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "correlation_matrix_portfolio",
        "input_schema": {
            "properties": {"returns_matrix": {"type": "object"}},
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/correlation_matrix_portfolio",
        "summary": "Correlation matrix and average pairwise correlation of asset returns.",
        "tool_name": "correlation_matrix_portfolio",
    },
    {
        "description": "By default (``local_risk_free``/``base_risk_free`` omitted, unchanged\n"
        "prior behaviour) this splits the base-currency return into a\n"
        "local-market component and a currency (FX) component per holding,\n"
        "weighted by exposure, via the geometric identity\n"
        "``base = (1+local)(1+fx)-1`` with currency as the residual. This naive\n"
        'split is NOT Karnosky-Singer -- see Bacon, C. (2008), "Practical\n'
        'Portfolio Performance Measurement and Attribution", 2nd ed., Ch. 6,\n'
        "which presents it as the baseline before introducing Karnosky-Singer.\n"
        "\n"
        "Supplying BOTH ``local_risk_free`` (per-holding local-currency\n"
        "risk-free/cash rate) and ``base_risk_free`` (the reporting/base\n"
        "currency's own risk-free rate) switches to Karnosky & Singer's (1994)\n"
        'genuine decomposition ("The Currency Dimension of Global Asset\n'
        'Management and Performance Attribution", CFA Institute Research\n'
        "Foundation): local returns are first netted against the *local*\n"
        "risk-free rate into a local return PREMIUM (the market-selection\n"
        "component the currency side must not re-capture), and the currency\n"
        "side is split into the base cash return and a currency SURPRISE --\n"
        "the currency return net of the covered-interest-parity forward\n"
        "premium implied by the two risk-free rates -- rather than absorbing\n"
        "the interest-rate differential as an unexplained residual:\n"
        "\n"
        "    premium_i = (1+local_i)/(1+local_rf_i) - 1\n"
        "    forward_premium_i = (1+base_rf)/(1+local_rf_i) - 1   (covered interest "
        "parity)\n"
        "    surprise_i = (1+fx_i)/(1+forward_premium_i) - 1\n"
        "\n"
        "These combine via the exact geometric identity\n"
        "``(1+base_rf)(1+premium_i)(1+surprise_i) = (1+local_i)(1+fx_i)`` -- i.e.\n"
        "Karnosky-Singer re-partitions the *same* total base-currency return\n"
        "used by the naive split, it does not change it (verified in tests).\n"
        "The ``currency_effect`` bucket is further broken into\n"
        "``base_cash_effect`` (``base_rf``, common to every holding),\n"
        "``currency_surprise_effect`` (``surprise_i``) and a small\n"
        "``currency_interaction_effect`` residual capturing the compounding\n"
        "cross-terms between the three multiplicative legs -- the same\n"
        "reconciling-residual pattern :func:`return_attribution_brinson` uses\n"
        "for its own interaction effect, so the three currency sub-effects sum\n"
        "exactly to ``currency_effect`` (which itself sums with ``local_effect``\n"
        "to ``total_return``, as before).",
        "domain": "portfolio",
        "function_name": "currency_attribution",
        "input_schema": {
            "properties": {
                "base_risk_free": {"type": "object"},
                "currency_names": {"type": "object"},
                "fx_returns": {"type": "object"},
                "local_returns": {"type": "object"},
                "local_risk_free": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["local_returns", "fx_returns", "weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/currency_attribution",
        "summary": "Currency attribution -- naive geometric split, or genuine Karnosky-Singer.",
        "tool_name": "currency_attribution",
    },
    {
        "description": "Maximises expected return subject to the portfolio CVaR (at\n"
        "``confidence_level``) not exceeding ``cvar_limit``, long-only and fully\n"
        "invested. CVaR is computed empirically over the supplied scenarios.\n"
        "\n"
        "Solved via Rockafellar & Uryasev's (2000) original auxiliary-variable\n"
        "linear-programming reformulation, not a direct nonlinear CVaR\n"
        "constraint. Introduce an auxiliary VaR estimate ``zeta`` and one\n"
        "non-negative excess-loss variable ``u_s`` per scenario, then solve the\n"
        "convex LP\n"
        "\n"
        "    minimize    -mu^T w\n"
        "    subject to  sum(w) = 1,  0 <= w_i <= 1\n"
        "                zeta + (1/(S(1-alpha))) * sum_s u_s <= cvar_limit\n"
        "                u_s >= -(scenario_s . w) - zeta,   u_s >= 0   (s=1..S)\n"
        "\n"
        "via ``scipy.optimize.linprog`` (HiGHS). CVaR is a convex function of\n"
        "``w`` and both this LP and the retired SLSQP-on-empirical-CVaR\n"
        "formulation share the same feasible region and the same (convex)\n"
        "objective, so they solve to the same global optimum — the LP just gets\n"
        "there via Rockafellar-Uryasev's exact reformulation instead of SLSQP\n"
        "re-evaluating the empirical quantile/tail-mean at every iterate.",
        "domain": "portfolio",
        "function_name": "cvar_constrained_optimisation",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.95, "type": "number"},
                "cvar_limit": {"default": 0.05, "type": "number"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "scenario_returns": {"type": "object"},
            },
            "required": ["scenario_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/cvar_constrained_optimisation",
        "summary": "CVaR-constrained portfolio optimisation (Rockafellar-Uryasev).",
        "tool_name": "cvar_constrained_optimisation",
    },
    {
        "description": "``(w' σ) / sqrt(w' Σ w)`` where ``σ`` is the vector of asset "
        "volatilities.\n"
        "Always >= 1; higher means more diversification benefit (Choueifaty).",
        "domain": "portfolio",
        "function_name": "diversification_ratio",
        "input_schema": {
            "properties": {"cov_matrix": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/diversification_ratio",
        "summary": "Diversification ratio — weighted average vol over portfolio vol.",
        "tool_name": "diversification_ratio",
    },
    {
        "description": "Counts consecutive periods spent below the prior peak.",
        "domain": "portfolio",
        "function_name": "drawdown_duration",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/drawdown_duration",
        "summary": "Drawdown duration — longest and current underwater run lengths.",
        "tool_name": "drawdown_duration",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "equal_weight_portfolio",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "n_assets": {"type": "integer"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["n_assets"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/equal_weight_portfolio",
        "summary": "Equal-weight (1/N) portfolio.",
        "tool_name": "equal_weight_portfolio",
    },
    {
        "description": "Computes the weighted-average portfolio ESG score. If ``min_esg_score`` "
        "and\n"
        "a covariance matrix are supplied, solves a minimum-variance long-only\n"
        "portfolio subject to the weighted ESG score meeting the floor.",
        "domain": "portfolio",
        "function_name": "esg_score_integration",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "esg_scores": {"type": "object"},
                "min_esg_score": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "esg_scores"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/esg_score_integration",
        "summary": "ESG score integration — weighted score and optional ESG-constrained tilt.",
        "tool_name": "esg_score_integration",
    },
    {
        "description": "Builds the asset covariance from a factor model\n"
        "``Σ = B F Bᵀ + diag(specific_var)`` and finds the long-only "
        "fully-invested\n"
        "minimum-variance portfolio, optionally matching ``target_exposures`` to "
        "the\n"
        "factors via an equality constraint.",
        "domain": "portfolio",
        "function_name": "factor_based_optimisation",
        "input_schema": {
            "properties": {
                "factor_cov": {"type": "object"},
                "factor_exposures": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "specific_var": {"type": "object"},
                "target_exposures": {"type": "object"},
            },
            "required": ["factor_exposures", "factor_cov", "specific_var"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_based_optimisation",
        "summary": "Factor-based minimum-risk optimisation.",
        "tool_name": "factor_based_optimisation",
    },
    {
        "description": "Aggregates per-asset factor loadings into portfolio-level exposures\n"
        "``Bᵀ w`` — the active/absolute factor tilts of the portfolio.",
        "domain": "portfolio",
        "function_name": "factor_exposure_analysis_barra",
        "input_schema": {
            "properties": {
                "asset_exposures": {"type": "object"},
                "factor_names": {"type": "object"},
                "weights": {"type": "object"},
            },
            "required": ["asset_exposures", "weights"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_exposure_analysis_barra",
        "summary": "Barra-style portfolio factor exposure.",
        "tool_name": "factor_exposure_analysis_barra",
    },
    {
        "description": "Decomposes the realised portfolio return into per-factor contributions\n"
        "``exposure_i * factor_return_i`` plus a specific (idiosyncratic) "
        "component.",
        "domain": "portfolio",
        "function_name": "factor_return_attribution",
        "input_schema": {
            "properties": {
                "factor_exposures": {"type": "object"},
                "factor_names": {"type": "object"},
                "factor_returns": {"type": "object"},
                "specific_return": {"type": "number"},
            },
            "required": ["factor_exposures", "factor_returns", "specific_return"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/factor_return_attribution",
        "summary": "Factor return attribution.",
        "tool_name": "factor_return_attribution",
    },
    {
        "description": "Regresses portfolio excess returns on the market, size (SMB) and value\n"
        "(HML) factors. The intercept is the factor alpha.",
        "domain": "portfolio",
        "function_name": "fama_french_3_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/fama_french_3_factor_model",
        "summary": "Fama-French 3-factor regression (MKT, SMB, HML).",
        "tool_name": "fama_french_3_factor_model",
    },
    {
        "description": "Adds profitability (RMW) and investment (CMA) factors to the 3-factor "
        "model.",
        "domain": "portfolio",
        "function_name": "fama_french_5_factor_model",
        "input_schema": {
            "properties": {"excess_returns": {"type": "object"}, "factors": {"type": "object"}},
            "required": ["excess_returns", "factors"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/fama_french_5_factor_model",
        "summary": "Fama-French 5-factor regression (MKT, SMB, HML, RMW, CMA).",
        "tool_name": "fama_french_5_factor_model",
    },
    {
        "description": "Aggregates position weights into GICS sector buckets and reports each\n"
        "sector's share of the portfolio. Shares sum to the total invested weight.",
        "domain": "portfolio",
        "function_name": "gics_sector_exposure",
        "input_schema": {
            "properties": {"sector_codes": {"type": "array"}, "weights": {"type": "object"}},
            "required": ["weights", "sector_codes"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/gics_sector_exposure",
        "summary": "GICS sector exposure aggregation.",
        "tool_name": "gics_sector_exposure",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "information_ratio",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/information_ratio",
        "summary": "Information ratio — active return over tracking error.",
        "tool_name": "information_ratio",
    },
    {
        "description": "``alpha = mean(r - rf) - beta * mean(b - rf)`` per period; annualised by\n"
        "multiplication by ``periods_per_year``.",
        "domain": "portfolio",
        "function_name": "jensens_alpha",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/jensens_alpha",
        "summary": "Jensen's alpha from the CAPM single-factor regression.",
        "tool_name": "jensens_alpha",
    },
    {
        "description": "Adds a liquidity cost term equal to half the weighted bid-ask spread to "
        "the\n"
        "parametric delta-normal VaR (Bangia-Diebold-Schuermann simplified "
        "add-on),\n"
        "capturing the cost of unwinding positions.",
        "domain": "portfolio",
        "function_name": "liquidity_adjusted_portfolio_var",
        "input_schema": {
            "properties": {
                "bid_ask_spreads": {"type": "object"},
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "horizon_days": {"default": 1, "type": "integer"},
                "portfolio_value": {"type": "number"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "cov_matrix", "bid_ask_spreads", "portfolio_value"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/liquidity_adjusted_portfolio_var",
        "summary": "Liquidity-adjusted parametric VaR (LVaR).",
        "tool_name": "liquidity_adjusted_portfolio_var",
    },
    {
        "description": "Marginal contribution ``(Σw)_i / sigma_p``; component ``w_i * "
        "marginal_i``.\n"
        "Component contributions sum exactly to the portfolio volatility (Euler).",
        "domain": "portfolio",
        "function_name": "marginal_contribution_to_risk",
        "input_schema": {
            "properties": {"cov_matrix": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["weights", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/marginal_contribution_to_risk",
        "summary": "Marginal and component contribution to portfolio volatility risk.",
        "tool_name": "marginal_contribution_to_risk",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "maximum_drawdown",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/maximum_drawdown",
        "summary": "Maximum drawdown — largest peak-to-trough decline.",
        "tool_name": "maximum_drawdown",
    },
    {
        "description": "Maximises the annualised Sharpe ratio subject to weights summing to 1.",
        "domain": "portfolio",
        "function_name": "maximum_sharpe_ratio_portfolio",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/maximum_sharpe_ratio_portfolio",
        "summary": "Maximum Sharpe ratio (tangency) portfolio.",
        "tool_name": "maximum_sharpe_ratio_portfolio",
    },
    {
        "description": "Maximises ``w'μ - 0.5 * λ * w'Σw`` subject to weights summing to 1, with "
        "an\n"
        "optional long-only constraint.",
        "domain": "portfolio",
        "function_name": "mean_variance_optimisation",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_aversion": {"default": 1.0, "type": "number"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/mean_variance_optimisation",
        "summary": "Mean-variance (Markowitz) optimisation.",
        "tool_name": "mean_variance_optimisation",
    },
    {
        "description": "Minimises ``w'Σw`` subject to weights summing to 1. With shorting allowed\n"
        "the closed-form solution ``Σ⁻¹1 / (1'Σ⁻¹1)`` is used; long-only uses "
        "SLSQP.",
        "domain": "portfolio",
        "function_name": "minimum_variance_portfolio",
        "input_schema": {
            "properties": {
                "allow_short": {"default": False, "type": "boolean"},
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/minimum_variance_portfolio",
        "summary": "Global minimum-variance portfolio.",
        "tool_name": "minimum_variance_portfolio",
    },
    {
        "description": "Draws correlated multivariate-normal asset returns (RULE 3: pre-drawn in\n"
        "pure Python via Cholesky), compounds them over the horizon in a JIT "
        "kernel,\n"
        "and reports the simulated VaR / ES of terminal P&L.",
        "domain": "portfolio",
        "function_name": "monte_carlo_portfolio_simulation",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.99, "type": "number"},
                "cov_matrix": {"type": "object"},
                "horizon": {"default": 10, "type": "integer"},
                "mean_returns": {"type": "object"},
                "n_simulations": {"default": 10000, "type": "integer"},
                "portfolio_value": {"default": 1000000.0, "type": "number"},
                "seed": {"default": 12345, "type": "integer"},
                "weights": {"type": "object"},
            },
            "required": ["weights", "mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/monte_carlo_portfolio_simulation",
        "summary": "Monte Carlo portfolio simulation of terminal P&L.",
        "tool_name": "monte_carlo_portfolio_simulation",
    },
    {
        "description": "``Omega = sum(max(r - threshold, 0)) / sum(max(threshold - r, 0))``.",
        "domain": "portfolio",
        "function_name": "omega_ratio",
        "input_schema": {
            "properties": {
                "returns": {"type": "object"},
                "threshold": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/omega_ratio",
        "summary": "Omega ratio — probability-weighted gains over losses about a threshold.",
        "tool_name": "omega_ratio",
    },
    {
        "description": "``beta = cov(r, b) / var(b)``.",
        "domain": "portfolio",
        "function_name": "portfolio_beta",
        "input_schema": {
            "properties": {"benchmark_returns": {"type": "object"}, "returns": {"type": "object"}},
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/portfolio_beta",
        "summary": "Portfolio beta — sensitivity of portfolio returns to the benchmark.",
        "tool_name": "portfolio_beta",
    },
    {
        "description": "``0.5 * sum(|w_after - w_before|)`` (one-way convention).",
        "domain": "portfolio",
        "function_name": "portfolio_turnover",
        "input_schema": {
            "properties": {
                "weights_after": {"type": "object"},
                "weights_before": {"type": "object"},
            },
            "required": ["weights_before", "weights_after"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/portfolio_turnover",
        "summary": "Portfolio turnover — one-way traded fraction between two weight vectors.",
        "tool_name": "portfolio_turnover",
    },
    {
        "description": "Eigendecomposes the covariance matrix to extract orthogonal principal\n"
        "components ordered by explained variance.",
        "domain": "portfolio",
        "function_name": "principal_component_analysis",
        "input_schema": {
            "properties": {
                "n_components": {"type": "object"},
                "returns_matrix": {"type": "object"},
            },
            "required": ["returns_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/principal_component_analysis",
        "summary": "Principal Component Analysis of an asset return matrix.",
        "tool_name": "principal_component_analysis",
    },
    {
        "description": "Computes the trades to move from current to target weights, suppressing\n"
        "trades within a no-trade band to avoid churn, and reports turnover and\n"
        "total transaction cost.\n"
        "\n"
        "By default ``no_trade_band`` is a single user-supplied absolute weight\n"
        "threshold applied uniformly to every asset (unchanged prior behaviour).\n"
        "Supplying both ``asset_volatility`` and ``risk_aversion`` instead\n"
        "*derives* a per-asset band from the classic Constantinides (1986) /\n"
        "Davis & Norman (1990) asymptotic no-trade-region half-width — the\n"
        "closed-form cube-root result that Leland's (1999) mean-variance\n"
        "tracking-error approximation and Donohue & Yip's (2003) practitioner\n"
        "rebalancing-band heuristic both build on:\n"
        "\n"
        "    h_i = ( (3/4) * c_i * sigma_i^2 * w_i^tgt * (1 - w_i^tgt)^2 / gamma "
        ")^(1/3)\n"
        "\n"
        "where ``c_i`` is the proportional transaction cost (``cost_bps_i /\n"
        "1e4``), ``sigma_i`` is asset i's return volatility, ``w_i^tgt`` is asset\n"
        "i's target weight (the frictionless-optimal allocation the band is\n"
        "centred on) and ``gamma`` is the investor's (CRRA) risk-aversion\n"
        "coefficient. The half-width widens with cost and volatility (cube-root\n"
        "scaling) and narrows as risk aversion rises — more risk-averse investors\n"
        "tolerate less drift before trading. This is the classic single-risky-\n"
        "asset asymptotic result applied per-asset; it is not a reproduction of\n"
        "Leland's or Donohue & Yip's own published numerical examples (no\n"
        "published table was available to cross-check exact figures against).\n"
        "\n"
        "When the derived-band mode is used, it *replaces* the scalar\n"
        "``no_trade_band`` for that call rather than combining with it; when\n"
        "either ``asset_volatility`` or ``risk_aversion`` is omitted, behaviour\n"
        "is unchanged — the scalar ``no_trade_band`` is used exactly as before.",
        "domain": "portfolio",
        "function_name": "rebalancing_optimiser",
        "input_schema": {
            "properties": {
                "asset_volatility": {"type": "object"},
                "cost_bps": {"type": "object"},
                "current_weights": {"type": "object"},
                "no_trade_band": {"default": 0.0, "type": "number"},
                "risk_aversion": {"type": "object"},
                "target_weights": {"type": "object"},
            },
            "required": ["current_weights", "target_weights", "cost_bps"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/rebalancing_optimiser",
        "summary": "Rebalancing optimiser with a no-trade band.",
        "tool_name": "rebalancing_optimiser",
    },
    {
        "description": "Note: despite the name, this fits a stationary 2-component Gaussian\n"
        "mixture (EM, i.i.d. weights) — there is no transition matrix, so it does\n"
        "not model true HMM regime persistence/switching dynamics.\n"
        "\n"
        "Fits a two-component Gaussian mixture by EM and labels each observation "
        "by\n"
        "its most likely regime. The higher-variance component is reported as the\n"
        '"stress" regime — the standard calm/turbulent market characterisation.',
        "domain": "portfolio",
        "function_name": "regime_detection_hmm",
        "input_schema": {
            "properties": {
                "n_iter": {"default": 50, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/regime_detection_hmm",
        "summary": "Two-state Gaussian regime detection via EM.",
        "tool_name": "regime_detection_hmm",
    },
    {
        "description": "Bootstraps return samples from the estimated multivariate-normal, solves "
        "the\n"
        "minimum-variance long-only portfolio on each resample, and averages the\n"
        "weights — reducing estimation-error sensitivity. All randomness is "
        "pre-drawn\n"
        "in pure Python (RULE 3).",
        "domain": "portfolio",
        "function_name": "resampled_efficient_frontier",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "n_obs": {"default": 250, "type": "integer"},
                "n_resamples": {"default": 50, "type": "integer"},
                "seed": {"default": 2024, "type": "integer"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/resampled_efficient_frontier",
        "summary": "Resampled efficient frontier (Michaud) minimum-variance point.",
        "tool_name": "resampled_efficient_frontier",
    },
    {
        "description": "Regresses portfolio returns on the benchmark (CAPM) and reports the\n"
        "standard deviation of the residuals — the risk not explained by beta.",
        "domain": "portfolio",
        "function_name": "residual_risk",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/residual_risk",
        "summary": "Residual (idiosyncratic) risk — volatility of single-factor regression "
        "residuals.",
        "tool_name": "residual_risk",
    },
    {
        "description": "Decomposes the active return into allocation, selection and interaction\n"
        "effects per segment. The three effects sum exactly to the total active\n"
        "return — the reconciliation property required for performance reporting.",
        "domain": "portfolio",
        "function_name": "return_attribution_brinson",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "benchmark_weights": {"type": "object"},
                "portfolio_returns": {"type": "object"},
                "portfolio_weights": {"type": "object"},
                "segment_names": {"type": "object"},
            },
            "required": [
                "portfolio_weights",
                "benchmark_weights",
                "portfolio_returns",
                "benchmark_returns",
            ],
            "type": "object",
        },
        "path": "/api/v1/portfolio/return_attribution_brinson",
        "summary": "Brinson-Hood-Beebower return attribution.",
        "tool_name": "return_attribution_brinson",
    },
    {
        "description": "Finds long-only weights so each asset contributes equally to portfolio\n"
        "variance, by minimising the dispersion of risk contributions.\n"
        "\n"
        "Dispersion is measured as the sum of squared pairwise differences\n"
        "between all assets' risk contributions rather than each asset's\n"
        "deviation from the mean contribution -- a stronger gradient signal for\n"
        "SLSQP that converges to the same equal-risk-contribution solution.",
        "domain": "portfolio",
        "function_name": "risk_parity_portfolio",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/risk_parity_portfolio",
        "summary": "Equal risk contribution (risk parity) portfolio.",
        "tool_name": "risk_parity_portfolio",
    },
    {
        "description": "Uses the worst-case expected return ``μ - κ·diag(Σ)^{1/2}`` within an\n"
        "ellipsoidal/box uncertainty set (Tütüncü-Koenig style), then solves the\n"
        "standard mean-variance problem — producing more conservative weights.",
        "domain": "portfolio",
        "function_name": "robust_portfolio_optimisation",
        "input_schema": {
            "properties": {
                "cov_matrix": {"type": "object"},
                "mean_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "risk_aversion": {"default": 1.0, "type": "number"},
                "uncertainty": {"default": 0.05, "type": "number"},
            },
            "required": ["mean_returns", "cov_matrix"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/robust_portfolio_optimisation",
        "summary": "Robust mean-variance optimisation with a box uncertainty set on means.",
        "tool_name": "robust_portfolio_optimisation",
    },
    {
        "description": "A thin specialisation of :func:`return_attribution_brinson` where "
        "segments\n"
        "are GICS sectors. Allocation+selection+interaction reconcile to the "
        "active\n"
        "return.",
        "domain": "portfolio",
        "function_name": "sector_attribution",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "benchmark_weights": {"type": "object"},
                "portfolio_returns": {"type": "object"},
                "portfolio_weights": {"type": "object"},
                "sector_names": {"type": "object"},
            },
            "required": [
                "portfolio_weights",
                "benchmark_weights",
                "portfolio_returns",
                "benchmark_returns",
            ],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sector_attribution",
        "summary": "Sector attribution — Brinson allocation/selection grouped by sector.",
        "tool_name": "sector_attribution",
    },
    {
        "description": "Mean excess return divided by return volatility, annualised by\n"
        "``sqrt(periods_per_year)``.\n"
        "\n"
        "By default (``ddof=0``, unchanged from prior behaviour) volatility is the\n"
        "*population* standard deviation (divide by n) of per-period excess\n"
        "returns. Pass ``ddof=1`` to use the *sample* standard deviation (divide\n"
        "by n-1) instead — the usual unbiased-estimator convention when\n"
        "``returns`` is treated as a sample drawn from a larger population. The\n"
        "``n``-vs-``n-1`` divisor only matters materially for small samples; for\n"
        "the sample sizes typical of return series (hundreds+ of observations)\n"
        "the two converge.",
        "domain": "portfolio",
        "function_name": "sharpe_ratio",
        "input_schema": {
            "properties": {
                "ddof": {"default": 0, "type": "integer"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sharpe_ratio",
        "summary": "Annualised Sharpe ratio.",
        "tool_name": "sharpe_ratio",
    },
    {
        "description": "Like Sharpe but penalises only downside deviation below ``target``, so\n"
        "upside volatility is not treated as risk.\n"
        "\n"
        "The numerator's excess return is measured against ``risk_free`` while\n"
        "the downside-deviation denominator measures shortfalls of the raw (not\n"
        "risk-free-adjusted) returns below the separate ``target``, so when\n"
        "``target != risk_free`` the two are distinct reference rates by\n"
        "construction.",
        "domain": "portfolio",
        "function_name": "sortino_ratio",
        "input_schema": {
            "properties": {
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
                "target": {"default": 0.0, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/sortino_ratio",
        "summary": "Annualised Sortino ratio.",
        "tool_name": "sortino_ratio",
    },
    {
        "description": "``|quantile(1 - tail)| / |quantile(tail)|``. A value above 1 indicates "
        "the\n"
        "right (gain) tail is larger than the left (loss) tail.",
        "domain": "portfolio",
        "function_name": "tail_ratio",
        "input_schema": {
            "properties": {
                "returns": {"type": "object"},
                "tail": {"default": 0.05, "type": "number"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/tail_ratio",
        "summary": "Tail ratio — magnitude of the right tail relative to the left tail.",
        "tool_name": "tail_ratio",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "tracking_error",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/tracking_error",
        "summary": "Tracking error — volatility of active (portfolio minus benchmark) return.",
        "tool_name": "tracking_error",
    },
    {
        "description": "Computes per-trade slippage against an arrival/VWAP benchmark and the\n"
        "quantity-weighted average slippage in basis points. ``side`` is +1 for\n"
        "buys (paying above benchmark is a cost) and -1 for sells.\n"
        "\n"
        "By default (``decision_price`` omitted, unchanged prior behaviour) this\n"
        "is narrower than Perold's (1988) full implementation-shortfall\n"
        "decomposition -- it measures only execution slippage against the\n"
        "``benchmark_prices`` (arrival/VWAP), with no delay-cost leg.\n"
        "\n"
        "Passing ``decision_price`` -- the price at the instant the investment\n"
        'decision was made, Perold\'s "paper" price, distinct from the\n'
        "arrival/VWAP ``benchmark_prices`` used for execution slippage -- adds\n"
        "the delay-cost leg: the cost incurred between the decision and the\n"
        "order reaching the market (``benchmark_prices``), *before* any\n"
        "execution slippage is measured. Delay cost and execution slippage sum\n"
        "exactly to the executed-quantity implementation shortfall measured\n"
        "directly against the decision price:\n"
        "``delay_cost + total_cost == sum(side * (trade_prices - decision_price)\n"
        "* trade_quantities)``.\n"
        "\n"
        "Additionally passing ``unexecuted_quantity`` and ``cancellation_price``\n"
        "together adds the opportunity-cost leg for shares that were never\n"
        "executed: the paper cost of the price move between the decision instant\n"
        "and the price at which the unexecuted portion of the order was marked\n"
        "at cancellation/expiry, ``side * (cancellation_price - decision_price) *\n"
        "unexecuted_quantity``. Delay cost + execution slippage + opportunity\n"
        "cost together are the full-order implementation shortfall against the\n"
        "decision price, covering every share of the original order (executed\n"
        "and unexecuted alike) -- this function still does not model any\n"
        "explicit commission/fee leg, which some treatments of Perold's\n"
        "decomposition include as a further, separate component.",
        "domain": "portfolio",
        "function_name": "transaction_cost_analysis",
        "input_schema": {
            "properties": {
                "benchmark_prices": {"type": "object"},
                "cancellation_price": {"type": "object"},
                "decision_price": {"type": "object"},
                "side": {"default": 1, "type": "integer"},
                "trade_prices": {"type": "object"},
                "trade_quantities": {"type": "object"},
                "unexecuted_quantity": {"type": "object"},
            },
            "required": ["trade_prices", "benchmark_prices", "trade_quantities"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/transaction_cost_analysis",
        "summary": "Transaction Cost Analysis (TCA) — implementation shortfall vs benchmark.",
        "tool_name": "transaction_cost_analysis",
    },
    {
        "description": "",
        "domain": "portfolio",
        "function_name": "treynor_ratio",
        "input_schema": {
            "properties": {
                "benchmark_returns": {"type": "object"},
                "periods_per_year": {"default": 252, "type": "integer"},
                "returns": {"type": "object"},
                "risk_free": {"default": 0.0, "type": "number"},
            },
            "required": ["returns", "benchmark_returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/treynor_ratio",
        "summary": "Treynor ratio — annualised excess return per unit of systematic risk (beta).",
        "tool_name": "treynor_ratio",
    },
    {
        "description": "A depth-and-duration-sensitive risk measure: deeper, longer drawdowns are\n"
        "penalised quadratically.",
        "domain": "portfolio",
        "function_name": "ulcer_index",
        "input_schema": {
            "properties": {
                "is_equity_curve": {"default": False, "type": "boolean"},
                "returns": {"type": "object"},
            },
            "required": ["returns"],
            "type": "object",
        },
        "path": "/api/v1/portfolio/ulcer_index",
        "summary": "Ulcer Index — root-mean-square of percentage drawdowns from peak.",
        "tool_name": "ulcer_index",
    },
]

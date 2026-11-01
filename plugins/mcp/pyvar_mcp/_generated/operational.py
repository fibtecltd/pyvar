"""plugins/mcp/pyvar_mcp/_generated/operational.py — GENERATED, do not edit by hand.

The operational tools. Regenerate with: python3 scripts/generate_mcp_tools.py (from the
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
        "description": "Superseded by the Standardised Measurement Approach for Basel III/IV\n"
        "regulatory capital (see ``basel_standardised_measurement_sma``); retained\n"
        "here for economic-capital, internal scenario analysis, and jurisdictions\n"
        "still on earlier timelines only.\n"
        "\n"
        "The AMA permits the LDA internal model. Under Basel II §669(b), if a bank "
        "can\n"
        "demonstrate that expected loss (EL) is already captured in its "
        "provisioning /\n"
        "pricing, capital may be set to unexpected loss only (OpVaR − EL); "
        "otherwise\n"
        "capital equals the full OpVaR.\n"
        "\n"
        "OpVaR and EL are not supplied by the caller — both are computed internally "
        "by\n"
        "running the full LDA pipeline (frequency/severity MLE fit, then a Monte "
        "Carlo\n"
        "quantile) over ``annual_event_counts`` and ``loss_amounts``.",
        "domain": "operational",
        "function_name": "advanced_measurement_approach_ama",
        "input_schema": {
            "properties": {
                "annual_event_counts": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "expected_loss_covered": {"default": True, "type": "boolean"},
                "loss_amounts": {"type": "object"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["annual_event_counts", "loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/advanced_measurement_approach_ama",
        "summary": "Advanced Measurement Approach (AMA) capital charge — retired under Basel "
        "III/IV.",
        "tool_name": "advanced_measurement_approach_ama",
    },
    {
        "description": "Base score is severity × likelihood on the 5×5 scale; overdue remediation\n"
        "escalates the score (each 30-day block adds an uplift), capped at 25.",
        "domain": "operational",
        "function_name": "audit_finding_risk_scorer",
        "input_schema": {
            "properties": {
                "likelihood": {"type": "integer"},
                "overdue_days": {"type": "number"},
                "severity": {"type": "integer"},
            },
            "required": ["severity", "likelihood", "overdue_days"],
            "type": "object",
        },
        "path": "/api/v1/operational/audit_finding_risk_scorer",
        "summary": "Score an outstanding audit finding by severity, likelihood and ageing.",
        "tool_name": "audit_finding_risk_scorer",
    },
    {
        "description": "SMA capital = BIC × ILM, where the Business Indicator Component (BIC) is "
        "a\n"
        "piecewise-linear function of the Business Indicator (12%/15%/18% marginal\n"
        "coefficients across the three buckets) and the Internal Loss Multiplier\n"
        "(ILM) scales by the bank's historical loss experience:\n"
        "``ILM = ln(e − 1 + (LC / BIC)^0.8)``. Bucket-1 banks may set ILM = 1.\n"
        "\n"
        "The ILM = 1.0 case (``use_ilm=False``, bucket-1 BI, or non-positive BIC) "
        "is\n"
        "an explicit override in code rather than a value the log formula itself\n"
        "produces.",
        "domain": "operational",
        "function_name": "basel_standardised_measurement_sma",
        "input_schema": {
            "properties": {
                "business_indicator": {"type": "number"},
                "loss_component": {"default": 0.0, "type": "number"},
                "use_ilm": {"default": True, "type": "boolean"},
            },
            "required": ["business_indicator"],
            "type": "object",
        },
        "path": "/api/v1/operational/basel_standardised_measurement_sma",
        "summary": "Basel III Standardised Measurement Approach (SMA) capital.",
        "tool_name": "basel_standardised_measurement_sma",
    },
    {
        "description": "Flags where the recovery time objective (RTO) exceeds the maximum\n"
        "tolerable downtime (MTD) and discounts the residual risk by BCP maturity.\n"
        "A breach of either recovery objective is the dominant driver.\n"
        "\n"
        "By default (``rpo_target_hours`` omitted) this is byte-identical to the\n"
        "original RTO-only scoring: ``rpo_hours`` is still range-validated but "
        "does\n"
        "not affect ``bc_risk_score``, since RPO risk has nothing to be measured\n"
        "against without a target to compare it to. Pass ``rpo_target_hours`` (the\n"
        "maximum tolerable period of data loss, per ISO 22301 / DRI International\n"
        "BCM practice) to additionally score potential data loss: RTO and RPO are\n"
        "independently critical recovery objectives — a plan can fail on either\n"
        "axis — so the pre-BCP-maturity risk is the *worse* of the two, not an\n"
        "average of them, consistent with this function's existing \"a breach is\n"
        'the dominant driver" philosophy for RTO alone.',
        "domain": "operational",
        "function_name": "business_continuity_risk_score",
        "input_schema": {
            "properties": {
                "bcp_maturity": {"type": "number"},
                "max_tolerable_downtime": {"type": "number"},
                "rpo_hours": {"type": "number"},
                "rpo_target_hours": {"type": "object"},
                "rto_hours": {"type": "number"},
            },
            "required": ["rto_hours", "rpo_hours", "max_tolerable_downtime", "bcp_maturity"],
            "type": "object",
        },
        "path": "/api/v1/operational/business_continuity_risk_score",
        "summary": "Business-continuity risk from RTO/RPO versus tolerance and BCP maturity.",
        "tool_name": "business_continuity_risk_score",
    },
    {
        "description": "Translates forward-looking business-environment factor scores (e.g. on a "
        "1-5\n"
        "scale where higher = riskier) into a capital multiplier around 1.0: "
        "scores\n"
        "above the baseline increase capital, below decrease it. Part of the BEICF\n"
        "overlay permitted under the AMA.",
        "domain": "operational",
        "function_name": "business_environment_factor_bei",
        "input_schema": {
            "properties": {
                "baseline": {"default": 3.0, "type": "number"},
                "factor_scores": {"type": "object"},
                "sensitivity": {"default": 0.05, "type": "number"},
            },
            "required": ["factor_scores"],
            "type": "object",
        },
        "path": "/api/v1/operational/business_environment_factor_bei",
        "summary": "Business Environment Indicator (BEI) capital adjustment multiplier.",
        "tool_name": "business_environment_factor_bei",
    },
    {
        "description": "The classic frequency ⊗ severity convolution: for each simulated year draw "
        "a\n"
        "Poisson(lambda) number of events, then that many lognormal(mu, sigma)\n"
        "severities, and sum. Per RULE 3 all randomness is pre-drawn in pure "
        "Python;\n"
        "the per-year aggregation runs in the JIT kernel.",
        "domain": "operational",
        "function_name": "compound_loss_distribution",
        "input_schema": {
            "properties": {
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 50000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/compound_loss_distribution",
        "summary": "Simulate the compound (aggregate) annual loss distribution.",
        "tool_name": "compound_loss_distribution",
    },
    {
        "description": "Combines the complaints-per-1000-customers rate and the "
        "redress-to-revenue\n"
        "ratio into a normalised 0-100 conduct-risk index (higher = worse) with a "
        "RAG\n"
        "band.",
        "domain": "operational",
        "function_name": "conduct_risk_metric",
        "input_schema": {
            "properties": {
                "complaints": {"type": "number"},
                "customers": {"type": "number"},
                "redress_paid": {"type": "number"},
                "revenue": {"type": "number"},
            },
            "required": ["complaints", "customers", "redress_paid", "revenue"],
            "type": "object",
        },
        "path": "/api/v1/operational/conduct_risk_metric",
        "summary": "Composite conduct-risk metric from complaints and redress intensity.",
        "tool_name": "conduct_risk_metric",
    },
    {
        "description": "The empirical pass rate from control testing samples; an exception rate "
        "above\n"
        "a supervisory tolerance (default >5% failures) downgrades the conclusion.",
        "domain": "operational",
        "function_name": "control_testing_effectiveness",
        "input_schema": {
            "properties": {"tests_passed": {"type": "integer"}, "tests_total": {"type": "integer"}},
            "required": ["tests_passed", "tests_total"],
            "type": "object",
        },
        "path": "/api/v1/operational/control_testing_effectiveness",
        "summary": "Control testing pass rate and effectiveness conclusion.",
        "tool_name": "control_testing_effectiveness",
    },
    {
        "description": "Worst-case (given a breach) = ``records_exposed × cost_per_record +\n"
        "business_interruption_cost``; expected loss multiplies by the annual "
        "breach\n"
        "probability — a FAIR-style single-loss-expectancy estimate.",
        "domain": "operational",
        "function_name": "cyber_risk_loss_estimation",
        "input_schema": {
            "properties": {
                "breach_probability": {"type": "number"},
                "business_interruption_cost": {"default": 0.0, "type": "number"},
                "cost_per_record": {"type": "number"},
                "records_exposed": {"type": "number"},
            },
            "required": ["records_exposed", "cost_per_record", "breach_probability"],
            "type": "object",
        },
        "path": "/api/v1/operational/cyber_risk_loss_estimation",
        "summary": "Estimate expected and worst-case cyber loss.",
        "tool_name": "cyber_risk_loss_estimation",
    },
    {
        "description": "Compares the simple sum of standalone capitals (perfect-correlation, no\n"
        "diversification) with the correlated aggregate\n"
        "``sqrt(sum_i sum_j rho_ij K_i K_j)`` using a uniform pairwise "
        "correlation.\n"
        "The benefit is the reduction from imperfect correlation.",
        "domain": "operational",
        "function_name": "diversification_benefit_oprisk",
        "input_schema": {
            "properties": {
                "correlation": {"default": 0.0, "type": "number"},
                "standalone_capitals": {"type": "object"},
            },
            "required": ["standalone_capitals"],
            "type": "object",
        },
        "path": "/api/v1/operational/diversification_benefit_oprisk",
        "summary": "Diversification benefit across OpRisk cells under a single correlation.",
        "tool_name": "diversification_benefit_oprisk",
    },
    {
        "description": "Maps a loss amount to the highest governance tier whose threshold it meets "
        "or\n"
        'exceeds (e.g. ``{"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}``).\n'
        "\n"
        "This is a rule-based lookup: it selects the triggered tier with the\n"
        "numerically largest threshold value, not necessarily the dict's declared\n"
        '"highest" tier by name or insertion order, so it relies on ``thresholds``\n'
        "being ordered monotonically with severity.",
        "domain": "operational",
        "function_name": "escalation_threshold_calculation",
        "input_schema": {
            "properties": {"loss_amount": {"type": "number"}, "thresholds": {"type": "object"}},
            "required": ["loss_amount", "thresholds"],
            "type": "object",
        },
        "path": "/api/v1/operational/escalation_threshold_calculation",
        "summary": "Determine the escalation level for a loss against tiered thresholds.",
        "tool_name": "escalation_threshold_calculation",
    },
    {
        "description": "External (consortium / public) losses are scaled to the firm's size by a\n"
        "``scaling_factor`` (e.g. ratio of revenues) before being pooled with "
        "internal\n"
        "losses — the standard approach for enriching a sparse internal tail.",
        "domain": "operational",
        "function_name": "external_loss_data_integration",
        "input_schema": {
            "properties": {
                "external_losses": {"type": "object"},
                "internal_losses": {"type": "object"},
                "scaling_factor": {"type": "number"},
            },
            "required": ["internal_losses", "external_losses", "scaling_factor"],
            "type": "object",
        },
        "path": "/api/v1/operational/external_loss_data_integration",
        "summary": "Integrate scaled external loss data with internal data.",
        "tool_name": "external_loss_data_integration",
    },
    {
        "description": "The Poisson MLE for lambda is the sample mean of annual counts. Also "
        "reports\n"
        "the variance-to-mean ratio (dispersion) — a value far above 1 signals\n"
        "over-dispersion and a possible negative-binomial alternative.",
        "domain": "operational",
        "function_name": "frequency_distribution_fitting",
        "input_schema": {
            "properties": {"annual_event_counts": {"type": "object"}},
            "required": ["annual_event_counts"],
            "type": "object",
        },
        "path": "/api/v1/operational/frequency_distribution_fitting",
        "summary": "Fit a Poisson frequency distribution to annual loss-event counts.",
        "tool_name": "frequency_distribution_fitting",
    },
    {
        "description": "Recoverable amount = ``min(max(gross_loss − deductible, 0), "
        "policy_limit)``\n"
        "reduced by a supervisory haircut (Basel caps total insurance recognition "
        "at\n"
        "20% of capital and applies haircuts for residual term and payment\n"
        "uncertainty; the cap is applied by the caller).",
        "domain": "operational",
        "function_name": "insurance_offset_calculation",
        "input_schema": {
            "properties": {
                "deductible": {"type": "number"},
                "gross_loss": {"type": "number"},
                "haircut": {"default": 0.0, "type": "number"},
                "policy_limit": {"type": "number"},
            },
            "required": ["gross_loss", "policy_limit", "deductible"],
            "type": "object",
        },
        "path": "/api/v1/operational/insurance_offset_calculation",
        "summary": "Insurance mitigation offset for an operational loss.",
        "tool_name": "insurance_offset_calculation",
    },
    {
        "description": "Stronger internal controls (higher average effectiveness in [0, 1]) "
        "reduce\n"
        "the capital multiplier below 1.0; weaker controls increase it. The BEICF\n"
        "counterpart to :func:`business_environment_factor_bei`.",
        "domain": "operational",
        "function_name": "internal_control_factor_icf",
        "input_schema": {
            "properties": {
                "baseline": {"default": 0.8, "type": "number"},
                "control_scores": {"type": "object"},
                "sensitivity": {"default": 0.25, "type": "number"},
            },
            "required": ["control_scores"],
            "type": "object",
        },
        "path": "/api/v1/operational/internal_control_factor_icf",
        "summary": "Internal Control Factor (ICF) capital adjustment multiplier.",
        "tool_name": "internal_control_factor_icf",
    },
    {
        "description": "Blends system availability (fraction), incident frequency and patch\n"
        "compliance (fraction) into a 0-100 IT-risk score (higher = worse) with a "
        "RAG\n"
        "band.",
        "domain": "operational",
        "function_name": "it_risk_scoring",
        "input_schema": {
            "properties": {
                "availability": {"type": "number"},
                "incident_count": {"type": "number"},
                "patch_compliance": {"type": "number"},
            },
            "required": ["availability", "incident_count", "patch_compliance"],
            "type": "object",
        },
        "path": "/api/v1/operational/it_risk_scoring",
        "summary": "IT operational-risk score from availability, incidents and patching.",
        "tool_name": "it_risk_scoring",
    },
    {
        "description": "Each KRI definition must carry a ``name``, a numeric ``amber_threshold`` "
        "and\n"
        '``red_threshold``, and a ``direction`` (``"higher_breach"`` or\n'
        '``"lower_breach"``). Returns a validated registry keyed by name.\n'
        "\n"
        "This is a pure validation/indexing pass — it checks required keys and "
        "builds\n"
        "the keyed registry, with no numeric computation involved.",
        "domain": "operational",
        "function_name": "key_risk_indicator_kri_library",
        "input_schema": {
            "properties": {"kri_definitions": {"type": "array"}},
            "required": ["kri_definitions"],
            "type": "object",
        },
        "path": "/api/v1/operational/key_risk_indicator_kri_library",
        "summary": "Validate and index a KRI library.",
        "tool_name": "key_risk_indicator_kri_library",
    },
    {
        "description": "For ``higher_breach`` KRIs (higher = worse, e.g. failed trades) the value\n"
        "crosses amber then red as it rises; for ``lower_breach`` KRIs (lower = "
        "worse,\n"
        "e.g. staffing level) it crosses as it falls.\n"
        "\n"
        "For ``lower_breach`` every inequality above is reversed (red at or below "
        "the\n"
        "red threshold, amber between red and amber, green above amber).",
        "domain": "operational",
        "function_name": "kri_threshold_breach_detection",
        "input_schema": {
            "properties": {
                "amber_threshold": {"type": "number"},
                "direction": {"default": "higher_breach", "type": "string"},
                "red_threshold": {"type": "number"},
                "value": {"type": "number"},
            },
            "required": ["value", "amber_threshold", "red_threshold"],
            "type": "object",
        },
        "path": "/api/v1/operational/kri_threshold_breach_detection",
        "summary": "Classify a KRI value into a green/amber/red status.",
        "tool_name": "kri_threshold_breach_detection",
    },
    {
        "description": "Fits an OLS slope to the observation series and classifies the trend as\n"
        '``"deteriorating"``, ``"improving"`` or ``"stable"`` based on the slope '
        "sign\n"
        "and the metric direction.\n"
        "\n"
        '"Stable" is a scale-relative rule (``|slope| < 1e-4 * '
        "mean(|observations|)``),\n"
        "not a fixed absolute tolerance, and the deteriorating/improving call "
        "flips\n"
        "with ``higher_is_worse``.",
        "domain": "operational",
        "function_name": "kri_trend_analysis",
        "input_schema": {
            "properties": {
                "higher_is_worse": {"default": True, "type": "boolean"},
                "observations": {"type": "object"},
            },
            "required": ["observations"],
            "type": "object",
        },
        "path": "/api/v1/operational/kri_trend_analysis",
        "summary": "Linear-trend analysis of a KRI time series.",
        "tool_name": "kri_trend_analysis",
    },
    {
        "description": "Filters loss events at or above the firm's de-minimis reporting threshold "
        "and\n"
        "summarises count and total — the internal loss dataset feeding the LDA.",
        "domain": "operational",
        "function_name": "loss_data_collection_framework",
        "input_schema": {
            "properties": {
                "loss_events": {"type": "array"},
                "reporting_threshold": {"type": "number"},
            },
            "required": ["loss_events", "reporting_threshold"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_data_collection_framework",
        "summary": "Internal loss-data collection above a reporting threshold.",
        "tool_name": "loss_data_collection_framework",
    },
    {
        "description": "Fits the frequency (Poisson) and severity (lognormal) distributions from\n"
        "historical data, simulates the compound distribution and reads OpVaR /\n"
        "capital at the regulatory confidence — the full LDA pipeline in one call.\n"
        "\n"
        "This is a composed pipeline, not a single closed-form equation; "
        "``n_years``\n"
        "and ``seed`` only control the internal Monte Carlo simulation, not the\n"
        "capital figure itself.",
        "domain": "operational",
        "function_name": "loss_distribution_approach_lda",
        "input_schema": {
            "properties": {
                "annual_event_counts": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
                "loss_amounts": {"type": "object"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
            },
            "required": ["annual_event_counts", "loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_distribution_approach_lda",
        "summary": "End-to-end Loss Distribution Approach capital estimate.",
        "tool_name": "loss_distribution_approach_lda",
    },
    {
        "description": "Validates the event type against the seven Basel II Level-1 categories\n"
        "(BCBS 128, Annex 9) and returns its ordinal index for downstream "
        "bucketing.\n"
        "\n"
        "This is a membership lookup against the fixed seven Basel II categories, "
        "not\n"
        "a numeric equation.",
        "domain": "operational",
        "function_name": "loss_event_classification_basel",
        "input_schema": {
            "properties": {"event_type": {"type": "string"}},
            "required": ["event_type"],
            "type": "object",
        },
        "path": "/api/v1/operational/loss_event_classification_basel",
        "summary": "Classify a loss event into a Basel II Level-1 event-type category.",
        "tool_name": "loss_event_classification_basel",
    },
    {
        "description": "Combines model materiality and complexity (1-5 each) into an inherent "
        "score,\n"
        "then discounts by validation quality (in [0, 1]) to a residual model-risk\n"
        "tier (SR 11-7 / PRA SS1/23 style).\n"
        "\n"
        "SR 11-7 / PRA SS1/23 are named only for the general materiality x "
        "complexity\n"
        "tiering style this follows; the specific 1-5 scale, multiplication, and "
        "RAG\n"
        "thresholds are pyvar's own, not values prescribed by either document.",
        "domain": "operational",
        "function_name": "model_risk_assessment",
        "input_schema": {
            "properties": {
                "complexity": {"type": "integer"},
                "materiality": {"type": "integer"},
                "validation_score": {"type": "number"},
            },
            "required": ["materiality", "complexity", "validation_score"],
            "type": "object",
        },
        "path": "/api/v1/operational/model_risk_assessment",
        "summary": "Model risk tier from materiality, complexity, and validation quality.",
        "tool_name": "model_risk_assessment",
    },
    {
        "description": "Builds the compound loss distribution and reads the loss quantile at the\n"
        "regulatory confidence (Basel AMA uses 99.9% over a one-year horizon). "
        "Capital\n"
        "is the unexpected loss = OpVaR minus expected loss.",
        "domain": "operational",
        "function_name": "monte_carlo_oprisk_capital",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.999, "type": "number"},
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 100000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/monte_carlo_oprisk_capital",
        "summary": "Monte Carlo OpRisk regulatory capital (OpVaR + expected shortfall).",
        "tool_name": "monte_carlo_oprisk_capital",
    },
    {
        "description": "A near-miss is an event with zero actual loss but a non-zero potential "
        "loss.\n"
        "Validates events and summarises the count and aggregate potential loss — "
        "a\n"
        "leading indicator of control weakness.\n"
        "\n"
        "This is a rule-based filter/count over ``events``; ``actual_loss`` and\n"
        "``potential_loss`` are per-event dict keys rather than top-level function\n"
        "parameters.",
        "domain": "operational",
        "function_name": "near_miss_capture_framework",
        "input_schema": {
            "properties": {"events": {"type": "array"}},
            "required": ["events"],
            "type": "object",
        },
        "path": "/api/v1/operational/near_miss_capture_framework",
        "summary": "Summarise captured near-miss events.",
        "tool_name": "near_miss_capture_framework",
    },
    {
        "description": "Reads the loss quantile at the confidence level directly from a supplied\n"
        "(e.g. simulated or historical) annual-loss array — the generic OpVaR "
        "reader.",
        "domain": "operational",
        "function_name": "operational_var_opvar",
        "input_schema": {
            "properties": {
                "annual_losses": {"type": "object"},
                "confidence_level": {"default": 0.999, "type": "number"},
            },
            "required": ["annual_losses"],
            "type": "object",
        },
        "path": "/api/v1/operational/operational_var_opvar",
        "summary": "Operational VaR from an empirical aggregate-loss sample.",
        "tool_name": "operational_var_opvar",
    },
    {
        "description": "Distributes the firm-wide capital to business lines in proportion to "
        "their\n"
        "standalone risk contributions, so the allocations sum exactly to the total "
        "—\n"
        "a coherent (additive) allocation.",
        "domain": "operational",
        "function_name": "oprisk_capital_allocation",
        "input_schema": {
            "properties": {
                "business_line_risks": {"type": "object"},
                "total_capital": {"type": "number"},
            },
            "required": ["total_capital", "business_line_risks"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_capital_allocation",
        "summary": "Allocate total OpRisk capital across business lines (pro-rata by risk).",
        "tool_name": "oprisk_capital_allocation",
    },
    {
        "description": "Economic capital is the unexpected loss (OpVaR − expected loss) reduced "
        "by\n"
        "recognised risk mitigants (insurance recoveries and diversification), "
        "floored\n"
        "at zero.",
        "domain": "operational",
        "function_name": "oprisk_economic_capital",
        "input_schema": {
            "properties": {
                "diversification_benefit": {"default": 0.0, "type": "number"},
                "expected_loss": {"type": "number"},
                "insurance_offset": {"default": 0.0, "type": "number"},
                "opvar": {"type": "number"},
            },
            "required": ["opvar", "expected_loss"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_economic_capital",
        "summary": "OpRisk economic capital (unexpected loss net of mitigants).",
        "tool_name": "oprisk_economic_capital",
    },
    {
        "description": "Buckets each (likelihood, impact) risk into the 5×5 grid and computes the\n"
        "score (likelihood × impact) and RAG band for each, plus a count matrix of\n"
        "risks per cell.",
        "domain": "operational",
        "function_name": "oprisk_heat_map_generator",
        "input_schema": {
            "properties": {"impacts": {"type": "object"}, "likelihoods": {"type": "object"}},
            "required": ["likelihoods", "impacts"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_heat_map_generator",
        "summary": "Generate a 5×5 OpRisk heat-map distribution.",
        "tool_name": "oprisk_heat_map_generator",
    },
    {
        "description": "Projects stressed capital by scaling the base capital for shocks to event\n"
        "frequency and severity. Because aggregate loss scales (approximately)\n"
        "multiplicatively in both drivers, stressed capital =\n"
        "``base × (1 + freq_shock) × (1 + sev_shock)``.",
        "domain": "operational",
        "function_name": "oprisk_stress_testing",
        "input_schema": {
            "properties": {
                "base_capital": {"type": "number"},
                "frequency_shock": {"type": "number"},
                "severity_shock": {"type": "number"},
            },
            "required": ["base_capital", "frequency_shock", "severity_shock"],
            "type": "object",
        },
        "path": "/api/v1/operational/oprisk_stress_testing",
        "summary": "OpRisk stress-testing capital projection.",
        "tool_name": "oprisk_stress_testing",
    },
    {
        "description": "Combines design effectiveness (is the control well-designed?) and "
        "operating\n"
        "effectiveness (does it operate as intended?) into a single [0, 1] score "
        "via a\n"
        "weighted average.",
        "domain": "operational",
        "function_name": "rcsa_control_effectiveness",
        "input_schema": {
            "properties": {
                "design_score": {"type": "number"},
                "design_weight": {"default": 0.4, "type": "number"},
                "operating_score": {"type": "number"},
            },
            "required": ["design_score", "operating_score"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_control_effectiveness",
        "summary": "Composite control effectiveness from design and operating effectiveness.",
        "tool_name": "rcsa_control_effectiveness",
    },
    {
        "description": "Inherent risk is the gross exposure before controls: ``likelihood × "
        "impact``\n"
        "on the 1-5 scale, giving a 1-25 score mapped to a RAG band.",
        "domain": "operational",
        "function_name": "rcsa_inherent_risk_scoring",
        "input_schema": {
            "properties": {"impact": {"type": "integer"}, "likelihood": {"type": "integer"}},
            "required": ["likelihood", "impact"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_inherent_risk_scoring",
        "summary": "Inherent risk score on the 5×5 RCSA heat map.",
        "tool_name": "rcsa_inherent_risk_scoring",
    },
    {
        "description": "Residual = ``inherent × (1 − control_effectiveness)``: effective controls\n"
        "reduce the inherent score toward zero. The residual is mapped to a RAG "
        "band.",
        "domain": "operational",
        "function_name": "rcsa_residual_risk_scoring",
        "input_schema": {
            "properties": {
                "control_effectiveness": {"type": "number"},
                "inherent_score": {"type": "number"},
            },
            "required": ["inherent_score", "control_effectiveness"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_residual_risk_scoring",
        "summary": "Residual risk after control mitigation.",
        "tool_name": "rcsa_residual_risk_scoring",
    },
    {
        "description": "Checks each risk entry exposes a ``risk_id`` and a Basel ``category`` and\n"
        "summarises counts by category — the identification step of the RCSA "
        "cycle.\n"
        "\n"
        "This is validation plus a count-by-category aggregation, not a numeric\n"
        "formula; ``category`` is a per-entry dict key rather than a top-level\n"
        "function parameter.",
        "domain": "operational",
        "function_name": "rcsa_risk_identification",
        "input_schema": {
            "properties": {"risk_register": {"type": "array"}},
            "required": ["risk_register"],
            "type": "object",
        },
        "path": "/api/v1/operational/rcsa_risk_identification",
        "summary": "Validate and summarise an RCSA risk register.",
        "tool_name": "rcsa_risk_identification",
    },
    {
        "description": "Computes the weighted fraction of regulatory requirements met (each 0 = "
        "not\n"
        "met, 1 = met, or a partial value in between) as a 0-100 compliance score "
        "with\n"
        "a RAG band.",
        "domain": "operational",
        "function_name": "regulatory_compliance_score",
        "input_schema": {
            "properties": {"requirements_met": {"type": "object"}, "weights": {"type": "object"}},
            "required": ["requirements_met"],
            "type": "object",
        },
        "path": "/api/v1/operational/regulatory_compliance_score",
        "summary": "Weighted regulatory-compliance score.",
        "tool_name": "regulatory_compliance_score",
    },
    {
        "description": "Maps a metric to ``within_appetite`` / ``within_tolerance`` / ``breach``\n"
        "against a two-tier limit structure: appetite (the desired ceiling) and\n"
        "tolerance (the absolute maximum before escalation).\n"
        "\n"
        "When ``higher_is_worse=False`` every inequality is reversed and "
        "utilisation\n"
        "is computed as ``tolerance_limit / current_metric`` rather than the\n"
        "``current_metric / tolerance_limit`` used in the higher-is-worse case.",
        "domain": "operational",
        "function_name": "risk_appetite_statement_oprisk",
        "input_schema": {
            "properties": {
                "appetite_limit": {"type": "number"},
                "current_metric": {"type": "number"},
                "higher_is_worse": {"default": True, "type": "boolean"},
                "tolerance_limit": {"type": "number"},
            },
            "required": ["current_metric", "appetite_limit", "tolerance_limit"],
            "type": "object",
        },
        "path": "/api/v1/operational/risk_appetite_statement_oprisk",
        "summary": "Assess an OpRisk metric against appetite and tolerance limits.",
        "tool_name": "risk_appetite_statement_oprisk",
    },
    {
        "description": "Normalises the supplied causal-factor weights (e.g. people, process,\n"
        "systems, external) to sum to 1 and identifies the dominant root cause — "
        "the\n"
        "quantitative backbone of an RCA template.",
        "domain": "operational",
        "function_name": "root_cause_analysis_template",
        "input_schema": {
            "properties": {"causal_factors": {"type": "object"}},
            "required": ["causal_factors"],
            "type": "object",
        },
        "path": "/api/v1/operational/root_cause_analysis_template",
        "summary": "Aggregate root-cause contributions into a normalised attribution.",
        "tool_name": "root_cause_analysis_template",
    },
    {
        "description": "Builds a single scenario's aggregate annual loss distribution from its\n"
        "calibrated frequency and lognormal severity and reads the loss quantile —\n"
        "the scenario's contribution to capital. Per RULE 3 randomness is "
        "pre-drawn\n"
        "in pure Python.",
        "domain": "operational",
        "function_name": "scenario_analysis_oprisk",
        "input_schema": {
            "properties": {
                "confidence_level": {"default": 0.999, "type": "number"},
                "frequency_lambda": {"type": "number"},
                "n_years": {"default": 50000, "type": "integer"},
                "seed": {"default": 42, "type": "object"},
                "severity_mu": {"type": "number"},
                "severity_sigma": {"type": "number"},
            },
            "required": ["frequency_lambda", "severity_mu", "severity_sigma"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_analysis_oprisk",
        "summary": "Scenario-based OpRisk capital via a compound Monte Carlo.",
        "tool_name": "scenario_analysis_oprisk",
    },
    {
        "description": "Combines multiple experts' point estimates into a weighted consensus and\n"
        "reports the dispersion (weighted standard deviation) as a confidence proxy "
        "—\n"
        "wide disagreement signals an unreliable scenario.",
        "domain": "operational",
        "function_name": "scenario_expert_elicitation_model",
        "input_schema": {
            "properties": {
                "expert_estimates": {"type": "object"},
                "expert_weights": {"type": "object"},
            },
            "required": ["expert_estimates"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_expert_elicitation_model",
        "summary": "Aggregate expert loss estimates into a consensus with dispersion.",
        "tool_name": "scenario_expert_elicitation_model",
    },
    {
        "description": "Uses the expert's expected events per year directly, or — if historical\n"
        "occurrence data is supplied — the empirical rate ``occurrences /\n"
        "observation_years``. The result is the Poisson lambda feeding the "
        "scenario's\n"
        "compound loss.",
        "domain": "operational",
        "function_name": "scenario_frequency_estimation",
        "input_schema": {
            "properties": {
                "expected_events_per_year": {"type": "number"},
                "observation_years": {"type": "object"},
                "occurrences": {"type": "object"},
            },
            "required": ["expected_events_per_year"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_frequency_estimation",
        "summary": "Estimate a scenario's annual frequency (Poisson lambda).",
        "tool_name": "scenario_frequency_estimation",
    },
    {
        "description": "Treats ``typical_loss`` as the lognormal median (so ``mu = ln(typical)``) "
        "and\n"
        "solves for ``sigma`` from the worst-case percentile:\n"
        "``sigma = (ln(worst) − mu) / z_p``. This is the standard two-point expert\n"
        "calibration for scenario severities.",
        "domain": "operational",
        "function_name": "scenario_severity_estimation",
        "input_schema": {
            "properties": {
                "typical_loss": {"type": "number"},
                "worst_case_loss": {"type": "number"},
                "worst_case_percentile": {"default": 0.99, "type": "number"},
            },
            "required": ["typical_loss", "worst_case_loss"],
            "type": "object",
        },
        "path": "/api/v1/operational/scenario_severity_estimation",
        "summary": "Calibrate a lognormal severity from expert typical / worst-case losses.",
        "tool_name": "scenario_severity_estimation",
    },
    {
        "description": "Supports four standard OpRisk severity families, all fit by maximum\n"
        "likelihood with the location parameter pinned at zero (severities are\n"
        "strictly positive, so a free location would let the MLE drift away from\n"
        "the actual support):\n"
        "\n"
        '- ``"lognormal"`` (default, the OpRisk industry standard): closed-form '
        "MLE\n"
        "  of the log-loss mean/sigma, i.e. ``scipy.stats.lognorm.fit(x, floc=0)``\n"
        "  reparameterised as ``mu = log(scale)``, ``sigma = shape``.\n"
        '- ``"gamma"``: ``scipy.stats.gamma.fit(x, floc=0)`` — shape ``a`` and\n'
        "  ``scale``; commonly used for moderate, right-skewed severities.\n"
        '- ``"weibull"``: ``scipy.stats.weibull_min.fit(x, floc=0)`` — shape ``c``\n'
        "  and ``scale``; flexible hazard shape, another standard severity choice.\n"
        '- ``"gpd"`` (Generalized Pareto Distribution): '
        "``scipy.stats.genpareto.fit(\n"
        "  x, floc=0)`` — shape ``xi`` and ``scale``; the standard EVT/POT model "
        "for\n"
        "  the tail of large losses (threshold-exceedance modelling). The mean is\n"
        "  only finite for ``xi < 1``; when ``xi >= 1`` ``mean_severity`` is\n"
        "  ``None`` rather than a misleading infinite/negative value.\n"
        "\n"
        "Any other ``distribution`` value raises ``ValueError`` rather than "
        "falling\n"
        "back or approximating.",
        "domain": "operational",
        "function_name": "severity_distribution_fitting",
        "input_schema": {
            "properties": {
                "distribution": {"default": "lognormal", "type": "string"},
                "loss_amounts": {"type": "object"},
            },
            "required": ["loss_amounts"],
            "type": "object",
        },
        "path": "/api/v1/operational/severity_distribution_fitting",
        "summary": "Fit a severity distribution to individual loss amounts.",
        "tool_name": "severity_distribution_fitting",
    },
    {
        "description": "Stresses the extreme tail by scaling losses beyond the tail quantile by a\n"
        '``severity_multiplier`` (e.g. a "perfect-storm" amplification) and '
        "re-reading\n"
        "the stressed tail expectation. Reports the uplift over the unstressed "
        "tail.",
        "domain": "operational",
        "function_name": "tail_risk_scenario_oprisk",
        "input_schema": {
            "properties": {
                "annual_losses": {"type": "object"},
                "severity_multiplier": {"default": 1.0, "type": "number"},
                "tail_confidence": {"default": 0.999, "type": "number"},
            },
            "required": ["annual_losses"],
            "type": "object",
        },
        "path": "/api/v1/operational/tail_risk_scenario_oprisk",
        "summary": "Tail-risk scenario capital uplift for OpRisk.",
        "tool_name": "tail_risk_scenario_oprisk",
    },
    {
        "description": "Weighted index of vendor criticality (1-5), inverse financial health,\n"
        "concentration and inverse substitutability — all normalised to a 0-100 "
        "score\n"
        "(higher = worse).",
        "domain": "operational",
        "function_name": "third_party_vendor_risk",
        "input_schema": {
            "properties": {
                "concentration": {"type": "number"},
                "criticality": {"type": "integer"},
                "financial_health": {"type": "number"},
                "substitutability": {"type": "number"},
            },
            "required": ["criticality", "financial_health", "concentration", "substitutability"],
            "type": "object",
        },
        "path": "/api/v1/operational/third_party_vendor_risk",
        "summary": "Third-party / vendor risk score.",
        "tool_name": "third_party_vendor_risk",
    },
]

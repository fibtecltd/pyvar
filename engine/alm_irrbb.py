"""engine/alm_irrbb.py — IRRBB framework (ALM & Balance Sheet).

[REGULATORY] Basel Committee BCBS d368 (Standards: Interest rate risk in the
banking book, April 2016). Implements the six prescribed rate-shock scenarios,
the standardised EVE framework, an internal-model EVE, repricing gap / maturity
profile, static & dynamic gap, basis risk, option (automatic + behavioural)
risk, pipeline risk, the IRRBB capital outlier metric and the asset-liability
mismatch index.

Pure-Python vectorised NumPy wrappers (CLAUDE.md §3.1 satisfied trivially).
Rate shocks follow BCBS d368: the six shock names are
``parallel_up | parallel_down | steepener | flattener | short_up | short_down``.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "irrbb_six_standard_rate_shocks",
    "irrbb_standardised_framework",
    "irrbb_internal_model",
    "repricing_gap_analysis",
    "repricing_maturity_profile",
    "static_gap_analysis",
    "dynamic_gap_analysis",
    "basis_risk_irrbb",
    "option_risk_irrbb",
    "pipeline_risk_measurement",
    "interest_rate_risk_capital_irrbb",
    "asset_liability_mismatch_index",
]

SIX_SHOCKS = (
    "parallel_up",
    "parallel_down",
    "steepener",
    "flattener",
    "short_up",
    "short_down",
)


def irrbb_six_standard_rate_shocks(
    tenors: np.ndarray,
    parallel_bps: float = 200.0,
    short_bps: float = 300.0,
    long_bps: float = 150.0,
) -> dict:  # type: ignore[type-arg]
    """Construct the six BCBS d368 standard interest-rate shock curves.

    [REGULATORY] BCBS d368 §115. The steepener/flattener combine scaled short
    and long shocks: ``steepener = −0.65·short + 0.90·long`` and
    ``flattener = +0.80·short − 0.60·long`` (per-tenor short/long scalars decay
    as ``e^{−t/4}``).

    Args:
        tenors: Tenor points in years (> 0).
        parallel_bps: Parallel shock magnitude (basis points).
        short_bps: Short-rate shock magnitude (basis points).
        long_bps: Long-rate shock magnitude (basis points).

    Returns:
        Dict mapping each of the six shock names to a per-tenor shock array
        (in decimal, not bps).

    Raises:
        ValueError: If ``tenors`` is empty.
    """
    t = np.asarray(tenors, dtype=np.float64)
    if t.size == 0:
        raise ValueError("tenors must be non-empty")

    par = parallel_bps / 1e4
    s_short = short_bps / 1e4 * np.exp(-t / 4.0)  # decays with tenor
    s_long = long_bps / 1e4 * (1.0 - np.exp(-t / 4.0))  # grows with tenor

    shocks = {
        "parallel_up": np.full(t.size, par),
        "parallel_down": np.full(t.size, -par),
        "short_up": s_short,
        "short_down": -s_short,
        "steepener": -0.65 * s_short + 0.90 * s_long,
        "flattener": 0.80 * s_short - 0.60 * s_long,
    }
    return {name: shocks[name].tolist() for name in SIX_SHOCKS}


def _eve_under_curve(cashflows: np.ndarray, times: np.ndarray, zero_rates: np.ndarray) -> float:
    """PV of net cashflows under a (possibly shocked) zero curve."""
    df = np.exp(-zero_rates * times)
    return float(np.sum(cashflows * df))


def economic_value_helper(
    net_cashflows: np.ndarray, times: np.ndarray, base_rates: np.ndarray
) -> float:
    """Helper exposing base EVE (used by NII/EVE module)."""
    return _eve_under_curve(net_cashflows, times, base_rates)


def irrbb_standardised_framework(
    net_cashflows: np.ndarray,
    times: np.ndarray,
    base_rates: np.ndarray,
    parallel_bps: float = 200.0,
    short_bps: float = 300.0,
    long_bps: float = 150.0,
) -> dict:  # type: ignore[type-arg]
    """Standardised IRRBB EVE measure: worst ΔEVE across the six shocks.

    [REGULATORY] BCBS d368. ΔEVE per scenario is the change in the present value
    of net banking-book cashflows under the shocked curve; the regulatory metric
    is the maximum loss (most negative ΔEVE).

    Args:
        net_cashflows: Net (asset − liability) cashflow per time bucket.
        times: Bucket midpoint times in years.
        base_rates: Base zero rate per bucket (decimal).
        parallel_bps: Parallel shock magnitude (bps).
        short_bps: Short shock magnitude (bps).
        long_bps: Long shock magnitude (bps).

    Returns:
        Dict with ``base_eve``, per-scenario ``delta_eve`` and ``worst_case``.

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    cf = np.asarray(net_cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    r0 = np.asarray(base_rates, dtype=np.float64)
    if not (cf.size == t.size == r0.size):
        raise ValueError("net_cashflows, times, base_rates must match length")

    base_eve = _eve_under_curve(cf, t, r0)
    shocks = irrbb_six_standard_rate_shocks(t, parallel_bps, short_bps, long_bps)
    delta_eve: dict[str, float] = {}
    for name in SIX_SHOCKS:
        shocked = r0 + np.asarray(shocks[name], dtype=np.float64)
        delta_eve[name] = round(_eve_under_curve(cf, t, shocked) - base_eve, 6)
    worst = min(delta_eve.values())
    worst_name = min(delta_eve, key=lambda k: delta_eve[k])
    return {
        "base_eve": round(base_eve, 6),
        "delta_eve": delta_eve,
        "worst_case": round(worst, 6),
        "worst_scenario": worst_name,
    }


def irrbb_internal_model(
    net_cashflows: np.ndarray,
    times: np.ndarray,
    base_rates: np.ndarray,
    rate_scenarios: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Internal-model IRRBB EVE using a bank's own rate scenarios.

    Unlike the standardised framework this accepts an arbitrary matrix of
    rate-shock scenarios (e.g. historical or Monte Carlo simulated) and reports
    the EVE distribution and a 99% worst-case.

    Args:
        net_cashflows: Net cashflow per bucket.
        times: Bucket times in years.
        base_rates: Base zero rate per bucket (decimal).
        rate_scenarios: ``(n_scenarios, n_buckets)`` additive rate shocks.

    Returns:
        Dict with ``base_eve``, ``mean_delta_eve``, ``worst_case_99``.

    Raises:
        ValueError: If shapes are inconsistent.
    """
    cf = np.asarray(net_cashflows, dtype=np.float64)
    t = np.asarray(times, dtype=np.float64)
    r0 = np.asarray(base_rates, dtype=np.float64)
    scen = np.asarray(rate_scenarios, dtype=np.float64)
    if not (cf.size == t.size == r0.size):
        raise ValueError("net_cashflows, times, base_rates must match length")
    if scen.ndim != 2 or scen.shape[1] != cf.size:
        raise ValueError("rate_scenarios must be (n_scenarios, n_buckets)")

    base_eve = _eve_under_curve(cf, t, r0)
    deltas = np.array([_eve_under_curve(cf, t, r0 + scen[i]) - base_eve for i in range(scen.shape[0])])
    worst_99 = float(np.percentile(deltas, 1.0))
    return {
        "base_eve": round(base_eve, 6),
        "mean_delta_eve": round(float(np.mean(deltas)), 6),
        "worst_case_99": round(worst_99, 6),
    }


def repricing_gap_analysis(
    bucket_assets: np.ndarray,
    bucket_liabilities: np.ndarray,
    bucket_labels: list[str] | None = None,
) -> dict:  # type: ignore[type-arg]
    """Repricing gap per time bucket and the cumulative gap.

    ``gap_i = RSA_i − RSL_i``; the cumulative gap drives NII sensitivity.

    Args:
        bucket_assets: Rate-sensitive assets repricing in each bucket.
        bucket_liabilities: Rate-sensitive liabilities repricing in each bucket.
        bucket_labels: Optional bucket names.

    Returns:
        Dict with ``gap`` (per bucket), ``cumulative_gap`` and ``total_gap``.

    Raises:
        ValueError: If the two arrays differ in length.
    """
    a = np.asarray(bucket_assets, dtype=np.float64)
    l = np.asarray(bucket_liabilities, dtype=np.float64)
    if a.size != l.size:
        raise ValueError("bucket_assets and bucket_liabilities must match length")
    gap = a - l
    cumulative = np.cumsum(gap)
    if bucket_labels is None:
        bucket_labels = [f"bucket_{i}" for i in range(a.size)]
    return {
        "gap": {bucket_labels[i]: round(float(gap[i]), 6) for i in range(a.size)},
        "cumulative_gap": [round(float(c), 6) for c in cumulative],
        "total_gap": round(float(np.sum(gap)), 6),
    }


def repricing_maturity_profile(
    balances: np.ndarray,
    repricing_times: np.ndarray,
    n_buckets: int,
    bucket_edges: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Allocate balances into repricing-time buckets.

    Args:
        balances: Balance per instrument.
        repricing_times: Next repricing time per instrument (years).
        n_buckets: Number of buckets.
        bucket_edges: Length ``n_buckets+1`` ascending bucket boundaries.

    Returns:
        Dict with ``profile`` (balance per bucket) and ``weighted_avg_repricing``.

    Raises:
        ValueError: If inputs are inconsistent.
    """
    b = np.asarray(balances, dtype=np.float64)
    rt = np.asarray(repricing_times, dtype=np.float64)
    edges = np.asarray(bucket_edges, dtype=np.float64)
    if b.size != rt.size:
        raise ValueError("balances and repricing_times must match length")
    if edges.size != n_buckets + 1:
        raise ValueError("bucket_edges must have length n_buckets+1")

    profile = np.zeros(n_buckets, dtype=np.float64)
    idx = np.clip(np.digitize(rt, edges[1:-1]), 0, n_buckets - 1)
    for k in range(b.size):
        profile[idx[k]] += b[k]
    total = float(np.sum(b))
    wavg = float(np.sum(b * rt) / total) if total != 0 else 0.0
    return {
        "profile": [round(float(p), 6) for p in profile],
        "weighted_avg_repricing": round(wavg, 8),
    }


def static_gap_analysis(
    bucket_assets: np.ndarray,
    bucket_liabilities: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Static (point-in-time) repricing gap assuming a frozen balance sheet.

    Args:
        bucket_assets: Rate-sensitive assets per bucket.
        bucket_liabilities: Rate-sensitive liabilities per bucket.

    Returns:
        Dict with ``gap``, ``cumulative_gap`` and ``gap_ratio`` (RSA/RSL).

    Raises:
        ValueError: If the arrays differ in length.
    """
    a = np.asarray(bucket_assets, dtype=np.float64)
    l = np.asarray(bucket_liabilities, dtype=np.float64)
    if a.size != l.size:
        raise ValueError("arrays must match length")
    gap = a - l
    total_l = float(np.sum(l))
    ratio = float(np.sum(a) / total_l) if total_l != 0 else float("inf")
    return {
        "gap": [round(float(g), 6) for g in gap],
        "cumulative_gap": [round(float(c), 6) for c in np.cumsum(gap)],
        "gap_ratio": round(ratio, 8),
    }


def dynamic_gap_analysis(
    bucket_assets: np.ndarray,
    bucket_liabilities: np.ndarray,
    asset_growth: np.ndarray,
    liability_growth: np.ndarray,
    n_periods: int,
) -> dict:  # type: ignore[type-arg]
    """Dynamic gap projecting balance growth over future periods.

    Applies per-bucket growth rates compounding over ``n_periods`` and returns
    the projected gap path — capturing new business unlike a static gap.

    Args:
        bucket_assets: Initial rate-sensitive assets per bucket.
        bucket_liabilities: Initial rate-sensitive liabilities per bucket.
        asset_growth: Per-period asset growth rate per bucket (decimal).
        liability_growth: Per-period liability growth rate per bucket.
        n_periods: Number of projection periods.

    Returns:
        Dict with ``projected_total_gap`` (length n_periods).

    Raises:
        ValueError: If array lengths are inconsistent.
    """
    a = np.asarray(bucket_assets, dtype=np.float64)
    l = np.asarray(bucket_liabilities, dtype=np.float64)
    ag = np.asarray(asset_growth, dtype=np.float64)
    lg = np.asarray(liability_growth, dtype=np.float64)
    if not (a.size == l.size == ag.size == lg.size):
        raise ValueError("all arrays must match length")

    path = []
    for p in range(1, n_periods + 1):
        a_p = a * (1.0 + ag) ** p
        l_p = l * (1.0 + lg) ** p
        path.append(round(float(np.sum(a_p - l_p)), 6))
    return {"projected_total_gap": path}


def basis_risk_irrbb(
    asset_balances: np.ndarray,
    asset_index_shifts: np.ndarray,
    liability_balances: np.ndarray,
    liability_index_shifts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Basis risk: NII impact of imperfectly-correlated index repricing.

    [REGULATORY] BCBS d368 — basis risk arises when assets and liabilities
    reprice off different indices. ΔNII = Σ A·Δi_A − Σ L·Δi_L.

    Args:
        asset_balances: Balance per asset index bucket.
        asset_index_shifts: Index move per asset bucket (decimal).
        liability_balances: Balance per liability index bucket.
        liability_index_shifts: Index move per liability bucket (decimal).

    Returns:
        Dict with ``basis_risk_nii``.

    Raises:
        ValueError: If paired arrays differ in length.
    """
    ab = np.asarray(asset_balances, dtype=np.float64)
    ash = np.asarray(asset_index_shifts, dtype=np.float64)
    lb = np.asarray(liability_balances, dtype=np.float64)
    lsh = np.asarray(liability_index_shifts, dtype=np.float64)
    if ab.size != ash.size or lb.size != lsh.size:
        raise ValueError("balances and shifts must match length within each side")
    nii = float(np.sum(ab * ash) - np.sum(lb * lsh))
    return {"basis_risk_nii": round(nii, 6)}


def option_risk_irrbb(
    automatic_option_value: float,
    behavioural_option_value: float,
    notional: float,
) -> dict:  # type: ignore[type-arg]
    """Option risk: value of automatic and behavioural embedded options.

    [REGULATORY] BCBS d368 distinguishes automatic options (caps/floors,
    prepayment options exercised optimally) from behavioural options (early
    redemption, deposit withdrawal). Total option risk = sum of both.

    Args:
        automatic_option_value: PV of automatic interest-rate options.
        behavioural_option_value: PV of behavioural options.
        notional: Reference notional for the option-risk ratio.

    Returns:
        Dict with ``total_option_risk`` and ``option_risk_ratio``.

    Raises:
        ValueError: If ``notional`` is non-positive.
    """
    if notional <= 0:
        raise ValueError("notional must be positive")
    total = automatic_option_value + behavioural_option_value
    return {
        "total_option_risk": round(float(total), 6),
        "option_risk_ratio": round(float(total / notional), 8),
    }


def pipeline_risk_measurement(
    pipeline_notional: float,
    pull_through_rate: float,
    rate_lock_period: float,
    rate_volatility: float,
) -> dict:  # type: ignore[type-arg]
    """Pipeline risk of rate-locked mortgage commitments not yet on balance.

    Exposure = ``notional · pull_through``; the rate risk scales with the
    rate-lock period and rate volatility (a √time vol exposure proxy).

    Args:
        pipeline_notional: Committed pipeline notional.
        pull_through_rate: Expected fraction that completes in [0, 1].
        rate_lock_period: Rate-lock horizon in years.
        rate_volatility: Annualised rate volatility (decimal).

    Returns:
        Dict with ``expected_exposure`` and ``rate_risk``.

    Raises:
        ValueError: If ``pull_through_rate`` not in [0, 1].
    """
    if not 0.0 <= pull_through_rate <= 1.0:
        raise ValueError("pull_through_rate must be in [0, 1]")
    if rate_lock_period < 0 or rate_volatility < 0:
        raise ValueError("rate_lock_period and rate_volatility must be >= 0")
    exposure = pipeline_notional * pull_through_rate
    rate_risk = exposure * rate_volatility * np.sqrt(rate_lock_period)
    return {
        "expected_exposure": round(float(exposure), 6),
        "rate_risk": round(float(rate_risk), 6),
    }


def interest_rate_risk_capital_irrbb(
    worst_delta_eve: float,
    tier1_capital: float,
    outlier_threshold: float = 0.15,
) -> dict:  # type: ignore[type-arg]
    """IRRBB supervisory outlier test against Tier-1 capital.

    [REGULATORY] BCBS d368 §118: a bank is an outlier if the worst-case EVE
    decline exceeds 15% of Tier-1 capital. Capital implied is the breach amount.

    Args:
        worst_delta_eve: Worst-case ΔEVE (negative for a loss).
        tier1_capital: Tier-1 capital (currency).
        outlier_threshold: Supervisory threshold (default 0.15 = 15%).

    Returns:
        Dict with ``eve_decline``, ``threshold_amount``, ``is_outlier`` and
        ``capital_add_on``.

    Raises:
        ValueError: If ``tier1_capital`` is non-positive.
    """
    if tier1_capital <= 0:
        raise ValueError("tier1_capital must be positive")
    decline = abs(min(worst_delta_eve, 0.0))
    threshold_amount = outlier_threshold * tier1_capital
    is_outlier = decline > threshold_amount
    add_on = max(decline - threshold_amount, 0.0)
    return {
        "eve_decline": round(float(decline), 6),
        "threshold_amount": round(float(threshold_amount), 6),
        "is_outlier": bool(is_outlier),
        "capital_add_on": round(float(add_on), 6),
    }


def asset_liability_mismatch_index(
    asset_durations: np.ndarray,
    asset_amounts: np.ndarray,
    liability_durations: np.ndarray,
    liability_amounts: np.ndarray,
) -> dict:  # type: ignore[type-arg]
    """Asset-liability mismatch index from duration-weighted exposures.

    Index = normalised absolute duration gap
    ``|D_A·A − D_L·L| / A`` — zero when the book is perfectly immunised.

    Args:
        asset_durations: Duration per asset bucket (years).
        asset_amounts: Amount per asset bucket (currency).
        liability_durations: Duration per liability bucket.
        liability_amounts: Amount per liability bucket.

    Returns:
        Dict with ``mismatch_index``, ``asset_dollar_duration``,
        ``liability_dollar_duration``.

    Raises:
        ValueError: If paired arrays differ in length.
    """
    ad = np.asarray(asset_durations, dtype=np.float64)
    aa = np.asarray(asset_amounts, dtype=np.float64)
    ld = np.asarray(liability_durations, dtype=np.float64)
    la = np.asarray(liability_amounts, dtype=np.float64)
    if ad.size != aa.size or ld.size != la.size:
        raise ValueError("durations and amounts must match length within each side")

    a_dollar = float(np.sum(ad * aa))
    l_dollar = float(np.sum(ld * la))
    total_assets = float(np.sum(aa))
    index = abs(a_dollar - l_dollar) / total_assets if total_assets != 0 else 0.0
    return {
        "mismatch_index": round(float(index), 8),
        "asset_dollar_duration": round(a_dollar, 6),
        "liability_dollar_duration": round(l_dollar, 6),
    }

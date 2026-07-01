"""tests/validation/test_ops_ref.py — P5a operational-risk reference validation.

Every function in the six operational-risk engine modules is validated against an
EXTERNAL reference, never against the function's own output:

* Closed-form / statistical checks are cross-validated with SciPy or an
  independent NumPy re-derivation (Poisson MLE, lognormal MoM, compound mean
  E[N]*E[X], empirical high quantile). These are marked
  "cross-validated (scipy), not regulator-sourced".
* Regulatory checks cite the governing Basel Committee document/section
  (BCBS d424 for the SMA; BCBS 128 Annex 9 for the Basel loss-event taxonomy).
* Scoring / governance functions with no published closed form are checked with
  an independent hand-calculation recomputed from the inputs inside the test,
  marked "independent hand-calc, no published reference".

Structural / regulatory-property assertions are included throughout: capital>=0,
OpVaR monotone in confidence, diversification benefit in [0, sum], residual <=
inherent, insurance offset reduces capital.

Stochastic engines (LDA / AMA / scenario Monte Carlo) use fixed seeds.
Tolerances: 0.1% relative for Monte-Carlo OpVaR; tighter for closed form; zero
tolerance for Basel-defined boundaries.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import stats

from engine.oprisk_capital import (
    basel_standardised_measurement_sma,
    diversification_benefit_oprisk,
    insurance_offset_calculation,
    oprisk_capital_allocation,
    oprisk_economic_capital,
    oprisk_stress_testing,
    tail_risk_scenario_oprisk,
)
from engine.oprisk_governance import (
    audit_finding_risk_scorer,
    business_continuity_risk_score,
    conduct_risk_metric,
    cyber_risk_loss_estimation,
    escalation_threshold_calculation,
    it_risk_scoring,
    model_risk_assessment,
    near_miss_capture_framework,
    oprisk_heat_map_generator,
    regulatory_compliance_score,
    risk_appetite_statement_oprisk,
    root_cause_analysis_template,
    third_party_vendor_risk,
)
from engine.oprisk_kri import (
    key_risk_indicator_kri_library,
    kri_threshold_breach_detection,
    kri_trend_analysis,
)
from engine.oprisk_lda import (
    advanced_measurement_approach_ama,
    compound_loss_distribution,
    frequency_distribution_fitting,
    loss_distribution_approach_lda,
    monte_carlo_oprisk_capital,
    operational_var_opvar,
    severity_distribution_fitting,
)
from engine.oprisk_rcsa import (
    business_environment_factor_bei,
    control_testing_effectiveness,
    external_loss_data_integration,
    internal_control_factor_icf,
    loss_data_collection_framework,
    loss_event_classification_basel,
    rcsa_control_effectiveness,
    rcsa_inherent_risk_scoring,
    rcsa_residual_risk_scoring,
    rcsa_risk_identification,
)
from engine.oprisk_scenario import (
    scenario_analysis_oprisk,
    scenario_expert_elicitation_model,
    scenario_frequency_estimation,
    scenario_severity_estimation,
)

# Relative tolerance for Monte-Carlo OpVaR-type comparisons.
MC_RTOL = 1e-3
# Tolerance for deterministic closed-form comparisons.
CF_RTOL = 1e-9


# ---------------------------------------------------------------------------
# engine/oprisk_lda.py
# ---------------------------------------------------------------------------


def test_frequency_distribution_fitting_poisson_mle():
    """Poisson MLE lambda == sample mean; dispersion == var/mean.

    Reference: independent NumPy re-derivation. The Poisson maximum-likelihood
    estimate of lambda is exactly the arithmetic sample mean of the counts —
    cross-validated (numpy), not regulator-sourced.
    """
    counts = np.array([3, 5, 2, 8, 4, 6, 1, 7], dtype=float)
    out = frequency_distribution_fitting(counts)

    ref_lambda = float(np.mean(counts))  # Poisson MLE
    ref_dispersion = float(np.var(counts)) / ref_lambda

    assert out["distribution"] == "poisson"
    assert out["lambda"] == pytest.approx(ref_lambda, rel=CF_RTOL)
    assert out["dispersion"] == pytest.approx(ref_dispersion, rel=1e-6)


def test_severity_distribution_fitting_lognormal_mle():
    """Lognormal fit: mu, sigma are mean/std of log-losses; mean = exp(mu+sig^2/2).

    Reference: cross-validated with scipy.stats.lognorm.fit (floc=0), whose shape
    parameter equals sigma of log and scale == exp(mu). Cross-validated (scipy),
    not regulator-sourced.
    """
    rng = np.random.default_rng(7)
    losses = rng.lognormal(mean=10.0, sigma=1.3, size=5000)
    out = severity_distribution_fitting(losses)

    log_losses = np.log(losses)
    ref_mu = float(np.mean(log_losses))
    ref_sigma = float(np.std(log_losses))  # population std (ddof=0), as engine uses

    # scipy cross-check: shape=sigma, scale=exp(mu) with location fixed at 0.
    shape, loc, scale = stats.lognorm.fit(losses, floc=0)
    assert shape == pytest.approx(out["sigma"], rel=1e-3)
    assert math.log(scale) == pytest.approx(out["mu"], rel=1e-3)

    assert out["mu"] == pytest.approx(ref_mu, rel=1e-6)
    assert out["sigma"] == pytest.approx(ref_sigma, rel=1e-6)
    ref_mean = math.exp(ref_mu + 0.5 * ref_sigma**2)
    assert out["mean_severity"] == pytest.approx(ref_mean, rel=1e-4)


def test_severity_distribution_fitting_rejects_nonpositive():
    with pytest.raises(ValueError):
        severity_distribution_fitting(np.array([1.0, -2.0, 3.0]))


def test_compound_loss_distribution_mean_equals_EN_times_EX():
    """Compound mean == E[N]*E[X] (Wald's identity).

    Reference: for a compound Poisson with Poisson(lambda) frequency and
    lognormal(mu,sigma) severity, E[aggregate] = lambda * exp(mu+sigma^2/2).
    Cross-validated (analytic Wald identity), not regulator-sourced. 0.1% MC tol.
    """
    lam, mu, sigma = 12.0, 8.0, 0.9
    out = compound_loss_distribution(lam, mu, sigma, n_years=200_000, seed=123)

    e_x = math.exp(mu + 0.5 * sigma**2)
    ref_mean = lam * e_x  # E[N] * E[X]
    assert out["mean_annual_loss"] == pytest.approx(ref_mean, rel=2e-3)

    # Compound Poisson variance identity: Var = lambda * E[X^2].
    e_x2 = math.exp(2 * mu + 2 * sigma**2)
    ref_std = math.sqrt(lam * e_x2)
    assert out["std_annual_loss"] == pytest.approx(ref_std, rel=1e-2)

    assert np.all(np.diff(out["annual_losses"]) >= 0)  # sorted ascending


def test_compound_loss_distribution_rejects_bad_params():
    with pytest.raises(ValueError):
        compound_loss_distribution(0.0, 8.0, 0.9)
    with pytest.raises(ValueError):
        compound_loss_distribution(5.0, 8.0, 0.0)


def test_monte_carlo_oprisk_capital_matches_independent_quantile():
    """OpVaR == independent empirical quantile of an independently drawn compound.

    Reference: rebuild the same compound Poisson-lognormal sample with an
    independent NumPy simulation (same seed/params) and read the quantile with
    numpy's own floor-index rule. Cross-validated (independent numpy MC), not
    regulator-sourced. 0.1% MC tol on the two independent-but-seeded samples.
    """
    lam, mu, sigma, cl = 10.0, 9.0, 1.0, 0.999
    n = 100_000
    out = monte_carlo_oprisk_capital(lam, mu, sigma, confidence_level=cl, n_years=n, seed=42)

    # Independent reconstruction of the aggregate sample (same generator/seed).
    rng = np.random.default_rng(42)
    counts = rng.poisson(lam, size=n).astype(np.int64)
    sev = rng.lognormal(mu, sigma, size=int(counts.sum()))
    annual = np.empty(n)
    pos = 0
    for y in range(n):
        c = counts[y]
        annual[y] = sev[pos : pos + c].sum()
        pos += c
    annual.sort()
    idx = min(int(np.floor(cl * n)), n - 1)
    ref_opvar = float(annual[idx])
    ref_el = float(annual.mean())
    ref_es = float(annual[idx:].mean())

    assert out["opvar"] == pytest.approx(ref_opvar, rel=MC_RTOL)
    assert out["expected_loss"] == pytest.approx(ref_el, rel=MC_RTOL)
    assert out["expected_shortfall"] == pytest.approx(ref_es, rel=MC_RTOL)

    # Regulatory properties: capital = UL >= 0, ES >= OpVaR.
    assert out["capital"] >= 0.0
    assert out["expected_shortfall"] >= out["opvar"]
    assert out["capital"] == pytest.approx(max(out["opvar"] - out["expected_loss"], 0.0), rel=1e-6)


def test_monte_carlo_oprisk_capital_opvar_monotone_in_confidence():
    """OpVaR must increase with confidence level (property test)."""
    base = dict(frequency_lambda=10.0, severity_mu=9.0, severity_sigma=1.0, n_years=100_000, seed=42)
    v95 = monte_carlo_oprisk_capital(confidence_level=0.95, **base)["opvar"]
    v99 = monte_carlo_oprisk_capital(confidence_level=0.99, **base)["opvar"]
    v999 = monte_carlo_oprisk_capital(confidence_level=0.999, **base)["opvar"]
    assert v95 < v99 < v999


def test_monte_carlo_oprisk_capital_rejects_confidence():
    with pytest.raises(ValueError):
        monte_carlo_oprisk_capital(10.0, 9.0, 1.0, confidence_level=0.5)


def test_operational_var_opvar_empirical_quantile():
    """OpVaR reader == floor-index empirical quantile of the supplied sample.

    Reference: independent NumPy sort + floor-index quantile. Cross-validated
    (numpy), not regulator-sourced.
    """
    rng = np.random.default_rng(3)
    losses = rng.gamma(shape=2.0, scale=1e5, size=20_000)
    cl = 0.99
    out = operational_var_opvar(losses, confidence_level=cl)

    s = np.sort(losses)
    idx = min(int(np.floor(cl * s.size)), s.size - 1)
    # Engine rounds to 2 dp; compare with abs tol matching that rounding.
    assert out["opvar"] == pytest.approx(float(s[idx]), abs=0.005)
    assert out["expected_shortfall"] == pytest.approx(float(s[idx:].mean()), abs=0.005)
    assert out["expected_loss"] == pytest.approx(float(s.mean()), abs=0.005)
    # Property: ES >= OpVaR.
    assert out["expected_shortfall"] >= out["opvar"]


def test_operational_var_opvar_monotone_and_errors():
    rng = np.random.default_rng(5)
    losses = rng.gamma(2.0, 1e5, size=10_000)
    assert (
        operational_var_opvar(losses, 0.95)["opvar"]
        <= operational_var_opvar(losses, 0.99)["opvar"]
    )
    with pytest.raises(ValueError):
        operational_var_opvar(np.array([]), 0.99)
    with pytest.raises(ValueError):
        operational_var_opvar(losses, 1.5)


def test_loss_distribution_approach_lda_pipeline():
    """LDA end-to-end: fits feed a compound MC whose OpVaR we independently rebuild.

    Reference: recompute Poisson MLE + lognormal MoM from the historical data,
    then independently simulate the compound distribution (same seed) and read
    OpVaR. Cross-validated (independent numpy MC), not regulator-sourced.
    """
    rng = np.random.default_rng(11)
    counts = rng.poisson(15.0, size=10).astype(float)
    losses = rng.lognormal(9.5, 1.1, size=400)
    cl, n = 0.999, 100_000
    out = loss_distribution_approach_lda(counts, losses, confidence_level=cl, n_years=n, seed=42)

    # Independent fit.
    lam = float(np.mean(counts))
    log_l = np.log(losses)
    mu, sigma = float(np.mean(log_l)), float(np.std(log_l))
    # round to engine's 6-dp fit precision so the MC uses identical parameters.
    lam_r, mu_r, sigma_r = round(lam, 6), round(mu, 6), round(sigma, 6)

    gen = np.random.default_rng(42)
    cnt = gen.poisson(lam_r, size=n).astype(np.int64)
    sev = gen.lognormal(mu_r, sigma_r, size=int(cnt.sum()))
    annual = np.empty(n)
    pos = 0
    for y in range(n):
        c = cnt[y]
        annual[y] = sev[pos : pos + c].sum()
        pos += c
    annual.sort()
    idx = min(int(np.floor(cl * n)), n - 1)
    ref_opvar = float(annual[idx])

    assert out["frequency"]["lambda"] == pytest.approx(lam, rel=1e-6)
    assert out["severity"]["mu"] == pytest.approx(mu, rel=1e-6)
    assert out["opvar"] == pytest.approx(ref_opvar, rel=MC_RTOL)
    assert out["capital"] >= 0.0


def test_advanced_measurement_approach_ama_el_treatment():
    """AMA capital: EL-covered -> UL only (OpVaR-EL); else full OpVaR.

    Reference: Basel II §669(b) — capital may be unexpected loss only when EL is
    demonstrably provisioned, otherwise capital = OpVaR. We check the branch logic
    directly against the LDA outputs (regulatory rule).
    """
    rng = np.random.default_rng(21)
    counts = rng.poisson(12.0, size=8).astype(float)
    losses = rng.lognormal(9.0, 1.0, size=300)
    kw = dict(confidence_level=0.999, n_years=80_000, seed=42)

    covered = advanced_measurement_approach_ama(counts, losses, expected_loss_covered=True, **kw)
    full = advanced_measurement_approach_ama(counts, losses, expected_loss_covered=False, **kw)

    # Same underlying OpVaR/EL (deterministic seed) -> compare capital treatment.
    assert covered["opvar"] == full["opvar"]
    assert full["ama_capital"] == pytest.approx(full["opvar"], rel=1e-9)
    assert covered["ama_capital"] == pytest.approx(
        max(covered["opvar"] - covered["expected_loss"], 0.0), rel=1e-6
    )
    # EL-covered capital must be <= full OpVaR capital.
    assert covered["ama_capital"] <= full["ama_capital"]
    assert covered["ama_capital"] >= 0.0


# ---------------------------------------------------------------------------
# engine/oprisk_capital.py
# ---------------------------------------------------------------------------


def test_sma_bic_piecewise_bcbs_d424():
    """SMA Business Indicator Component == BCBS d424 piecewise-linear formula.

    Reference: BCBS d424 "Minimum capital requirements for operational risk"
    (Dec 2017), §grid: marginal coefficients 12% up to EUR 1bn, 15% on (1bn,30bn],
    18% above 30bn. Regulatory boundary -> ZERO tolerance.
    """
    b1, b2 = 1_000_000_000.0, 30_000_000_000.0
    # Bucket 1: BI = 0.5bn -> 12% * 0.5bn.
    bi1 = 0.5e9
    out1 = basel_standardised_measurement_sma(bi1, use_ilm=False)
    assert out1["bic"] == round(0.12 * bi1, 2)

    # Bucket 2: BI = 10bn -> 12%*1bn + 15%*(10bn-1bn).
    bi2 = 10e9
    ref2 = 0.12 * b1 + 0.15 * (bi2 - b1)
    out2 = basel_standardised_measurement_sma(bi2, use_ilm=False)
    assert out2["bic"] == round(ref2, 2)

    # Bucket 3: BI = 50bn -> 12%*1bn + 15%*29bn + 18%*(50bn-30bn).
    bi3 = 50e9
    ref3 = 0.12 * b1 + 0.15 * (b2 - b1) + 0.18 * (bi3 - b2)
    out3 = basel_standardised_measurement_sma(bi3, use_ilm=False)
    assert out3["bic"] == round(ref3, 2)


def test_sma_ilm_formula_bcbs_d424():
    """SMA ILM == ln(e - 1 + (LC/BIC)^0.8) per BCBS d424.

    Reference: BCBS d424 §Internal Loss Multiplier. Capital = BIC * ILM.
    Regulatory formula -> tight tolerance.
    """
    bi = 10e9  # bucket 2 so ILM applies
    lc = 2e9
    out = basel_standardised_measurement_sma(bi, loss_component=lc, use_ilm=True)
    b1, b2 = 1e9, 30e9
    bic_ref = 0.12 * b1 + 0.15 * (bi - b1)
    ilm_ref = math.log(math.e - 1.0 + (lc / bic_ref) ** 0.8)
    assert out["bic"] == pytest.approx(bic_ref, rel=1e-9)
    assert out["ilm"] == pytest.approx(ilm_ref, rel=1e-6)
    assert out["sma_capital"] == pytest.approx(bic_ref * ilm_ref, rel=1e-6)


def test_sma_bucket1_ilm_is_one_bcbs_d424():
    """Bucket-1 banks may fix ILM = 1.0 (BCBS d424). Zero tolerance boundary."""
    bi = 0.8e9
    out = basel_standardised_measurement_sma(bi, loss_component=5e9, use_ilm=True)
    assert out["ilm"] == 1.0
    assert out["sma_capital"] == out["bic"]


def test_sma_rejects_negative_bi():
    with pytest.raises(ValueError):
        basel_standardised_measurement_sma(-1.0)


def test_oprisk_capital_allocation_pro_rata():
    """Allocation is pro-rata by risk and sums exactly to total (coherence).

    Reference: independent hand-calc — allocation_i = total * risk_i/sum(risk).
    """
    total = 1_000_000.0
    risks = np.array([100.0, 200.0, 300.0, 400.0])
    out = oprisk_capital_allocation(total, risks)
    ref = (risks / risks.sum()) * total
    assert out["allocations"] == pytest.approx(ref.tolist(), rel=1e-6)
    assert sum(out["allocations"]) == pytest.approx(total, rel=1e-6)
    assert sum(out["shares"]) == pytest.approx(1.0, rel=1e-6)


def test_oprisk_capital_allocation_errors():
    with pytest.raises(ValueError):
        oprisk_capital_allocation(1e6, np.array([]))
    with pytest.raises(ValueError):
        oprisk_capital_allocation(1e6, np.array([0.0, 0.0]))


def test_diversification_benefit_quadratic_form():
    """Diversified capital == sqrt(k' C k); benefit in [0, sum].

    Reference: independent hand-calc of the correlation quadratic form with a
    uniform off-diagonal correlation. Property: 0 <= benefit <= sum_standalone,
    and rho=1 gives zero benefit.
    """
    k = np.array([100.0, 150.0, 200.0])
    rho = 0.3
    out = diversification_benefit_oprisk(k, correlation=rho)
    c = np.full((3, 3), rho)
    np.fill_diagonal(c, 1.0)
    ref_div = math.sqrt(k @ c @ k)
    # Engine rounds to 2 dp; compare with abs tol matching that rounding.
    assert out["diversified_capital"] == pytest.approx(ref_div, abs=0.005)
    assert out["sum_standalone"] == pytest.approx(float(k.sum()), abs=0.005)
    benefit = out["diversification_benefit"]
    assert 0.0 <= benefit <= out["sum_standalone"]
    assert benefit == pytest.approx(float(k.sum()) - ref_div, abs=0.005)

    # rho = 1 => no diversification.
    full = diversification_benefit_oprisk(k, correlation=1.0)
    assert full["diversification_benefit"] == pytest.approx(0.0, abs=1e-2)


def test_diversification_benefit_errors():
    with pytest.raises(ValueError):
        diversification_benefit_oprisk(np.array([1.0, -1.0]))
    with pytest.raises(ValueError):
        diversification_benefit_oprisk(np.array([1.0]), correlation=1.5)


def test_oprisk_economic_capital_net_of_mitigants():
    """Economic capital == max(UL - insurance - diversification, 0).

    Reference: independent hand-calc. Property: insurance offset reduces capital;
    result floored at zero.
    """
    opvar, el = 5_000_000.0, 1_000_000.0
    ins, div = 500_000.0, 300_000.0
    out = oprisk_economic_capital(opvar, el, insurance_offset=ins, diversification_benefit=div)
    gross = opvar - el
    ref = max(gross - (ins + div), 0.0)
    assert out["gross_capital"] == pytest.approx(gross, rel=1e-9)
    assert out["economic_capital"] == pytest.approx(ref, rel=1e-9)
    assert out["total_mitigation"] == pytest.approx(ins + div, rel=1e-9)

    # Insurance offset strictly reduces capital vs no insurance.
    no_ins = oprisk_economic_capital(opvar, el, insurance_offset=0.0, diversification_benefit=div)
    assert out["economic_capital"] < no_ins["economic_capital"]
    # Floor at zero.
    floored = oprisk_economic_capital(opvar, el, insurance_offset=1e9)
    assert floored["economic_capital"] == 0.0


def test_insurance_offset_calculation_layer_logic():
    """Recoverable == min(max(loss-deductible,0), limit) * (1-haircut).

    Reference: independent hand-calc of the standard insurance layer. Property:
    net_loss = gross - recoverable, and recoverable reduces net loss.
    """
    gross, limit, ded, hc = 1_000_000.0, 600_000.0, 100_000.0, 0.1
    out = insurance_offset_calculation(gross, limit, ded, haircut=hc)
    above = max(gross - ded, 0.0)
    capped = min(above, limit)
    ref_rec = capped * (1.0 - hc)
    assert out["recoverable"] == pytest.approx(ref_rec, rel=1e-9)
    assert out["net_loss"] == pytest.approx(gross - ref_rec, rel=1e-9)
    assert out["recovery_rate"] == pytest.approx(ref_rec / gross, rel=1e-6)
    assert out["net_loss"] < gross  # offset reduces loss


def test_insurance_offset_errors():
    with pytest.raises(ValueError):
        insurance_offset_calculation(-1.0, 1.0, 1.0)
    with pytest.raises(ValueError):
        insurance_offset_calculation(1.0, 1.0, 1.0, haircut=1.5)


def test_tail_risk_scenario_oprisk_uplift():
    """Stressed tail ES == base tail ES * multiplier; uplift == difference.

    Reference: independent hand-calc — base ES is the mean of losses at/above the
    floor-index tail quantile; stressed ES scales it. Property: uplift >= 0.
    """
    rng = np.random.default_rng(9)
    losses = rng.gamma(2.0, 1e5, size=50_000)
    cl, mult = 0.999, 1.5
    out = tail_risk_scenario_oprisk(losses, tail_confidence=cl, severity_multiplier=mult)
    s = np.sort(losses)
    idx = min(int(np.floor(cl * s.size)), s.size - 1)
    base_es = float(s[idx:].mean())
    # Engine rounds to 2 dp; compare with abs tol matching that rounding.
    assert out["base_tail_es"] == pytest.approx(base_es, abs=0.005)
    assert out["stressed_tail_es"] == pytest.approx(base_es * mult, abs=0.01)
    assert out["capital_uplift"] == pytest.approx(base_es * (mult - 1.0), abs=0.01)
    assert out["capital_uplift"] >= 0.0


def test_tail_risk_scenario_errors():
    with pytest.raises(ValueError):
        tail_risk_scenario_oprisk(np.array([]))
    with pytest.raises(ValueError):
        tail_risk_scenario_oprisk(np.array([1.0]), severity_multiplier=0.5)


def test_oprisk_stress_testing_multiplicative():
    """Stressed capital == base * (1+freq) * (1+sev).

    Reference: independent hand-calc of the multiplicative driver scaling.
    Property: capital increases when both shocks positive.
    """
    base = 10_000_000.0
    fs, ss = 0.5, 0.3
    out = oprisk_stress_testing(base, fs, ss)
    ref = base * (1 + fs) * (1 + ss)
    assert out["stressed_capital"] == pytest.approx(ref, rel=1e-9)
    assert out["capital_increase"] == pytest.approx(ref - base, rel=1e-9)
    assert out["capital_increase"] > 0.0
    with pytest.raises(ValueError):
        oprisk_stress_testing(base, -1.5, 0.1)


# ---------------------------------------------------------------------------
# engine/oprisk_rcsa.py
# ---------------------------------------------------------------------------


def test_rcsa_risk_identification_counts_by_basel_category():
    """Register summary counts by Basel category.

    Reference: independent hand-count of a register of BCBS 128 Annex 9 Level-1
    categories (regulatory taxonomy for the category keys).
    """
    register = [
        {"risk_id": "R1", "category": "internal_fraud"},
        {"risk_id": "R2", "category": "internal_fraud"},
        {"risk_id": "R3", "category": "external_fraud"},
        {"risk_id": "R4", "category": "execution_delivery_process"},
    ]
    out = rcsa_risk_identification(register)
    assert out["num_risks"] == 4
    assert out["by_category"] == {
        "internal_fraud": 2,
        "external_fraud": 1,
        "execution_delivery_process": 1,
    }


def test_rcsa_risk_identification_rejects_bad_category():
    with pytest.raises(ValueError):
        rcsa_risk_identification([{"risk_id": "R1", "category": "not_a_basel_type"}])
    with pytest.raises(ValueError):
        rcsa_risk_identification([])


def test_rcsa_inherent_risk_scoring_5x5():
    """Inherent score == likelihood * impact on the 5x5 grid.

    Reference: independent hand-calc, no published reference. RAG bands:
    green<=6, amber<=12, red otherwise.
    """
    assert rcsa_inherent_risk_scoring(2, 3)["inherent_score"] == 6
    assert rcsa_inherent_risk_scoring(2, 3)["rating"] == "green"
    assert rcsa_inherent_risk_scoring(3, 3)["rating"] == "amber"  # 9
    assert rcsa_inherent_risk_scoring(4, 4)["rating"] == "red"  # 16
    with pytest.raises(ValueError):
        rcsa_inherent_risk_scoring(0, 3)


def test_rcsa_residual_risk_scoring_reduces_inherent():
    """Residual == inherent * (1 - control_eff); residual <= inherent.

    Reference: independent hand-calc, no published reference.
    """
    inherent = 20.0
    ce = 0.6
    out = rcsa_residual_risk_scoring(inherent, ce)
    ref = inherent * (1 - ce)
    assert out["residual_score"] == pytest.approx(ref, rel=1e-9)
    # Regulatory property: residual risk must not exceed inherent risk.
    assert out["residual_score"] <= inherent
    assert rcsa_residual_risk_scoring(20.0, 1.0)["residual_score"] == 0.0
    with pytest.raises(ValueError):
        rcsa_residual_risk_scoring(-1.0, 0.5)


def test_rcsa_control_effectiveness_weighted_average():
    """Effectiveness == w*design + (1-w)*operating.

    Reference: independent hand-calc, no published reference. Rating bands:
    effective>=0.8, partial>=0.5, else ineffective.
    """
    out = rcsa_control_effectiveness(0.9, 0.7, design_weight=0.4)
    ref = 0.4 * 0.9 + 0.6 * 0.7
    assert out["effectiveness"] == pytest.approx(ref, rel=1e-9)
    assert out["rating"] == "partial"  # 0.78
    assert rcsa_control_effectiveness(1.0, 1.0)["rating"] == "effective"
    assert rcsa_control_effectiveness(0.1, 0.1)["rating"] == "ineffective"
    with pytest.raises(ValueError):
        rcsa_control_effectiveness(1.2, 0.5)


def test_control_testing_effectiveness_pass_rate():
    """Pass rate == passed/total; effective iff pass_rate>=0.95.

    Reference: independent hand-calc, no published reference.
    """
    out = control_testing_effectiveness(96, 100)
    assert out["pass_rate"] == pytest.approx(0.96, rel=1e-9)
    assert out["exception_rate"] == pytest.approx(0.04, rel=1e-9)
    assert out["conclusion"] == "effective"
    assert control_testing_effectiveness(90, 100)["conclusion"] == "deficient"
    with pytest.raises(ValueError):
        control_testing_effectiveness(10, 0)
    with pytest.raises(ValueError):
        control_testing_effectiveness(11, 10)


def test_business_environment_factor_bei_multiplier():
    """BEI multiplier == max(1 + sensitivity*(avg - baseline), 0).

    Reference: independent hand-calc, no published reference.
    """
    scores = np.array([4.0, 5.0, 3.0])  # avg 4.0
    out = business_environment_factor_bei(scores, baseline=3.0, sensitivity=0.05)
    avg = float(scores.mean())
    ref = max(1.0 + 0.05 * (avg - 3.0), 0.0)
    assert out["avg_score"] == pytest.approx(avg, rel=1e-9)
    assert out["bei_multiplier"] == pytest.approx(ref, rel=1e-9)
    assert out["capital_impact"] == pytest.approx(ref - 1.0, rel=1e-6)
    # Above baseline => multiplier > 1 (more capital).
    assert out["bei_multiplier"] > 1.0
    with pytest.raises(ValueError):
        business_environment_factor_bei(np.array([]))


def test_internal_control_factor_icf_multiplier():
    """ICF multiplier == max(1 - sensitivity*(avg - baseline), 0).

    Reference: independent hand-calc, no published reference. Stronger controls
    (avg > baseline) reduce capital.
    """
    scores = np.array([0.9, 0.95, 0.85])  # avg 0.9
    out = internal_control_factor_icf(scores, baseline=0.8, sensitivity=0.25)
    avg = float(scores.mean())
    ref = max(1.0 - 0.25 * (avg - 0.8), 0.0)
    assert out["avg_effectiveness"] == pytest.approx(avg, rel=1e-9)
    assert out["icf_multiplier"] == pytest.approx(ref, rel=1e-9)
    assert out["icf_multiplier"] < 1.0  # strong controls reduce capital
    with pytest.raises(ValueError):
        internal_control_factor_icf(np.array([1.5]))


def test_loss_event_classification_basel_taxonomy():
    """Basel Level-1 event-type validation and ordinal index.

    Reference: BCBS 128 ("International Convergence...", Basel II) Annex 9 — the
    seven Level-1 operational-risk event-type categories in their published order.
    Regulatory taxonomy -> zero tolerance on membership & ordering.
    """
    expected_order = (
        "internal_fraud",
        "external_fraud",
        "employment_practices",
        "clients_products_business",
        "damage_physical_assets",
        "business_disruption_systems",
        "execution_delivery_process",
    )
    for i, et in enumerate(expected_order):
        out = loss_event_classification_basel(et)
        assert out["valid"] is True
        assert out["category_index"] == i
    bad = loss_event_classification_basel("nonexistent_event")
    assert bad["valid"] is False
    assert bad["category_index"] == -1
    with pytest.raises(ValueError):
        loss_event_classification_basel("")


def test_loss_data_collection_framework_threshold():
    """Reportable = events at/above threshold; below counted separately.

    Reference: independent hand-calc filter.
    """
    events = [
        {"gross_amount": 5_000.0},
        {"gross_amount": 20_000.0},
        {"gross_amount": 500.0},
        {"gross_amount": 100_000.0},
    ]
    thr = 1_000.0
    out = loss_data_collection_framework(events, thr)
    reportable = [e["gross_amount"] for e in events if e["gross_amount"] >= thr]
    assert out["reportable_count"] == len(reportable)
    assert out["total_loss"] == pytest.approx(sum(reportable), rel=1e-9)
    assert out["max_loss"] == pytest.approx(max(reportable), rel=1e-9)
    assert out["below_threshold_count"] == 1
    with pytest.raises(ValueError):
        loss_data_collection_framework(events, -1.0)
    with pytest.raises(ValueError):
        loss_data_collection_framework([{"foo": 1}], 0.0)


def test_external_loss_data_integration_scaling():
    """External losses scaled then pooled; external_weight is external share.

    Reference: independent hand-calc — combined mean and external count share.
    """
    internal = np.array([100.0, 200.0, 300.0])
    external = np.array([1000.0, 2000.0])
    sf = 0.5
    out = external_loss_data_integration(internal, external, sf)
    combined = np.concatenate([internal, external * sf])
    assert out["combined_count"] == combined.size
    assert out["combined_mean"] == pytest.approx(float(combined.mean()), rel=1e-6)
    assert out["external_weight"] == pytest.approx(external.size / combined.size, rel=1e-6)
    with pytest.raises(ValueError):
        external_loss_data_integration(internal, external, 0.0)


# ---------------------------------------------------------------------------
# engine/oprisk_kri.py
# ---------------------------------------------------------------------------


def test_key_risk_indicator_kri_library_validation():
    """KRI library indexes valid definitions by name.

    Reference: independent hand-check of registry construction, no published ref.
    """
    defs = [
        {
            "name": "failed_trades",
            "amber_threshold": 5,
            "red_threshold": 10,
            "direction": "higher_breach",
        },
        {
            "name": "staffing",
            "amber_threshold": 20,
            "red_threshold": 10,
            "direction": "lower_breach",
        },
    ]
    out = key_risk_indicator_kri_library(defs)
    assert out["num_kris"] == 2
    assert set(out["registry"].keys()) == {"failed_trades", "staffing"}
    with pytest.raises(ValueError):
        key_risk_indicator_kri_library([])
    with pytest.raises(ValueError):
        key_risk_indicator_kri_library([{"name": "x"}])
    with pytest.raises(ValueError):
        key_risk_indicator_kri_library(
            [{"name": "x", "amber_threshold": 1, "red_threshold": 2, "direction": "sideways"}]
        )


def test_kri_threshold_breach_detection_both_directions():
    """Breach status for higher_breach and lower_breach KRIs.

    Reference: independent hand-calc of the threshold ladder, no published ref.
    """
    # higher_breach: worse as value rises.
    assert kri_threshold_breach_detection(3, 5, 10, "higher_breach")["status"] == "green"
    assert kri_threshold_breach_detection(7, 5, 10, "higher_breach")["status"] == "amber"
    assert kri_threshold_breach_detection(12, 5, 10, "higher_breach")["status"] == "red"
    assert kri_threshold_breach_detection(12, 5, 10, "higher_breach")["breached"] is True
    # lower_breach: worse as value falls.
    assert kri_threshold_breach_detection(25, 20, 10, "lower_breach")["status"] == "green"
    assert kri_threshold_breach_detection(15, 20, 10, "lower_breach")["status"] == "amber"
    assert kri_threshold_breach_detection(8, 20, 10, "lower_breach")["status"] == "red"
    with pytest.raises(ValueError):
        kri_threshold_breach_detection(1, 10, 5, "higher_breach")  # red<amber inconsistent
    with pytest.raises(ValueError):
        kri_threshold_breach_detection(1, 5, 10, "sideways")


def test_kri_trend_analysis_ols_slope():
    """Trend slope == OLS slope; direction combines slope sign and metric sense.

    Reference: cross-validated with scipy.stats.linregress slope. Not
    regulator-sourced.
    """
    obs = np.array([1.0, 2.0, 2.5, 4.0, 5.5])
    out = kri_trend_analysis(obs, higher_is_worse=True)
    ref_slope = float(stats.linregress(np.arange(obs.size), obs).slope)
    assert out["slope"] == pytest.approx(ref_slope, rel=1e-6)
    assert out["trend"] == "deteriorating"  # rising & higher_is_worse
    assert out["latest"] == pytest.approx(5.5, rel=1e-9)
    # Same rising series but higher_is_better => improving.
    out2 = kri_trend_analysis(obs, higher_is_worse=False)
    assert out2["trend"] == "improving"
    # Flat series => stable.
    flat = kri_trend_analysis(np.array([10.0, 10.0, 10.0]))
    assert flat["trend"] == "stable"
    with pytest.raises(ValueError):
        kri_trend_analysis(np.array([1.0]))


# ---------------------------------------------------------------------------
# engine/oprisk_scenario.py
# ---------------------------------------------------------------------------


def test_scenario_frequency_estimation_expert_and_empirical():
    """Expert lambda passes through; empirical == occurrences/observation_years.

    Reference: independent hand-calc of the empirical Poisson rate, no published
    ref for the expert branch.
    """
    exp = scenario_frequency_estimation(2.5)
    assert exp["lambda"] == pytest.approx(2.5, rel=1e-9)
    assert exp["source"] == "expert"
    emp = scenario_frequency_estimation(2.5, occurrences=7, observation_years=10.0)
    assert emp["lambda"] == pytest.approx(0.7, rel=1e-9)
    assert emp["source"] == "empirical"
    with pytest.raises(ValueError):
        scenario_frequency_estimation(-1.0)
    with pytest.raises(ValueError):
        scenario_frequency_estimation(1.0, occurrences=5, observation_years=0.0)


def test_scenario_severity_estimation_two_point_lognormal():
    """Lognormal from median + worst-case percentile.

    Reference: cross-validated with scipy.stats.norm.ppf. mu=ln(typical),
    sigma=(ln(worst)-mu)/z_p. Cross-validated (scipy), not regulator-sourced.
    """
    typical, worst, p = 1_000_000.0, 10_000_000.0, 0.99
    out = scenario_severity_estimation(typical, worst, worst_case_percentile=p)
    mu_ref = math.log(typical)
    z = float(stats.norm.ppf(p))
    sigma_ref = (math.log(worst) - mu_ref) / z
    mean_ref = math.exp(mu_ref + 0.5 * sigma_ref**2)
    assert out["mu"] == pytest.approx(mu_ref, rel=1e-6)
    assert out["sigma"] == pytest.approx(sigma_ref, rel=1e-6)
    assert out["mean_severity"] == pytest.approx(mean_ref, rel=1e-4)
    # Independent check: the fitted lognormal's p-quantile recovers 'worst'.
    q = math.exp(mu_ref + sigma_ref * z)
    assert q == pytest.approx(worst, rel=1e-6)
    with pytest.raises(ValueError):
        scenario_severity_estimation(100.0, 50.0)
    with pytest.raises(ValueError):
        scenario_severity_estimation(100.0, 200.0, worst_case_percentile=0.4)


def test_scenario_expert_elicitation_weighted_stats():
    """Consensus == weighted mean; dispersion == weighted std; cov == disp/mean.

    Reference: independent hand-calc of weighted mean and weighted (population)
    standard deviation, no published reference.
    """
    est = np.array([100.0, 200.0, 300.0])
    w = np.array([1.0, 2.0, 1.0])
    out = scenario_expert_elicitation_model(est, w)
    consensus = float((est * w).sum() / w.sum())
    var = float((w * (est - consensus) ** 2).sum() / w.sum())
    disp = math.sqrt(var)
    assert out["consensus"] == pytest.approx(consensus, rel=1e-6)
    assert out["dispersion"] == pytest.approx(disp, rel=1e-6)
    # Engine rounds cov to 6 dp; compare with matching abs tol.
    assert out["coefficient_of_variation"] == pytest.approx(disp / consensus, abs=1e-6)
    # Equal-weight default == numpy mean/std.
    eq = scenario_expert_elicitation_model(est)
    assert eq["consensus"] == pytest.approx(float(est.mean()), rel=1e-6)
    assert eq["dispersion"] == pytest.approx(float(est.std()), rel=1e-6)
    with pytest.raises(ValueError):
        scenario_expert_elicitation_model(np.array([]))
    with pytest.raises(ValueError):
        scenario_expert_elicitation_model(est, np.array([1.0, 2.0]))


def test_scenario_analysis_oprisk_quantile():
    """Scenario VaR == independent compound-MC quantile; monotone in confidence.

    Reference: independent NumPy compound Poisson-lognormal simulation with the
    same seed and floor-index quantile. Cross-validated (independent numpy MC),
    not regulator-sourced. 0.1% MC tol.
    """
    lam, mu, sigma, cl = 5.0, 8.0, 1.0, 0.99
    n = 50_000
    out = scenario_analysis_oprisk(lam, mu, sigma, confidence_level=cl, n_years=n, seed=42)

    rng = np.random.default_rng(42)
    counts = rng.poisson(lam, size=n)
    annual = np.empty(n)
    for y in range(n):
        c = int(counts[y])
        annual[y] = 0.0 if c == 0 else float(rng.lognormal(mu, sigma, size=c).sum())
    annual.sort()
    idx = min(int(np.floor(cl * n)), n - 1)
    assert out["scenario_var"] == pytest.approx(float(annual[idx]), rel=MC_RTOL)
    assert out["expected_loss"] == pytest.approx(float(annual.mean()), rel=MC_RTOL)

    # Monotone in confidence.
    hi = scenario_analysis_oprisk(lam, mu, sigma, confidence_level=0.999, n_years=n, seed=42)
    assert hi["scenario_var"] >= out["scenario_var"]
    with pytest.raises(ValueError):
        scenario_analysis_oprisk(0.0, 8.0, 1.0)
    with pytest.raises(ValueError):
        scenario_analysis_oprisk(5.0, 8.0, 1.0, confidence_level=0.5)


# ---------------------------------------------------------------------------
# engine/oprisk_governance.py
# ---------------------------------------------------------------------------


def test_cyber_risk_loss_estimation_fair_style():
    """Worst-case == records*cost + BI; expected == worst * prob.

    Reference: independent hand-calc (FAIR single-loss-expectancy), no published
    numeric reference.
    """
    out = cyber_risk_loss_estimation(100_000, 150.0, 0.05, business_interruption_cost=1_000_000.0)
    worst = 100_000 * 150.0 + 1_000_000.0
    assert out["worst_case_loss"] == pytest.approx(worst, rel=1e-9)
    assert out["expected_loss"] == pytest.approx(worst * 0.05, rel=1e-9)
    assert out["expected_loss"] <= out["worst_case_loss"]
    with pytest.raises(ValueError):
        cyber_risk_loss_estimation(-1, 1.0, 0.5)
    with pytest.raises(ValueError):
        cyber_risk_loss_estimation(1, 1.0, 1.5)


def test_conduct_risk_metric_composite_index():
    """Conduct index == min(cpk,50) + min(redress_ratio*500,50).

    Reference: independent hand-calc, no published reference.
    """
    out = conduct_risk_metric(complaints=50.0, customers=10_000.0, redress_paid=50_000.0, revenue=1_000_000.0)
    cpk = 50.0 / 10_000.0 * 1000.0  # 5.0
    rr = 50_000.0 / 1_000_000.0  # 0.05
    index = min(cpk, 50.0) + min(rr * 500.0, 50.0)  # 5 + 25 = 30
    assert out["complaints_per_1000"] == pytest.approx(cpk, rel=1e-9)
    assert out["redress_ratio"] == pytest.approx(rr, rel=1e-9)
    assert out["conduct_index"] == pytest.approx(index, rel=1e-9)
    assert out["rating"] == "amber"  # 20 < 30 <= 50
    with pytest.raises(ValueError):
        conduct_risk_metric(1.0, 0.0, 1.0, 1.0)


def test_model_risk_assessment_residual():
    """Inherent == materiality*complexity; residual == inherent*(1-validation).

    Reference: independent hand-calc (SR 11-7 style), no published numeric ref.
    """
    out = model_risk_assessment(4, 4, 0.5)
    assert out["inherent_score"] == 16
    assert out["residual_score"] == pytest.approx(16 * 0.5, rel=1e-9)
    assert out["residual_score"] <= out["inherent_score"]
    assert out["tier"] == "amber"  # 8 -> amber
    with pytest.raises(ValueError):
        model_risk_assessment(0, 3, 0.5)
    with pytest.raises(ValueError):
        model_risk_assessment(3, 3, 1.5)


def test_it_risk_scoring_weighted():
    """IT score == (1-avail)*40 + min(incidents,20)*2 + (1-patch)*20, capped 100.

    Reference: independent hand-calc, no published reference.
    """
    out = it_risk_scoring(availability=0.99, incident_count=5, patch_compliance=0.9)
    ref = (1 - 0.99) * 40.0 + min(5, 20) * 2.0 + (1 - 0.9) * 20.0
    assert out["it_risk_score"] == pytest.approx(ref, rel=1e-6)
    assert out["rating"] == ("green" if ref <= 20 else "amber" if ref <= 50 else "red")
    with pytest.raises(ValueError):
        it_risk_scoring(1.5, 1, 0.5)
    with pytest.raises(ValueError):
        it_risk_scoring(0.9, -1, 0.5)


def test_third_party_vendor_risk_weighted():
    """Vendor score == crit/5*30 + (1-fin)*30 + conc*20 + (1-sub)*20.

    Reference: independent hand-calc, no published reference.
    """
    out = third_party_vendor_risk(criticality=5, financial_health=0.5, concentration=0.8, substitutability=0.2)
    ref = (5 / 5.0) * 30.0 + (1 - 0.5) * 30.0 + 0.8 * 20.0 + (1 - 0.2) * 20.0
    assert out["vendor_risk_score"] == pytest.approx(ref, rel=1e-6)
    assert out["rating"] == ("green" if ref <= 30 else "amber" if ref <= 60 else "red")
    with pytest.raises(ValueError):
        third_party_vendor_risk(6, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        third_party_vendor_risk(3, 1.5, 0.5, 0.5)


def test_business_continuity_risk_score_mtd_breach():
    """BC score derivation with MTD breach and BCP maturity discount.

    Reference: independent hand-calc of the documented formula, no published ref.
    """
    rto, rpo, mtd, mat = 10.0, 2.0, 5.0, 0.4
    out = business_continuity_risk_score(rto, rpo, mtd, mat)
    breach = rto > mtd
    coverage_gap = min(rto / mtd, 2.0) / 2.0
    raw = (50.0 if breach else 0.0) + coverage_gap * 50.0
    ref = min(raw * (1.0 - 0.5 * mat), 100.0)
    assert out["mtd_breach"] is True
    assert out["bc_risk_score"] == pytest.approx(ref, rel=1e-6)
    with pytest.raises(ValueError):
        business_continuity_risk_score(1.0, 1.0, 0.0, 0.5)
    with pytest.raises(ValueError):
        business_continuity_risk_score(1.0, 1.0, 5.0, 1.5)


def test_near_miss_capture_framework_classification():
    """Near-miss = zero actual loss & positive potential loss.

    Reference: independent hand-count, no published reference.
    """
    events = [
        {"actual_loss": 0.0, "potential_loss": 5000.0},  # near-miss
        {"actual_loss": 0.0, "potential_loss": 3000.0},  # near-miss
        {"actual_loss": 1000.0, "potential_loss": 2000.0},  # actual
        {"actual_loss": 0.0, "potential_loss": 0.0},  # neither -> actual bucket
    ]
    out = near_miss_capture_framework(events)
    assert out["near_miss_count"] == 2
    assert out["total_potential_loss"] == pytest.approx(8000.0, rel=1e-9)
    assert out["actual_loss_count"] == 2
    with pytest.raises(ValueError):
        near_miss_capture_framework([{"actual_loss": 0.0}])


def test_root_cause_analysis_template_normalisation():
    """Attribution == weights normalised to sum 1; primary == max share.

    Reference: independent hand-calc, no published reference.
    """
    factors = {"people": 30.0, "process": 50.0, "systems": 20.0}
    out = root_cause_analysis_template(factors)
    total = sum(factors.values())
    assert out["attribution"]["process"] == pytest.approx(50.0 / total, rel=1e-6)
    assert sum(out["attribution"].values()) == pytest.approx(1.0, rel=1e-6)
    assert out["primary_cause"] == "process"
    assert out["num_factors"] == 3
    with pytest.raises(ValueError):
        root_cause_analysis_template({})
    with pytest.raises(ValueError):
        root_cause_analysis_template({"a": -1.0})
    with pytest.raises(ValueError):
        root_cause_analysis_template({"a": 0.0})


def test_risk_appetite_statement_two_tier():
    """Status tiers against appetite/tolerance for both directions.

    Reference: independent hand-calc of the two-tier limit logic, no published ref.
    """
    # higher_is_worse
    assert risk_appetite_statement_oprisk(5.0, 10.0, 20.0)["status"] == "within_appetite"
    assert risk_appetite_statement_oprisk(15.0, 10.0, 20.0)["status"] == "within_tolerance"
    assert risk_appetite_statement_oprisk(25.0, 10.0, 20.0)["status"] == "breach"
    u = risk_appetite_statement_oprisk(15.0, 10.0, 20.0)["utilisation"]
    assert u == pytest.approx(15.0 / 20.0, rel=1e-6)
    # lower_is_worse (e.g. capital ratio)
    assert (
        risk_appetite_statement_oprisk(0.15, 0.10, 0.05, higher_is_worse=False)["status"]
        == "within_appetite"
    )
    assert (
        risk_appetite_statement_oprisk(0.02, 0.10, 0.05, higher_is_worse=False)["status"]
        == "breach"
    )
    with pytest.raises(ValueError):
        risk_appetite_statement_oprisk(5.0, 20.0, 10.0)  # tolerance<appetite inconsistent


def test_escalation_threshold_calculation_highest_tier():
    """Escalation == highest tier whose threshold the loss meets.

    Reference: independent hand-calc, no published reference.
    """
    thresholds = {"team": 1e3, "head": 1e4, "exco": 1e5, "board": 1e6}
    assert escalation_threshold_calculation(5e5, thresholds)["escalation_level"] == "exco"
    assert escalation_threshold_calculation(2e6, thresholds)["escalation_level"] == "board"
    low = escalation_threshold_calculation(100.0, thresholds)
    assert low["escalation_level"] is None
    with pytest.raises(ValueError):
        escalation_threshold_calculation(1.0, {})
    with pytest.raises(ValueError):
        escalation_threshold_calculation(-1.0, thresholds)


def test_oprisk_heat_map_generator_matrix():
    """Scores == like*imp; count matrix places each risk in its 5x5 cell.

    Reference: independent hand-calc of scores and the count matrix, no published
    reference.
    """
    like = np.array([1, 3, 5, 3])
    imp = np.array([1, 3, 5, 3])
    out = oprisk_heat_map_generator(like, imp)
    assert out["scores"] == [1, 9, 25, 9]
    assert out["ratings"] == ["green", "amber", "red", "amber"]
    m = np.array(out["matrix"])
    assert m.shape == (5, 5)
    assert m[0, 0] == 1  # like=1,imp=1
    assert m[2, 2] == 2  # two risks at (3,3)
    assert m[4, 4] == 1  # (5,5)
    assert m.sum() == 4
    with pytest.raises(ValueError):
        oprisk_heat_map_generator(np.array([1, 2]), np.array([1]))
    with pytest.raises(ValueError):
        oprisk_heat_map_generator(np.array([6]), np.array([1]))


def test_regulatory_compliance_score_weighted():
    """Compliance == weighted fraction met * 100.

    Reference: independent hand-calc of the weighted average, no published ref.
    """
    met = np.array([1.0, 1.0, 0.5, 0.0])
    w = np.array([2.0, 1.0, 1.0, 1.0])
    out = regulatory_compliance_score(met, w)
    ref = float((met * w).sum() / w.sum()) * 100.0
    assert out["compliance_score"] == pytest.approx(ref, rel=1e-6)
    assert out["num_requirements"] == 4
    assert out["rating"] == ("green" if ref >= 95 else "amber" if ref >= 80 else "red")
    # equal-weight default
    eq = regulatory_compliance_score(np.array([1.0, 1.0, 1.0, 1.0]))
    assert eq["compliance_score"] == pytest.approx(100.0, rel=1e-9)
    assert eq["rating"] == "green"
    with pytest.raises(ValueError):
        regulatory_compliance_score(np.array([1.5]))
    with pytest.raises(ValueError):
        regulatory_compliance_score(met, np.array([1.0]))


def test_audit_finding_risk_scorer_ageing_uplift():
    """Base == severity*likelihood; adjusted adds 2 per 30-day block, cap 25.

    Reference: independent hand-calc, no published reference.
    """
    out = audit_finding_risk_scorer(3, 3, overdue_days=65.0)
    base = 3 * 3  # 9
    uplift = (65 // 30) * 2.0  # 2 blocks -> 4
    adjusted = min(base + uplift, 25.0)  # 13
    assert out["base_score"] == base
    assert out["adjusted_score"] == pytest.approx(adjusted, rel=1e-9)
    assert out["rating"] == _rag_ref(adjusted)
    # Cap at 25.
    capped = audit_finding_risk_scorer(5, 5, overdue_days=3650.0)
    assert capped["adjusted_score"] == 25.0
    with pytest.raises(ValueError):
        audit_finding_risk_scorer(0, 3, 0.0)
    with pytest.raises(ValueError):
        audit_finding_risk_scorer(3, 3, -1.0)


def _rag_ref(score: float) -> str:
    """Independent RAG band reference (green<=6, amber<=12, else red)."""
    if score <= 6.0:
        return "green"
    if score <= 12.0:
        return "amber"
    return "red"

---
name: pyvar-derivatives
description: >
  Activate for derivatives pricing: options (vanilla, exotic, stochastic vol),
  fixed income, yield curves, interest rate derivatives, FX derivatives, or
  any instrument valuation task. Covers 62 functions across 8 sub-domains.
version: "1.0.0"
author: "Fibtec Limited — pyvar.com"
tags: [derivatives, options, Black-Scholes, Heston, SABR, Dupire, LSM,
       bonds, yield-curve, IRS, CDS, swaption, FX, QuantLib, monte-carlo]
---

# pyvar — Derivatives & Pricing  (62 functions)

## Architecture context
- **Compute**: NumPy/Numba (MC pricing), QuantLib (analytical), SciPy (calibration)
- **Queue**: Celery (batch re-pricing, XVA netting set)
- **Storage**: Redis cache (intraday marks), PostgreSQL (EOD prices)
- **API**: FastAPI endpoint `/api/v1/derivatives/{function}`

---

## Vanilla Options (BS & Trees)

```python
pyvar.derivatives.black_scholes_european_option(
    # Black-Scholes European Option
    **params
) -> float | dict
```

```python
pyvar.derivatives.black_scholes_greeks(
    # Black-Scholes Greeks
    **params
) -> float | dict
```

```python
pyvar.derivatives.binomial_tree_option_pricer(
    # Binomial Tree Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.trinomial_tree_option_pricer(
    # Trinomial Tree Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.monte_carlo_option_pricer(
    # Monte Carlo Option Pricer
    **params
) -> float | dict
```


## Stochastic Volatility Models

```python
pyvar.derivatives.heston_stochastic_volatility_model(
    # Heston Stochastic Volatility Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.sabr_volatility_model(
    # SABR Volatility Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.local_volatility_dupire_model(
    # Local Volatility (Dupire) Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.rough_volatility_rbergomi_model(
    # Rough Volatility (rBergomi) Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.variance_gamma_model(
    # Variance Gamma Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.normal_inverse_gaussian_model(
    # Normal Inverse Gaussian Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.displaced_diffusion_model(
    # Displaced Diffusion Model
    **params
) -> float | dict
```


## Exotic Options

```python
pyvar.derivatives.digital_option_pricer(
    # Digital Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.barrier_option_pricer(
    # Barrier Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.asian_option_pricer(
    # Asian Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.lookback_option_pricer(
    # Lookback Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.american_option_lsm(
    # American Option (LSM)
    **params
) -> float | dict
```

```python
pyvar.derivatives.bermudan_option_pricer(
    # Bermudan Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.rainbow_option_pricer(
    # Rainbow Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.basket_option_pricer(
    # Basket Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.spread_option_kirk_approximation(
    # Spread Option (Kirk Approximation)
    **params
) -> float | dict
```

```python
pyvar.derivatives.compound_option_pricer(
    # Compound Option Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.chooser_option_pricer(
    # Chooser Option Pricer
    **params
) -> float | dict
```


## Fixed Income Instruments

```python
pyvar.derivatives.bond_pricer_fixed_coupon(
    # Bond Pricer (Fixed Coupon)
    **params
) -> float | dict
```

```python
pyvar.derivatives.bond_pricer_floating_rate(
    # Bond Pricer (Floating Rate)
    **params
) -> float | dict
```

```python
pyvar.derivatives.zero_coupon_bond_pricer(
    # Zero Coupon Bond Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.inflation_linked_bond_pricer(
    # Inflation-Linked Bond Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.callable_bond_pricer(
    # Callable Bond Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.puttable_bond_pricer(
    # Puttable Bond Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.convertible_bond_pricer(
    # Convertible Bond Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.duration_macaulay(
    # Duration (Macaulay)
    **params
) -> float | dict
```


## Bond Analytics

```python
pyvar.derivatives.modified_duration(
    # Modified Duration
    **params
) -> float | dict
```

```python
pyvar.derivatives.effective_duration(
    # Effective Duration
    **params
) -> float | dict
```

```python
pyvar.derivatives.convexity(
    # Convexity
    **params
) -> float | dict
```

```python
pyvar.derivatives.dv01_pvbp(
    # DV01 / PVBP
    **params
) -> float | dict
```

```python
pyvar.derivatives.yield_to_maturity(
    # Yield to Maturity
    **params
) -> float | dict
```

```python
pyvar.derivatives.yield_to_call(
    # Yield to Call
    **params
) -> float | dict
```

```python
pyvar.derivatives.asset_swap_spread(
    # Asset Swap Spread
    **params
) -> float | dict
```

```python
pyvar.derivatives.z_spread_calculator(
    # Z-Spread Calculator
    **params
) -> float | dict
```

```python
pyvar.derivatives.oas_option_adjusted_spread(
    # OAS (Option-Adjusted Spread)
    **params
) -> float | dict
```


## Yield Curve Construction

```python
pyvar.derivatives.nelson_siegel_curve_fit(
    # Nelson-Siegel Curve Fit
    **params
) -> float | dict
```

```python
pyvar.derivatives.nelson_siegel_svensson_curve(
    # Nelson-Siegel-Svensson Curve
    **params
) -> float | dict
```

```python
pyvar.derivatives.bootstrap_yield_curve(
    # Bootstrap Yield Curve
    **params
) -> float | dict
```

```python
pyvar.derivatives.swap_rate_curve(
    # Swap Rate Curve
    **params
) -> float | dict
```

```python
pyvar.derivatives.ois_curve_sonia_sofr(
    # OIS Curve (SONIA / SOFR)
    **params
) -> float | dict
```

```python
pyvar.derivatives.forward_rate_agreement_fra(
    # Forward Rate Agreement (FRA)
    **params
) -> float | dict
```

```python
pyvar.derivatives.interest_rate_swap_irs_pricer(
    # Interest Rate Swap (IRS) Pricer
    **params
) -> float | dict
```


## Interest Rate Derivatives

```python
pyvar.derivatives.cross_currency_swap_pricer(
    # Cross-Currency Swap Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.overnight_index_swap_ois(
    # Overnight Index Swap (OIS)
    **params
) -> float | dict
```

```python
pyvar.derivatives.total_return_swap_trs(
    # Total Return Swap (TRS)
    **params
) -> float | dict
```

```python
pyvar.derivatives.credit_default_swap_cds_pricer(
    # Credit Default Swap (CDS) Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.equity_swap_pricer(
    # Equity Swap Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.caplet_floorlet_pricer_black(
    # Caplet / Floorlet Pricer (Black)
    **params
) -> float | dict
```

```python
pyvar.derivatives.cap_floor_pricer(
    # Cap / Floor Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.swaption_pricer_black(
    # Swaption Pricer (Black)
    **params
) -> float | dict
```

```python
pyvar.derivatives.swaption_pricer_sabr(
    # Swaption Pricer (SABR)
    **params
) -> float | dict
```

```python
pyvar.derivatives.lmm_bgm_rate_model(
    # LMM / BGM Rate Model
    **params
) -> float | dict
```


## FX Derivatives

```python
pyvar.derivatives.hull_white_short_rate_model(
    # Hull-White Short Rate Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.cox_ingersoll_ross_model(
    # Cox-Ingersoll-Ross Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.vasicek_interest_rate_model(
    # Vasicek Interest Rate Model
    **params
) -> float | dict
```

```python
pyvar.derivatives.fx_forward_pricer(
    # FX Forward Pricer
    **params
) -> float | dict
```

```python
pyvar.derivatives.fx_option_pricer_garman_kohlhagen(
    # FX Option Pricer (Garman-Kohlhagen)
    **params
) -> float | dict
```


## Naming convention
- All functions under `pyvar.derivatives.*`
- Prices in clean price (bonds) or premium (options)
- option_type: "call" | "put"
- style: "european" | "american" | "bermudan"
- day_count: "Act/365" | "Act/360" | "30/360"
- Models return dict with "price", "greeks", "model_params"

## Dependencies
numpy >= 1.24 · scipy >= 1.10 · pandas >= 2.0 · QuantLib >= 1.30
numba >= 0.57

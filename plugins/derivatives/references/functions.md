# pyvar Derivatives Pricing: parameter reference

Generated from `portal/functions.json` and the live OpenAPI schema by `scripts/sync_skills.py`: do not edit by hand. Every function is `POST /api/v1/derivatives/<name>` with a JSON body of the parameters below; `*` marks a required parameter.

## Vanilla Options (BS & Trees)

### black_scholes_european_option

`POST /api/v1/derivatives/black_scholes_european_option`: Black-Scholes-Merton price of a European option.

``Call = S e^{-qτ} N(d1) − K e^{-rτ} N(d2)``; the put follows by parity.
When ``tau == 0`` the intrinsic value is returned (zero-time limit) and when
``sigma == 0`` the discounted-forward intrinsic value is returned.

Formula (LaTeX): `C=S e^{-q\tau}N(d_1)-K e^{-r\tau}N(d_2),\qquad P=K e^{-r\tau}N(-d_2)-S e^{-q\tau}N(-d_1)\\d_1=\frac{\ln(S/K)+(r-q+\sigma^2/2)\tau}{\sigma\sqrt\tau},\qquad d_2=d_1-\sigma\sqrt\tau`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `div_yield` | `number` | `0.0` |  |

### black_scholes_greeks

`POST /api/v1/derivatives/black_scholes_greeks`: Closed-form Black-Scholes first-order Greeks.

Returns delta, gamma, vega, theta (per year) and rho. Gamma and vega are
identical for calls and puts.

Formula (LaTeX): `\Delta_{call}=e^{-q\tau}N(d_1),\quad \Delta_{put}=-e^{-q\tau}N(-d_1)\\\Gamma=\frac{e^{-q\tau}N'(d_1)}{S\sigma\sqrt\tau},\qquad \text{Vega}=S e^{-q\tau}N'(d_1)\sqrt\tau\quad(\text{same for call and put})\\\Theta_{call}=-\frac{S e^{-q\tau}N'(d_1)\sigma}{2\sqrt\tau}-rKe^{-r\tau}N(d_2)+qSe^{-q\tau}N(d_1),\quad \Theta_{put}=-\frac{S e^{-q\tau}N'(d_1)\sigma}{2\sqrt\tau}+rKe^{-r\tau}N(-d_2)-qSe^{-q\tau}N(-d_1)\\\rho_{call}=K\tau e^{-r\tau}N(d_2),\qquad \rho_{put}=-K\tau e^{-r\tau}N(-d_2)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `div_yield` | `number` | `0.0` |  |

### binomial_tree_option_pricer

`POST /api/v1/derivatives/binomial_tree_option_pricer`: Cox-Ross-Rubinstein binomial tree option price.

Handles European and American exercise. European prices converge to
Black-Scholes as ``n_steps`` grows.

Formula (LaTeX): `u=e^{\sigma\sqrt{\Delta t}},\quad d=\frac1u,\quad p=\frac{e^{(r-q)\Delta t}-d}{u-d}\\V_i^{(N)}=\max(\phi(S_0u^{N-i}d^{i}-K),0)\\V_i^{(k)}=\max\Big(e^{-r\Delta t}\big[pV_i^{(k+1)}+(1-p)V_{i+1}^{(k+1)}\big],\ \text{[American] intrinsic}(S_0u^{k-i}d^{i})\Big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_steps` | `integer` | `500` |  |
| `option_type` | `string` | `'call'` |  |
| `style` | `string` | `'european'` |  |
| `div_yield` | `number` | `0.0` |  |

### trinomial_tree_option_pricer

`POST /api/v1/derivatives/trinomial_tree_option_pricer`: Boyle trinomial tree option price.

Up/middle/down branching converges to Black-Scholes for European options.
Handles American exercise.

Formula (LaTeX): `dx=\sigma\sqrt{3\Delta t},\quad u=e^{dx},\quad \nu=r-q-\tfrac12\sigma^2\\p_u=\tfrac12\Big(\frac{\sigma^2\Delta t+\nu^2\Delta t^2}{dx^2}+\frac{\nu\Delta t}{dx}\Big),\quad p_d=\tfrac12\Big(\frac{\sigma^2\Delta t+\nu^2\Delta t^2}{dx^2}-\frac{\nu\Delta t}{dx}\Big),\quad p_m=1-p_u-p_d\\V_j^{(k)}=e^{-r\Delta t}\big(p_dV_j^{(k+1)}+p_mV_{j+1}^{(k+1)}+p_uV_{j+2}^{(k+1)}\big)\ \text{(+ American early-exercise check)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_steps` | `integer` | `300` |  |
| `option_type` | `string` | `'call'` |  |
| `style` | `string` | `'european'` |  |
| `div_yield` | `number` | `0.0` |  |

### monte_carlo_option_pricer

`POST /api/v1/derivatives/monte_carlo_option_pricer`: Monte Carlo price of a European option (terminal GBM payoff).

Randoms are pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3); the JIT kernel
only consumes the pre-drawn standard-normal array.

Formula (LaTeX): `S_T=S_0\exp\!\big[(r-q-\tfrac12\sigma^2)\tau+\sigma\sqrt\tau\,Z\big],\quad Z\sim N(0,1)\\\text{Price}=e^{-r\tau}\,\frac1N\sum_{i=1}^{N}\max(\phi(S_T^{(i)}-K),0)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `12345` |  |

## Stochastic Volatility Models

### heston_stochastic_volatility_model

`POST /api/v1/derivatives/heston_stochastic_volatility_model`: Heston stochastic-volatility European option price (semi-analytic).

Prices via the single-integral representation using the characteristic
function. As ``sigma`` (vol-of-vol) → 0 with ``v0 = theta`` the price tends
to Black-Scholes with constant vol ``sqrt(theta)``.

Formula (LaTeX): `C=S P_1-Ke^{-r\tau}P_2,\qquad P=C-S+Ke^{-r\tau}\ \text{(put-call parity)}\\P_1=\tfrac12+\frac{1}{\pi\,\phi(-i)}\int_0^\infty\text{Re}\Big[\frac{e^{-iu\ln K}\phi(u-i)}{iu}\Big]du,\qquad P_2=\tfrac12+\frac1\pi\int_0^\infty\text{Re}\Big[\frac{e^{-iu\ln K}\phi(u)}{iu}\Big]du\\\xi=\kappa-\sigma\rho i u,\ d=\sqrt{\xi^2+\sigma^2(iu+u^2)},\ g=\frac{\xi-d}{\xi+d}\\\phi(u)=\exp\!\Big[riu\tau+\frac{\kappa\theta}{\sigma^2}\big((\xi-d)\tau-2\ln\tfrac{1-ge^{-d\tau}}{1-g}\big)+\frac{\xi-d}{\sigma^2}\cdot\frac{1-e^{-d\tau}}{1-ge^{-d\tau}}\,v_0+iu\ln S\Big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `v0`* | `number` | required |  |
| `kappa`* | `number` | required |  |
| `theta`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `rho`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |

### sabr_volatility_model

`POST /api/v1/derivatives/sabr_volatility_model`: SABR implied (lognormal/Black) volatility via Hagan's expansion.

Returns the Black implied volatility for the given strike under the SABR
dynamics. At-the-money it reduces to the well-known ATM SABR vol.

Formula (LaTeX): `z=\frac{\nu}{\alpha}(FK)^{(1-\beta)/2}\ln\frac{F}{K},\qquad \chi(z)=\ln\!\left(\frac{\sqrt{1-2\rho z+z^2}+z-\rho}{1-\rho}\right)\\\sigma_B(K)=\frac{\alpha}{(FK)^{(1-\beta)/2}\Big[1+\frac{(1-\beta)^2}{24}\ln^2\frac{F}{K}+\frac{(1-\beta)^4}{1920}\ln^4\frac{F}{K}\Big]}\cdot\frac{z}{\chi(z)}\cdot\left[1+\left(\frac{(1-\beta)^2\alpha^2}{24(FK)^{1-\beta}}+\frac{\rho\beta\nu\alpha}{4(FK)^{(1-\beta)/2}}+\frac{2-3\rho^2}{24}\nu^2\right)\tau\right]\\\text{ATM }(F=K):\quad \sigma_B(F)=\frac{\alpha}{F^{1-\beta}}\left[1+\left(\frac{(1-\beta)^2\alpha^2}{24F^{2-2\beta}}+\frac{\rho\beta\nu\alpha}{4F^{1-\beta}}+\frac{2-3\rho^2}{24}\nu^2\right)\tau\right]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `forward`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `alpha`* | `number` | required |  |
| `beta`* | `number` | required |  |
| `rho`* | `number` | required |  |
| `nu`* | `number` | required |  |

### local_volatility_dupire_model

`POST /api/v1/derivatives/local_volatility_dupire_model`: Dupire local volatility surface from a call-price surface.

Uses finite differences of the Dupire equation
``σ_loc² = (∂C/∂T + r K ∂C/∂K) / (½ K² ∂²C/∂K²)`` on the supplied grid,
covering the FULL grid: central differences in strike at interior
points, one-sided (forward/backward) 2nd-order-accurate differences at
the two strike boundaries (exact non-uniform-grid Fornberg-style 3-point
stencils -- exact for any quadratic, verified against hand-differentiated
polynomials), and a forward/backward difference in maturity at the
first/last maturity respectively (interior maturities also use the
forward difference toward the next maturity).

Formula (LaTeX): `\sigma_{loc}^2(K,T)=\frac{\partial C/\partial T+rK\,\partial C/\partial K}{\tfrac12 K^2\,\partial^2C/\partial K^2}\\\text{interior}:\ \text{central differences};\quad \text{boundary}:\ \text{2nd-order one-sided 3-point stencils (exact for quadratics)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `strikes`* | `number[] or number[][]` | required |  |
| `maturities`* | `number[] or number[][]` | required |  |
| `call_surface`* | `number[] or number[][]` | required |  |
| `rate`* | `number` | required |  |
| `spot`* | `number` | required |  |

### rough_volatility_rbergomi_model

`POST /api/v1/derivatives/rough_volatility_rbergomi_model`: Rough Bergomi (rBergomi) European option price via Monte Carlo.

A rough-volatility model with Hurst exponent ``H < 0.5``. Randoms are
pre-drawn in pure Python (CLAUDE.md §3.1 RULE 3).

Three independent numerical-correctness bugs were fixed here (task #18,
found via the Tier 3 #2 test-reference audit and its follow-up
verification -- see _rbergomi_volterra_driver, _rbergomi_discrete_variance
and _rbergomi_paths' docstrings/comments for each in detail):

1. The fractional driver froze each increment's weight at the moment it
   was drawn instead of recomputing it (as a gap to the current time) at
   every later step -- right marginal variance, wrong autocovariance,
   invisible to any test that only checks a single time point.
2. The martingale correction used the CONTINUUM-limit variance
   (``t^(2H)``), which the naive discrete Riemann sum undershoots
   substantially at this model's default ``n_steps`` -- pulling
   ``E[var_t]`` well below ``xi``.
3. The variance applied to a given step's price shock was computed using
   that SAME step's own Brownian draw rather than a value predictable
   from strictly prior information -- correlating "random" volatility
   with the shock it should be independent of and breaking the
   risk-neutral drift (``E[S_T] != S0*exp(rT)``; put-call parity was off
   by more than 15, not a rounding-level miss).

Verified (not merely believed) via three checks the code lacked before:
an exact hand-computable impulse-response test on the fractional driver
(bug 1), an ``eta -> 0`` reduction to flat-vol Black-Scholes (bugs 2 & 3
together -- degenerate case has no vol-of-vol to expose either), and
put-call parity at the model's actual default parameters (bug 3
specifically, since parity holds regardless of how the volatility itself
is modelled).

Formula (LaTeX): `\widetilde W(t_k)=\sqrt{\Delta t}\sum_{j\le k}(t_k-t_j)^{H-1/2}Z^v_j\quad\text{(Volterra driver, gap-weighted)}\\v_{t_k}=\begin{cases}\xi & k=0\\ \xi\exp\!\Big(\eta\sqrt{2H}\,\widetilde W(t_{k-1})-\tfrac12\eta^2\,\text{Var}_{disc}(t_{k-1})\Big) & k>0\end{cases}\\dS/S=r\,dt+\sqrt{v_t}\,dW,\qquad dW=\rho\,dZ^v+\sqrt{1-\rho^2}\,dZ^s\\\text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(S_\tau-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `xi` | `number` | `0.04` |  |
| `eta` | `number` | `1.5` |  |
| `hurst` | `number` | `0.1` |  |
| `rho` | `number` | `-0.7` |  |
| `n_steps` | `integer` | `50` |  |
| `n_simulations` | `integer` | `50000` |  |
| `option_type` | `string` | `'call'` |  |
| `seed` | `integer` | `2024` |  |
| `control_variate` | `boolean` | `False` |  |
| `greeks` | `boolean` | `False` |  |

### variance_gamma_model

`POST /api/v1/derivatives/variance_gamma_model`: Variance Gamma European option price via Monte Carlo.

Note: the ``theta`` parameter here is the VG skew parameter
(subordinated-drift), unrelated to the Greek theta (time decay)
optionally returned when ``greeks=True``.

Time-changes Brownian motion by a Gamma subordinator (mean 1, variance
``nu``). The martingale drift correction ``omega`` is computed in closed
form so the discounted spot is a martingale.

Formula (LaTeX): `\omega=\frac1\nu\ln\big(1-\theta\nu-\tfrac12\sigma^2\nu\big)\\G\sim\text{Gamma}(\text{shape}=\tau/\nu,\ \text{scale}=\nu)\\\ln S_T=\ln S_0+(r+\omega)\tau+\theta G+\sigma\sqrt{G}\,Z\\\text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(S_T-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `sigma` | `number` | `0.2` |  |
| `theta` | `number` | `-0.1` |  |
| `nu` | `number` | `0.2` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `seed` | `integer` | `7` |  |
| `greeks` | `boolean` | `False` |  |

### normal_inverse_gaussian_model

`POST /api/v1/derivatives/normal_inverse_gaussian_model`: Normal Inverse Gaussian European option price via Monte Carlo.

NIG is Brownian motion subordinated by an inverse-Gaussian process. The
drift is corrected so the discounted spot is a martingale.

Formula (LaTeX): `\gamma=\sqrt{\alpha^2-\beta^2},\qquad \omega=\delta\big(\sqrt{\alpha^2-(\beta+1)^2}-\gamma\big)\\G\sim IG\Big(\mu=\frac{\delta\tau}{\gamma},\ \lambda=(\delta\tau)^2\Big)\\\ln S_T=\ln S_0+(r+\omega)\tau+\beta G+\sqrt{G}\,Z\\\text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(S_T-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `alpha` | `number` | `15.0` |  |
| `beta` | `number` | `-5.0` |  |
| `delta` | `number` | `0.5` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `seed` | `integer` | `11` |  |
| `greeks` | `boolean` | `False` |  |

### displaced_diffusion_model

`POST /api/v1/derivatives/displaced_diffusion_model`: Displaced-diffusion (shifted lognormal) European option price.

Prices ``(S + a)`` as a lognormal with vol scaled by ``S/(S+a)`` — a simple
way to interpolate between lognormal (a=0) and normal-like dynamics. Reduces
exactly to Black-Scholes when ``displacement == 0``.

Formula (LaTeX): `\text{Price}=\text{BS}(S+a,\ K+a,\ r,\ \sigma,\ \tau,\ q)\quad\text{(Black-Scholes on shifted spot/strike)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `displacement`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `div_yield` | `number` | `0.0` |  |

## Exotic Options

### digital_option_pricer

`POST /api/v1/derivatives/digital_option_pricer`: Cash-or-nothing digital (binary) option price.

``Call = payout · e^{-rτ} N(d2)``, ``Put = payout · e^{-rτ} N(-d2)``.

Formula (LaTeX): `\text{Call}=Q\,e^{-r\tau}N(d_2),\qquad \text{Put}=Q\,e^{-r\tau}N(-d_2),\qquad d_2=\frac{\ln(S/K)+(r-q-\sigma^2/2)\tau}{\sigma\sqrt\tau}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `payout` | `number` | `1.0` |  |
| `div_yield` | `number` | `0.0` |  |

### barrier_option_pricer

`POST /api/v1/derivatives/barrier_option_pricer`: Single-barrier option price (Reiner-Rubinstein closed form), with a

modelled rebate leg.

Uses the in-out parity ``knock-in + knock-out = vanilla`` for the *pure*
(no-rebate) option legs, so any of the four standard combinations is
supported. A nonzero ``rebate`` adds the standard Reiner-Rubinstein cash
rebate term on top of that pure leg: for a knock-in, the rebate is paid
at expiry if the barrier is never touched (the "E" term below); for a
knock-out, the rebate is paid at the moment the barrier is touched (the
"F" term below) -- the standard two rebate conventions (Haug, *The
Complete Guide to Option Pricing Formulas*, "Standard Barrier Options").

Note: only the general Reiner-Rubinstein building blocks (A/B/C/D) are
shown here — which combination prices the knock-in leg depends on
``option_type``, ``barrier_type``, and whether strike exceeds barrier.

Formula (LaTeX): `\mu=\frac{r-q-\sigma^2/2}{\sigma^2},\qquad \lambda=\sqrt{\mu^2+2r/\sigma^2}\\A=\phi Se^{-q\tau}N(\phi x_1)-\phi Ke^{-r\tau}N(\phi x_1-\phi\sigma\sqrt\tau)\\B=\phi Se^{-q\tau}N(\phi x_2)-\phi Ke^{-r\tau}N(\phi x_2-\phi\sigma\sqrt\tau)\\C=\phi Se^{-q\tau}\Big(\frac{H}{S}\Big)^{2(\mu+1)}N(\eta y_1)-\phi Ke^{-r\tau}\Big(\frac{H}{S}\Big)^{2\mu}N(\eta y_1-\eta\sigma\sqrt\tau)\\D=\phi Se^{-q\tau}\Big(\frac{H}{S}\Big)^{2(\mu+1)}N(\eta y_2)-\phi Ke^{-r\tau}\Big(\frac{H}{S}\Big)^{2\mu}N(\eta y_2-\eta\sigma\sqrt\tau)\\E=\text{rebate}\cdot e^{-r\tau}\big[N(\eta x_2-\eta\sigma\sqrt\tau)-(H/S)^{2\mu}N(\eta y_2-\eta\sigma\sqrt\tau)\big]\ \text{(rebate at expiry, knock-in)}\\F=\text{rebate}\big[(H/S)^{\mu+\lambda}N(\eta z)+(H/S)^{\mu-\lambda}N(\eta z-2\eta\lambda\sigma\sqrt\tau)\big]\ \text{(rebate at touch, knock-out)}\\\text{knock-in}=\{A,B,C,D\text{ combo}\}+E,\qquad \text{knock-out}=(\text{vanilla}-\text{knock-in}_{\text{no rebate}})+F`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `barrier`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `barrier_type` | `string` | `'down-and-out'` |  |
| `div_yield` | `number` | `0.0` |  |
| `rebate` | `number` | `0.0` |  |

### asian_option_pricer

`POST /api/v1/derivatives/asian_option_pricer`: Arithmetic-average Asian option price via Monte Carlo.

The averaging reduces volatility, so an Asian option is worth less than the
corresponding vanilla European option.

Formula (LaTeX): `\bar S=\frac1n\sum_{k=1}^n S_{t_k},\qquad S_{t_k}=S_0\exp\!\Big(\textstyle\sum_{j=1}^k\big[(r-q-\tfrac12\sigma^2)\Delta t+\sigma\sqrt{\Delta t}\,Z_j\big]\Big)\\ \text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(\bar S-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_steps` | `integer` | `100` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `average_type` | `string` | `'arithmetic'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `21` |  |
| `qmc` | `boolean` | `False` |  |
| `greeks` | `boolean` | `False` |  |

### lookback_option_pricer

`POST /api/v1/derivatives/lookback_option_pricer`: Lookback option price via Monte Carlo.

Floating-strike: call pays ``S_T − min`` (>= 0), put pays ``max − S_T``.
Fixed-strike: call pays ``max − K``, put pays ``K − min``. Always >= the
corresponding vanilla payoff.

Formula (LaTeX): `\text{Floating:}\ \text{Call}=e^{-r\tau}\mathbb E[S_T-S_{min}],\quad \text{Put}=e^{-r\tau}\mathbb E[S_{max}-S_T]\\ \text{Fixed:}\ \text{Call}=e^{-r\tau}\mathbb E[\max(S_{max}-K,0)],\quad \text{Put}=e^{-r\tau}\mathbb E[\max(K-S_{min},0)]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_steps` | `integer` | `100` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `strike_type` | `string` | `'floating'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `31` |  |
| `qmc` | `boolean` | `False` |  |
| `greeks` | `boolean` | `False` |  |

### american_option_lsm

`POST /api/v1/derivatives/american_option_lsm`: American option price via Longstaff-Schwartz Monte Carlo (LSM).

Allows early exercise at every time step. The price must be >= the European
price of the same option.

Note: the continuation value at each exercise date is fit by quadratic OLS
regression on in-the-money paths rather than evaluated from a closed-form
formula, and the opt-in Greeks use a spot bump roughly 30x larger than
this module's smooth-payoff pricers because that regression-based
exercise decision is discontinuous in spot.

Deliberately has no qmc option (task #15 Phase 2 evaluated and rejected
it for this function specifically -- see _price_by_qmc_replicates'
docstring). Randomized-QMC replicates work cleanly for asian_option_pricer
and lookback_option_pricer (simple path-average / path-extremum
estimators) but introduce a real, non-vanishing pricing bias here: LSM's
backward-induction step fits a cross-sectional OLS regression of
continuation value against in-the-money paths at each exercise date, and
that regression implicitly assumes the sampled points are independent.
Scrambled Sobol paths are deliberately correlated (that correlation is
exactly what gives QMC its variance reduction elsewhere), which biases
the regression fit and, through it, the exercise decision. Measured at
S=K=100, r=5%, sigma=20%, tau=1, n_steps=50 against a 200k-path plain-MC
reference (~6.024): plain MC at n_simulations=6,000/20,000 is biased by
only +0.03-0.04 (LSM's well-known small-sample low bias), while QMC
replicates at the same total budget were biased by +0.08 to +0.31
depending on replicate count/size -- shrinking as per-replicate path
count grows into the thousands, but not vanishing by n_simulations=20k
the way it does for Asian/lookback. Revisit only with a fix for the
underlying regression-bias interaction (e.g. an in-sample/out-of-sample
split for the regression fit), not by retuning replicate count alone.

Formula (LaTeX): `S_{t_k}=S_{t_{k-1}}\exp\!\big[(r-q-\tfrac12\sigma^2)\Delta t+\sigma\sqrt{\Delta t}\,Z_k\big],\ \Delta t=\tau/n \\\text{Intrinsic}(S)=\max(\phi(S-K),0) \\\hat C(S_{t_k})=\hat\beta_0+\hat\beta_1 S_{t_k}+\hat\beta_2 S_{t_k}^2\ \text{(OLS on in-the-money paths)}\\\text{Exercise at } t_k \text{ if Intrinsic}(S_{t_k})>\hat C(S_{t_k});\qquad \text{Price}=\mathbb E\big[e^{-r t}\,\text{Cashflow}\big]\ \text{(backward induction)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `n_steps` | `integer` | `50` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'put'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `41` |  |
| `greeks` | `boolean` | `False` |  |

### bermudan_option_pricer

`POST /api/v1/derivatives/bermudan_option_pricer`: Bermudan option price via LSM with discrete exercise dates.

Early exercise is allowed only on an evenly-spaced subset of the time grid.
Price lies between the European and American values.

Note: uses the same Longstaff-Schwartz regression-based exercise decision
as ``american_option_lsm`` (no closed form), restricted to an
evenly-spaced subset of roughly ``n_steps / exercise_dates`` grid points.

Formula (LaTeX): `\text{Same LSM recursion as american\_option\_lsm, restricted to } M \text{ discrete exercise dates:}\\\hat C(S_{t_k})=\hat\beta_0+\hat\beta_1S_{t_k}+\hat\beta_2S_{t_k}^2\ \text{(OLS, only at allowed } t_k),\\\text{Price}=\mathbb E\big[e^{-r t}\,\text{Cashflow}\big]\ \text{(backward induction)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `exercise_dates` | `integer` | `4` |  |
| `n_steps` | `integer` | `48` |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'put'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `51` |  |
| `greeks` | `boolean` | `False` |  |

### rainbow_option_pricer

`POST /api/v1/derivatives/rainbow_option_pricer`: Rainbow (best-of / worst-of) option price via Monte Carlo.

Payoff references the max (best-of) or min (worst-of) of the terminal asset
prices against the strike.

Formula (LaTeX): `S_{i,T}=S_{i,0}\exp\!\big[(r-\tfrac12\sigma_i^2)\tau+\sigma_i\sqrt\tau\,(LZ)_i\big]\\\text{ref}=\max_i S_{i,T}\ (\text{best-of})\ \text{ or }\ \min_i S_{i,T}\ (\text{worst-of})\\\text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(\text{ref}-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spots`* | `number[] or number[][]` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigmas`* | `number[] or number[][]` | required |  |
| `tau`* | `number` | required |  |
| `correlation`* | `number[] or number[][]` | required |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `rainbow_type` | `string` | `'best-of'` |  |
| `seed` | `integer` | `61` |  |
| `greeks` | `boolean` | `False` |  |

### basket_option_pricer

`POST /api/v1/derivatives/basket_option_pricer`: Basket option price via Monte Carlo on a weighted sum of assets.

Diversification means the basket option is worth no more than the weighted
sum of single-asset options.

Formula (LaTeX): `S_{i,T}=S_{i,0}\exp\!\big[(r-\tfrac12\sigma_i^2)\tau+\sigma_i\sqrt\tau\,(LZ)_i\big],\qquad \text{Basket}=\sum_i w_i S_{i,T}\\\text{Price}=e^{-r\tau}\,\mathbb E\big[\max(\phi(\text{Basket}-K),0)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spots`* | `number[] or number[][]` | required |  |
| `weights`* | `number[] or number[][]` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigmas`* | `number[] or number[][]` | required |  |
| `tau`* | `number` | required |  |
| `correlation`* | `number[] or number[][]` | required |  |
| `n_simulations` | `integer` | `100000` |  |
| `option_type` | `string` | `'call'` |  |
| `seed` | `integer` | `71` |  |
| `greeks` | `boolean` | `False` |  |

### spread_option_kirk_approximation

`POST /api/v1/derivatives/spread_option_kirk_approximation`: Spread option price via Kirk's approximation.

Prices an option on ``S1 − S2`` by reducing it to a Black-76 option on the
ratio with an effective volatility. Exact when ``strike == 0`` (Margrabe).
Inputs are treated as forwards (Black-76); the value is discounted once.

Formula (LaTeX): `\sigma_{eff}=\sqrt{\sigma_1^2-2\rho\sigma_1\sigma_2 r_2+(\sigma_2 r_2)^2},\qquad r_2=\frac{S_2}{S_2+K}\\d_1=\frac{\ln\frac{S_1}{S_2+K}+\tfrac12\sigma_{eff}^2\tau}{\sigma_{eff}\sqrt\tau},\qquad d_2=d_1-\sigma_{eff}\sqrt\tau\\\text{Call}=e^{-r\tau}\big[S_1N(d_1)-(S_2+K)N(d_2)\big]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot1`* | `number` | required |  |
| `spot2`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma1`* | `number` | required |  |
| `sigma2`* | `number` | required |  |
| `rho`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |

### compound_option_pricer

`POST /api/v1/derivatives/compound_option_pricer`: Compound option (option-on-option) price via the Geske (1979) closed form.

Supports the four standard compound types (call/put on call/put). See
``_geske_compound_price`` for the exact d-term algebra and its citation.

Formula (LaTeX): `I:\ V_{under}(I;K_2,\tau_u-\tau_c)=K_1\ \text{(critical price)}\\a_1=\frac{\ln(S/I)+(b+\sigma^2/2)\tau_c}{\sigma\sqrt{\tau_c}},\ a_2=a_1-\sigma\sqrt{\tau_c}\\b_1=\frac{\ln(S/K_2)+(b+\sigma^2/2)\tau_u}{\sigma\sqrt{\tau_u}},\ b_2=b_1-\sigma\sqrt{\tau_u},\quad \rho=\sqrt{\tau_c/\tau_u}\\\text{CallOnCall}=Se^{-q\tau_u}M(a_1,b_1;\rho)-K_2e^{-r\tau_u}M(a_2,b_2;\rho)-e^{-r\tau_c}K_1N(a_2)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike_underlying`* | `number` | required |  |
| `strike_compound`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau_compound`* | `number` | required |  |
| `tau_underlying`* | `number` | required |  |
| `n_simulations` | `integer` | `200000` |  |
| `compound_type` | `string` | `'call-on-call'` |  |
| `div_yield` | `number` | `0.0` |  |
| `seed` | `integer` | `81` |  |
| `greeks` | `boolean` | `False` |  |

### chooser_option_pricer

`POST /api/v1/derivatives/chooser_option_pricer`: Simple chooser option price (closed form).

At ``tau_choose`` the holder picks call or put (same strike/expiry). By
put-call parity the value is a call plus a put on a reduced-maturity
underlying: ``C(S,K,T) + P(S, K e^{-r(T-t)}·..., t)``. Worth at least the
more valuable of the embedded call and put.

Formula (LaTeX): `\text{Price}=C(S,K,\tau_e)+P\big(S,\;K e^{-(r-q)(\tau_e-\tau_c)},\;\tau_c\big)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau_choose`* | `number` | required |  |
| `tau_expiry`* | `number` | required |  |
| `div_yield` | `number` | `0.0` |  |

## Fixed Income Instruments

### bond_pricer_fixed_coupon

`POST /api/v1/derivatives/bond_pricer_fixed_coupon`: Price a fixed-coupon bond by discounting its cashflows at a flat yield.

Price falls as yield rises (inverse relationship), and equals par when the
coupon rate equals the yield.

Formula (LaTeX): `P=\sum_{i=1}^{n}\frac{F c_r/m}{(1+y/m)^{i}}+\frac{F}{(1+y/m)^{n}},\qquad n=\text{round}(T\cdot m)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `yield_rate`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### bond_pricer_floating_rate

`POST /api/v1/derivatives/bond_pricer_floating_rate`: Price a floating-rate note (FRN) from projected forward rates.

Each coupon is ``(reference_rate + spread) / frequency · face``. On a reset
date with discount rates equal to the reference rates, an FRN prices near
par plus the PV of the spread.

The coupon schedule actually priced is derived from
``len(reference_rates)`` (``discount_rates`` must match that length).
``maturity`` must be consistent with ``len(reference_rates) / frequency``
— a caller-supplied ``maturity`` that implies a different number of
periods is rejected rather than silently ignored.

Formula (LaTeX): `P=\sum_{i=1}^{n} CF_i\left(1+\frac{d_i}{m}\right)^{-i},\qquad CF_i=F\frac{r_i+s}{m}\ (\text{plus } F \text{ at } i=n)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `reference_rates`* | `number[] or number[][]` | required |  |
| `spread`* | `number` | required |  |
| `discount_rates`* | `number[] or number[][]` | required |  |
| `maturity`* | `number` | required |  |
| `frequency` | `integer` | `4` |  |

### zero_coupon_bond_pricer

`POST /api/v1/derivatives/zero_coupon_bond_pricer`: Price a zero-coupon bond: ``face / (1 + y/m)^{m·T}``.

Formula (LaTeX): `P=F\left(1+\frac{y}{m}\right)^{-mT}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `yield_rate`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### inflation_linked_bond_pricer

`POST /api/v1/derivatives/inflation_linked_bond_pricer`: Price an inflation-linked (real) bond with index-uplifted principal.

Coupons and principal accrete with cumulative inflation; the resulting
nominal cashflows are discounted at the real yield (the standard
real-cashflow / real-yield convention).

Formula (LaTeX): `P=\sum_{i=1}^{n}\left[\frac{F c_r}{m}(1+\pi)^{t_i}\right]\left(1+\frac{y_r}{m}\right)^{-i}+F(1+\pi)^{t_n}\left(1+\frac{y_r}{m}\right)^{-n},\qquad t_i=\frac{i}{m},\ n=\text{round}(T\cdot m)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `real_coupon_rate`* | `number` | required |  |
| `real_yield`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `inflation_rate`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### callable_bond_pricer

`POST /api/v1/derivatives/callable_bond_pricer`: Price a callable bond (issuer's option) on a short-rate binomial tree.

A callable bond is worth no more than the equivalent straight bond — the
embedded call belongs to the issuer.

Note: the short-rate tree is a simplified multiplicative lattice with
fixed 0.5/0.5 branch probabilities, not a Black-Derman-Toy tree calibrated
to an initial term structure, and the coupon is added at every node on
every step.

Formula (LaTeX): `V_j^{(N)}=F+c;\qquad V_j^{(k)}=\min\!\left(K_{call},\ c+e^{-r_{k,j}\,dt}\cdot\tfrac12\big(V_j^{(k+1)}+V_{j+1}^{(k+1)}\big)\right),\qquad r_{k,j}=r_0\,e^{\sigma_r\sqrt{dt}\,(2j-k)},\qquad \text{Price}=V_0^{(0)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `short_rate`* | `number` | required |  |
| `rate_vol`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `call_price`* | `number` | required |  |
| `frequency` | `integer` | `1` |  |

### puttable_bond_pricer

`POST /api/v1/derivatives/puttable_bond_pricer`: Price a puttable bond (holder's option) on a short-rate binomial tree.

A puttable bond is worth at least the equivalent straight bond — the
embedded put belongs to the holder.

Note: uses the same simplified multiplicative short-rate lattice as
``callable_bond_pricer`` — fixed 0.5/0.5 branch probabilities, not
calibrated to a market curve.

Formula (LaTeX): `V_j^{(N)}=F+c;\qquad V_j^{(k)}=\max\!\left(K_{put},\ c+e^{-r_{k,j}\,dt}\cdot\tfrac12\big(V_j^{(k+1)}+V_{j+1}^{(k+1)}\big)\right),\qquad r_{k,j}=r_0\,e^{\sigma_r\sqrt{dt}\,(2j-k)},\qquad \text{Price}=V_0^{(0)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `short_rate`* | `number` | required |  |
| `rate_vol`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `put_price`* | `number` | required |  |
| `frequency` | `integer` | `1` |  |

### convertible_bond_pricer

`POST /api/v1/derivatives/convertible_bond_pricer`: Price a convertible bond via the bond-floor + conversion-value maximum.

Value = max(straight bond floor, conversion value), a simple but standard
lower-bound decomposition. The convertible is always worth at least its
conversion value and at least its bond floor.

Note: this lower-bound decomposition does not model conversion
optionality, equity volatility, or embedded call/put features of a real
convertible bond.

Formula (LaTeX): `P=\max\big(P_{floor},\ \text{ratio}\cdot S\big),\qquad P_{floor}=\sum_{i=1}^{n}\frac{F c_r/m}{(1+y/m)^{i}}+\frac{F}{(1+y/m)^{n}},\quad n=\text{round}(T\cdot m)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `yield_rate`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `conversion_ratio`* | `number` | required |  |
| `stock_price`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

## Bond Analytics

### modified_duration

`POST /api/v1/derivatives/modified_duration`: Modified duration = Macaulay duration / (1 + y/m).

Approximates the percentage price change for a 1-unit yield move:
``ΔP/P ≈ −D_mod · Δy``.

Formula (LaTeX): `D_{mod}=\frac{D_{Mac}}{1+y/m},\qquad D_{Mac}=\frac{\sum_k t_k\, CF_k(1+y/m)^{-m t_k}}{\sum_k CF_k(1+y/m)^{-m t_k}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `yield_rate`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### effective_duration

`POST /api/v1/derivatives/effective_duration`: Effective duration from re-priced bond values under a parallel shock.

``D_eff = (P− − P+) / (2 · P0 · Δy)`` — model-agnostic, so it captures
embedded optionality (callable/puttable) that analytic duration misses.

Formula (LaTeX): `D_{eff}=\frac{P_- - P_+}{2\,P_0\,\Delta y}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `price_base`* | `number` | required |  |
| `price_up`* | `number` | required |  |
| `price_down`* | `number` | required |  |
| `yield_shock`* | `number` | required |  |

### convexity

`POST /api/v1/derivatives/convexity`: Bond convexity — the second-order yield sensitivity (always >= 0 for

option-free bonds).

``C = Σ cf_k · t_k(t_k + 1/m) · (1+y/m)^{-(m t_k + 2)} / P``.

Formula (LaTeX): `C=\frac{1}{P}\sum_k CF_k\, t_k\left(t_k+\frac{1}{m}\right)\left(1+\frac{y}{m}\right)^{-(m t_k+2)},\qquad P=\sum_k CF_k\left(1+\frac{y}{m}\right)^{-m t_k}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `yield_rate`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### dv01_pvbp

`POST /api/v1/derivatives/dv01_pvbp`: DV01 / PVBP — price change for a 1 basis-point yield move.

Computed by central difference of the price function at ±0.5bp.

Formula (LaTeX): `DV01=P(y-0.5\,\text{bp})-P(y+0.5\,\text{bp}),\quad \text{bp}=10^{-4},\qquad P(y)=\sum_k CF_k\left(1+\frac{y}{m}\right)^{-m t_k}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `yield_rate`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### yield_to_maturity

`POST /api/v1/derivatives/yield_to_maturity`: Yield to maturity — the flat rate that discounts cashflows to ``price``.

Solved by Brent root-finding. Recovers the input yield exactly when ``price``
was produced by :func:`engine.deriv_bonds.bond_pricer_fixed_coupon`.

Formula (LaTeX): `P=\sum_k CF_k\left(1+\frac{y}{m}\right)^{-m t_k},\quad \text{solved for } y=YTM`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `price`* | `number` | required |  |
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `frequency` | `integer` | `2` |  |

### yield_to_call

`POST /api/v1/derivatives/yield_to_call`: Yield to call — yield assuming redemption at the first call date.

Builds the cashflow stream truncated at ``call_date`` with redemption at
``call_price`` and solves for the yield.

Formula (LaTeX): `P=\sum_{i=1}^{n}\frac{F c_r/m}{(1+y_{tc}/m)^{i}}+\frac{K_{call}}{(1+y_{tc}/m)^{n}},\qquad n=\text{round}(T_{call}\cdot m),\ \text{solved for } y_{tc}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `price`* | `number` | required |  |
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `call_price`* | `number` | required |  |
| `call_date`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

### asset_swap_spread

`POST /api/v1/derivatives/asset_swap_spread`: Par-par asset-swap spread.

The spread equating the bond's net present value to an annuity of the
swap's fixed-leg PV01: ``ASW = (PV_bond − reference_price) / annuity``,
expressed in basis points.

By default (``use_market_price=False``), ``reference_price`` is
``face_value`` (par) — this reproduces the function's original,
par-referenced behaviour exactly and is unchanged for any existing
caller. Set ``use_market_price=True`` to use the bond's actual dirty
price instead, matching the standard market convention (O'Kane, 2000,
"Introduction to Asset Swaps", Lehman Brothers): the spread is only
equal to the par-referenced figure when the bond happens to trade at
par, so for any bond away from par the market-convention spread and
the par-referenced spread differ.

Formula (LaTeX): `ASW = \frac{PV_{bond} - R}{\text{Annuity}\cdot F},\qquad R = \begin{cases} F & \text{use\_market\_price=False (default)} \\ P_{bond} & \text{use\_market\_price=True} \end{cases},\qquad PV_{bond}=\sum_i CF_i\left(1+\frac{s_i}{m}\right)^{-m t_i},\qquad \text{Annuity}=\frac{1}{m}\sum_i\left(1+\frac{s_i}{m}\right)^{-m t_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `bond_price`* | `number` | required |  |
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `swap_rates`* | `number[] or number[][]` | required |  |
| `face_value` | `number` | `100.0` |  |
| `frequency` | `integer` | `2` |  |
| `use_market_price` | `boolean` | `False` |  |

### z_spread_calculator

`POST /api/v1/derivatives/z_spread_calculator`: Z-spread — constant spread over the zero curve that reprices the bond.

Solves for ``z`` such that ``Σ cf_k (1 + (zero_k + z)/m)^{-m t_k} = price``.

Formula (LaTeX): `P=\sum_k CF_k\left(1+\frac{z_{0,k}+z}{m}\right)^{-m t_k},\quad \text{solved for } z=Z_{spread}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `price`* | `number` | required |  |
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `zero_rates`* | `number[] or number[][]` | required |  |
| `frequency` | `integer` | `2` |  |

### oas_option_adjusted_spread

`POST /api/v1/derivatives/oas_option_adjusted_spread`: Option-adjusted spread of a callable bond.

Finds the constant spread added to the short rate on the pricing tree that
reprices the callable bond to its market price — stripping out the embedded
option so spreads are comparable across bonds.

Note: the spread is root-found (Brent's method) against
``callable_bond_pricer``'s tree price rather than expressed in closed
form — the equation above is the condition the solver satisfies, not an
explicit OAS formula.

Formula (LaTeX): `\text{Solve } s^{*} \text{ such that } P_{callable}\big(F,c_r,r_0+s^{*},\sigma_r,T,K_{call},m\big)=P_{market}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `market_price`* | `number` | required |  |
| `face_value`* | `number` | required |  |
| `coupon_rate`* | `number` | required |  |
| `short_rate`* | `number` | required |  |
| `rate_vol`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `call_price`* | `number` | required |  |
| `frequency` | `integer` | `1` |  |

### duration_macaulay

`POST /api/v1/derivatives/duration_macaulay`: Macaulay duration — PV-weighted average time to cashflows (in years).

Formula (LaTeX): `D_{Mac}=\frac{\sum_k t_k\, CF_k\left(1+\frac{y}{m}\right)^{-m t_k}}{\sum_k CF_k\left(1+\frac{y}{m}\right)^{-m t_k}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `cashflows`* | `number[] or number[][]` | required |  |
| `times`* | `number[] or number[][]` | required |  |
| `yield_rate`* | `number` | required |  |
| `frequency` | `integer` | `2` |  |

## Yield Curve Construction

### nelson_siegel_curve_fit

`POST /api/v1/derivatives/nelson_siegel_curve_fit`: Fit a Nelson-Siegel curve to observed yields.

Parameters: ``beta0`` (level), ``beta1`` (slope), ``beta2`` (curvature),
``tau`` (decay). ``beta0 + beta1`` is the instantaneous short rate and
``beta0`` is the asymptotic long rate.

Formula (LaTeX): `y(t)=\beta_0+\beta_1\frac{1-e^{-t/\tau}}{t/\tau}+\beta_2\left(\frac{1-e^{-t/\tau}}{t/\tau}-e^{-t/\tau}\right)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `maturities`* | `number[] or number[][]` | required |  |
| `yields`* | `number[] or number[][]` | required |  |
| `tau_init` | `number` | `1.5` |  |

### nelson_siegel_svensson_curve

`POST /api/v1/derivatives/nelson_siegel_svensson_curve`: Fit the Nelson-Siegel-Svensson (six-parameter) curve.

Adds a second curvature hump (``beta3``, ``tau2``) to Nelson-Siegel, giving
a closer fit to longer/more complex term structures.

Formula (LaTeX): `y(t)=\beta_0+\beta_1 f_1(t)+\beta_2\big(f_1(t)-e^{-t/\tau_1}\big)+\beta_3\big(f_2(t)-e^{-t/\tau_2}\big),\qquad f_i(t)=\frac{1-e^{-t/\tau_i}}{t/\tau_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `maturities`* | `number[] or number[][]` | required |  |
| `yields`* | `number[] or number[][]` | required |  |
| `tau1_init` | `number` | `1.5` |  |
| `tau2_init` | `number` | `8.0` |  |

### bootstrap_yield_curve

`POST /api/v1/derivatives/bootstrap_yield_curve`: Bootstrap zero (spot) rates from par-coupon bond rates.

Sequentially solves for each discount factor so each par bond prices to par,
then converts discount factors to continuously-compounded zero rates.

Formula (LaTeX): `DF_i=\frac{F-\sum_{j<i} c_i\,DF_j}{F+c_i},\qquad c_i=\frac{p_i F}{m},\qquad z_i=-\frac{\ln DF_i}{t_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `par_rates`* | `number[] or number[][]` | required |  |
| `maturities`* | `number[] or number[][]` | required |  |
| `frequency` | `integer` | `1` |  |
| `face_value` | `number` | `1.0` |  |

### swap_rate_curve

`POST /api/v1/derivatives/swap_rate_curve`: Par swap rates implied by a discount-factor curve.

For each tenor, ``swap_rate = (1 − DF(T)) / (Σ τ · DF)`` — the fixed rate
that makes a par swap have zero value.

Formula (LaTeX): `S_i=\frac{1-DF_i}{\sum_{j\le i}\tau\,DF_j},\qquad \tau=\frac1m`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `discount_factors`* | `number[] or number[][]` | required |  |
| `maturities`* | `number[] or number[][]` | required |  |
| `frequency` | `integer` | `1` |  |

### ois_curve_sonia_sofr

`POST /api/v1/derivatives/ois_curve_sonia_sofr`: Build an OIS (SONIA/SOFR) discount curve from quoted OIS swap rates.

OIS swaps pay annually against compounded overnight; the discount curve is
bootstrapped exactly as for par swaps (single-curve OIS-discounting).

Formula (LaTeX): `DF_i=\frac{1-r_i A_{i-1}}{1+r_i\tau},\qquad A_i=A_{i-1}+\tau\,DF_i,\qquad z_i=-\frac{\ln DF_i}{t_i},\qquad \tau=\frac1m`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `ois_rates`* | `number[] or number[][]` | required |  |
| `maturities`* | `number[] or number[][]` | required |  |
| `frequency` | `integer` | `1` |  |

## Swaps, Caps, Swaptions & Rate Models

### cross_currency_swap_pricer

`POST /api/v1/derivatives/cross_currency_swap_pricer`: Price a fixed-fixed cross-currency swap (with notional exchange).

Values each leg in its own currency (coupons + final notional), converts the
foreign leg at the FX spot, and nets. Pay-domestic = pay the domestic leg,
receive the foreign leg.

Formula (LaTeX): `PV_{dom}=N_d\Big(r_d\sum_i\tau_iDF_i^d+DF_n^d\Big),\qquad PV_{for}=N_f\Big(r_f\sum_i\tau_iDF_i^f+DF_n^f\Big)\\ V=\big(PV_{for}\cdot X-PV_{dom}\big)\ \text{[pay\_domestic]},\quad \text{or}\ \big(PV_{dom}-PV_{for}\cdot X\big)\ \text{otherwise}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional_dom`* | `number` | required |  |
| `notional_for`* | `number` | required |  |
| `fixed_rate_dom`* | `number` | required |  |
| `fixed_rate_for`* | `number` | required |  |
| `df_dom`* | `number[] or number[][]` | required |  |
| `df_for`* | `number[] or number[][]` | required |  |
| `accruals`* | `number[] or number[][]` | required |  |
| `fx_spot`* | `number` | required |  |
| `pay_domestic` | `boolean` | `True` |  |

### overnight_index_swap_ois

`POST /api/v1/derivatives/overnight_index_swap_ois`: Value a single-period overnight index swap.

Net cashflow = ``notional · (compounded_overnight − fixed) · accrual``,
discounted. Zero value when the compounded rate equals the fixed rate.

Formula (LaTeX): `V=N\,(r_{comp}-r_{fix})\,\tau\,DF`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `fixed_rate`* | `number` | required |  |
| `compounded_rate`* | `number` | required |  |
| `accrual`* | `number` | required |  |
| `discount_factor`* | `number` | required |  |
| `pay_fixed` | `boolean` | `True` |  |

### total_return_swap_trs

`POST /api/v1/derivatives/total_return_swap_trs`: Value a total-return swap leg.

The total-return receiver gets the asset's total return and pays a financing
rate (e.g. SOFR + spread): ``notional · (asset_return − financing·τ) · DF``.

Formula (LaTeX): `V=N\,(R_{asset}-r_{fin}\tau)\,DF`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `asset_return`* | `number` | required |  |
| `financing_rate`* | `number` | required |  |
| `accrual`* | `number` | required |  |
| `discount_factor`* | `number` | required |  |
| `receive_total_return` | `boolean` | `True` |  |

### credit_default_swap_cds_pricer

`POST /api/v1/derivatives/credit_default_swap_cds_pricer`: Price a CDS via a flat-hazard-rate reduced-form model with

accrual-midpoint default settlement.

Survival ``Q(t)=e^{−λt}``. Default losses -- and the accrued premium a
protection buyer owes if default falls inside a coupon period -- are
both settled at each period's ACCRUAL MIDPOINT
``t_mid,i = (t_{i−1}+t_i)/2``, discounted at ``DF(t_mid,i)``, following
the standard ISDA/JPMorgan reduced-form CDS convention also implemented
by QuantLib's ``MidPointCdsEngine`` (which settles the same way by
default: ``settlesAccrual=True``, ``paysAtDefaultTime=True`` --
confirmed by inspecting its NPV decomposition directly, since this is
exactly what ``tests/validation/test_derivatives_ref.py`` cross-checks
against). The regular coupon cashflow -- paid only while the name has
survived to the period end -- is unaffected: ``spread · τ · Σ DF(t_i) ·
Q(t_i)``.

Protection leg = ``(1−R) · Σ DF(t_mid,i) · (Q_{i−1} − Q_i)``.
Accrual-on-default rebate = ``spread · Σ (t_mid,i − t_{i−1}) ·
DF(t_mid,i) · (Q_{i−1} − Q_i)``, added to the premium leg. The par
spread zeroes the swap value.

Formula (LaTeX): `Q_i=e^{-\lambda t_i},\qquad DF_i=e^{-r t_i},\qquad t_i=\frac{i}{m},\ n=\text{round}(T\cdot m)\\t_{mid,i}=\tfrac12(t_{i-1}+t_i),\qquad DF_{mid,i}=e^{-r\,t_{mid,i}}\\\text{Protection leg}=(1-R)\,N\sum_i DF_{mid,i}(Q_{i-1}-Q_i)\\\text{Premium leg}=s\,N\Big[\tau\sum_i DF_i Q_i+\sum_i(t_{mid,i}-t_{i-1})\,DF_{mid,i}(Q_{i-1}-Q_i)\Big]\\\text{Value (buyer)}=\text{Protection}-\text{Premium}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `spread`* | `number` | required |  |
| `hazard_rate`* | `number` | required |  |
| `recovery_rate`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `discount_rate`* | `number` | required |  |
| `frequency` | `integer` | `4` |  |

### equity_swap_pricer

`POST /api/v1/derivatives/equity_swap_pricer`: Value an equity swap leg (equity return vs funding).

``notional · (equity_return − funding·τ) · DF`` to the equity receiver.

Formula (LaTeX): `V=N\,(R_{eq}-r_f\tau)\,DF`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `equity_return`* | `number` | required |  |
| `funding_rate`* | `number` | required |  |
| `accrual`* | `number` | required |  |
| `discount_factor`* | `number` | required |  |
| `receive_equity` | `boolean` | `True` |  |

### caplet_floorlet_pricer_black

`POST /api/v1/derivatives/caplet_floorlet_pricer_black`: Price a single caplet/floorlet under the Black (lognormal) model.

A caplet is a call on the forward rate; a floorlet is a put. Caplet +
floorlet (same strike) replicate a payer FRA (put-call parity).

Formula (LaTeX): `\text{Caplet}=N\,\tau\,DF\big[fN(d_1)-KN(d_2)\big],\qquad \text{Floorlet}=N\,\tau\,DF\big[KN(-d_2)-fN(-d_1)\big]\\d_1=\frac{\ln(f/K)+\tfrac12\sigma^2 T}{\sigma\sqrt T},\qquad d_2=d_1-\sigma\sqrt T`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `forward_rate`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `vol`* | `number` | required |  |
| `expiry`* | `number` | required |  |
| `accrual`* | `number` | required |  |
| `discount_factor`* | `number` | required |  |
| `option_type` | `string` | `'caplet'` |  |

### cap_floor_pricer

`POST /api/v1/derivatives/cap_floor_pricer`: Price an interest-rate cap/floor as a strip of caplets/floorlets.

Formula (LaTeX): `\text{Price}=\sum_i N\,\tau_i\,DF_i\big[f_iN(d_{1,i})-KN(d_{2,i})\big]\ (\text{cap; floorlet legs for a floor}),\\ d_{1,i}=\frac{\ln(f_i/K)+\tfrac12\sigma_i^2\tau_i^{exp}}{\sigma_i\sqrt{\tau_i^{exp}}},\quad d_{2,i}=d_{1,i}-\sigma_i\sqrt{\tau_i^{exp}}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `forward_rates`* | `number[] or number[][]` | required |  |
| `strike`* | `number` | required |  |
| `vols`* | `number[] or number[][]` | required |  |
| `expiries`* | `number[] or number[][]` | required |  |
| `accruals`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `option_type` | `string` | `'cap'` |  |

### swaption_pricer_black

`POST /api/v1/derivatives/swaption_pricer_black`: Price a European swaption under the Black model.

``Price = annuity · Black(forward_swap_rate, strike, vol, expiry)``. A payer
swaption is a call on the swap rate; a receiver swaption is a put.

Formula (LaTeX): `\text{Price}_{payer}=N\cdot A\cdot\big[FN(d_1)-KN(d_2)\big],\qquad \text{Price}_{receiver}=N\cdot A\cdot\big[KN(-d_2)-FN(-d_1)\big]\\d_1=\frac{\ln(F/K)+\tfrac12\sigma^2 T}{\sigma\sqrt T},\quad d_2=d_1-\sigma\sqrt T`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `forward_swap_rate`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `vol`* | `number` | required |  |
| `expiry`* | `number` | required |  |
| `annuity`* | `number` | required |  |
| `option_type` | `string` | `'payer'` |  |

### swaption_pricer_sabr

`POST /api/v1/derivatives/swaption_pricer_sabr`: Price a swaption using a SABR-implied Black volatility.

Computes the SABR lognormal vol for the (forward, strike, expiry) point via
Hagan's expansion, then plugs it into the Black swaption formula.

Formula (LaTeX): `\sigma_{SABR}=\text{Hagan}(F,K,T,\alpha,\beta,\rho,\nu)\ \text{(see sabr\_volatility\_model)}\\\text{Price}=N\cdot A\cdot\text{Black}(F,K,\sigma_{SABR},T)`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `forward_swap_rate`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `expiry`* | `number` | required |  |
| `annuity`* | `number` | required |  |
| `alpha`* | `number` | required |  |
| `beta`* | `number` | required |  |
| `rho`* | `number` | required |  |
| `nu`* | `number` | required |  |
| `option_type` | `string` | `'payer'` |  |

### lmm_bgm_rate_model

`POST /api/v1/derivatives/lmm_bgm_rate_model`: LIBOR Market Model (BGM) forward-rate Monte Carlo simulation.

Evolves a vector of forward LIBOR rates under the spot measure with the
standard log-normal BGM drift, discretised via the Glasserman-Zhao
predictor-corrector Euler scheme (see
``_lmm_terminal_rates_predictor_corrector``). Returns the mean terminal
forward curve; rates stay positive (log-normal dynamics).

The drift for rate ``i`` sums over ``j = 0..i`` inclusive (including rate
``i`` itself), evaluated from a single consistent rate vector at each of
the predictor and corrector stages -- not a sequential same-step
overwrite (see ``_lmm_terminal_rates_sequential_euler`` for the retained,
non-production former scheme).

Formula (LaTeX): `\mu_i(f)=\sum_{j\le i}\frac{\tau f_j\sigma_j\sigma_i}{1+\tau f_j}\\f_i^{pred}=f_i(t)\exp\!\left[(\mu_i(f(t))-\tfrac12\sigma_i^2)\Delta t+\sigma_i\sqrt{\Delta t}\,Z_i\right]\\f_i(t+\Delta t)=f_i(t)\exp\!\left[\Big(\tfrac12(\mu_i(f(t))+\mu_i(f^{pred}))-\tfrac12\sigma_i^2\Big)\Delta t+\sigma_i\sqrt{\Delta t}\,Z_i\right]`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `forward_rates`* | `number[] or number[][]` | required |  |
| `vols`* | `number[] or number[][]` | required |  |
| `tenor`* | `number` | required |  |
| `horizon`* | `number` | required |  |
| `n_steps` | `integer` | `20` |  |
| `n_simulations` | `integer` | `20000` |  |
| `seed` | `integer` | `104` |  |

### forward_rate_agreement_fra

`POST /api/v1/derivatives/forward_rate_agreement_fra`: Mark-to-market value of a forward rate agreement (long = pay fixed).

``Value = notional · (forward − fra_rate) · accrual · DF(end)``. Zero value
when the contracted FRA rate equals the projected forward.

Formula (LaTeX): `V=N\,(f-K)\,\tau\,DF,\qquad \tau=T_{end}-T_{start}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `fra_rate`* | `number` | required |  |
| `forward_rate`* | `number` | required |  |
| `start`* | `number` | required |  |
| `end`* | `number` | required |  |
| `discount_factor`* | `number` | required |  |

### interest_rate_swap_irs_pricer

`POST /api/v1/derivatives/interest_rate_swap_irs_pricer`: Price a vanilla fixed-vs-float interest-rate swap.

Float leg PV = ``notional · Σ fwd_i · τ_i · DF_i``; fixed leg PV =
``notional · fixed · Σ τ_i · DF_i``. Swap value to the payer is
``float − fixed``. The par (break-even) fixed rate is also returned.

Formula (LaTeX): `V=N\left(\sum_i f_i\tau_i DF_i-K\sum_i\tau_i DF_i\right),\qquad K_{par}=\frac{\sum_i f_i\tau_i DF_i}{\sum_i \tau_i DF_i}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `notional`* | `number` | required |  |
| `fixed_rate`* | `number` | required |  |
| `forward_rates`* | `number[] or number[][]` | required |  |
| `discount_factors`* | `number[] or number[][]` | required |  |
| `accruals`* | `number[] or number[][]` | required |  |
| `pay_fixed` | `boolean` | `True` |  |

## Short-Rate Models

### hull_white_short_rate_model

`POST /api/v1/derivatives/hull_white_short_rate_model`: Hull-White one-factor model with a constant mean-reversion level.

``dr = κ(θ−r)dt + σ dW`` — the extended-Vasicek form; with a constant θ the
closed-form ZCB price coincides with Vasicek. Returns the analytic bond
price and a Monte Carlo cross-check.

Note: with ``theta_const`` held constant this function literally delegates
to ``vasicek_interest_rate_model`` — it is not a genuine time-dependent
Hull-White model calibrated to fit an observed market forward curve.

Formula (LaTeX): `dr=\kappa(\theta-r)\,dt+\sigma\,dW,\qquad B=\frac{1-e^{-\kappa T}}{\kappa},\qquad A=\exp\!\Big[\big(\theta-\tfrac{\sigma^2}{2\kappa^2}\big)(B-T)-\tfrac{\sigma^2B^2}{4\kappa}\Big]\\P(0,T)=A\,e^{-Br_0}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `r0`* | `number` | required |  |
| `kappa`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `theta_const` | `number` | `0.03` |  |
| `n_steps` | `integer` | `100` |  |
| `n_simulations` | `integer` | `50000` |  |
| `seed` | `integer` | `103` |  |

### cox_ingersoll_ross_model

`POST /api/v1/derivatives/cox_ingersoll_ross_model`: CIR model: closed-form ZCB price + simulated (non-negative) short rate.

``dr = κ(θ−r)dt + σ√r dW``. The square-root diffusion keeps ``r >= 0``. The
Feller condition ``2κθ ≥ σ²`` guarantees strict positivity.

The Monte Carlo path uses the exact non-central chi-squared CIR
transition distribution (Broadie-Kaya / Glasserman §3.4;
``_cir_paths_exact_terminal``), not an Euler discretisation -- there is
no discretisation bias here at any ``n_steps``, unlike the (retained,
non-production) full-truncation Euler scheme in ``_cir_paths_euler``.

Formula (LaTeX): `\gamma=\sqrt{\kappa^2+2\sigma^2},\qquad B=\frac{2(e^{\gamma T}-1)}{(\gamma+\kappa)(e^{\gamma T}-1)+2\gamma}\\A=\left[\frac{2\gamma e^{(\kappa+\gamma)T/2}}{(\gamma+\kappa)(e^{\gamma T}-1)+2\gamma}\right]^{2\kappa\theta/\sigma^2},\qquad P(0,T)=A\,e^{-Br_0}\\c=\frac{\sigma^2(1-e^{-\kappa\,dt})}{4\kappa},\quad df=\frac{4\kappa\theta}{\sigma^2},\quad nc=\frac{r_t e^{-\kappa\,dt}}{c}\\r_{t+dt}=c\cdot\chi'^2(df,\,nc)\ \text{(exact CIR transition, Broadie-Kaya)}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `r0`* | `number` | required |  |
| `kappa`* | `number` | required |  |
| `theta`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `n_steps` | `integer` | `100` |  |
| `n_simulations` | `integer` | `50000` |  |
| `seed` | `integer` | `102` |  |

### vasicek_interest_rate_model

`POST /api/v1/derivatives/vasicek_interest_rate_model`: Vasicek model: closed-form zero-coupon bond price + simulated short rate.

``dr = κ(θ−r)dt + σ dW``. The affine ZCB price is ``P = A·e^{−B·r0}``. The
short rate is Gaussian (can go negative).

Formula (LaTeX): `dr=\kappa(\theta-r)\,dt+\sigma\,dW,\qquad B=\frac{1-e^{-\kappa T}}{\kappa},\qquad A=\exp\!\Big[\big(\theta-\tfrac{\sigma^2}{2\kappa^2}\big)(B-T)-\tfrac{\sigma^2B^2}{4\kappa}\Big]\\P(0,T)=A\,e^{-Br_0}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `r0`* | `number` | required |  |
| `kappa`* | `number` | required |  |
| `theta`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `maturity`* | `number` | required |  |
| `n_steps` | `integer` | `100` |  |
| `n_simulations` | `integer` | `50000` |  |
| `seed` | `integer` | `101` |  |

## FX Derivatives

### fx_forward_pricer

`POST /api/v1/derivatives/fx_forward_pricer`: FX forward rate and mark-to-market via covered interest-rate parity.

``F = S · e^{(r_dom − r_for)·τ}``. If a contracted forward is supplied, the
MtM value (domestic ccy) of a long-foreign position is
``notional · (F − contracted) · e^{−r_dom·τ}``.

Formula (LaTeX): `F=S\,e^{(r_d-r_f)\tau},\qquad V=N\,(F-K_{fwd})\,e^{-r_d\tau}`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `rate_domestic`* | `number` | required |  |
| `rate_foreign`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `notional` | `number` | `1.0` |  |
| `contracted_forward` | `number or null` | `None` |  |

### fx_option_pricer_garman_kohlhagen

`POST /api/v1/derivatives/fx_option_pricer_garman_kohlhagen`: Garman-Kohlhagen FX option price.

Black-Scholes with the foreign rate acting as a continuous dividend yield:
``Call = S e^{−r_for τ} N(d1) − K e^{−r_dom τ} N(d2)``. Satisfies FX
put-call parity ``C − P = S e^{−r_for τ} − K e^{−r_dom τ}``.

Formula (LaTeX): `C=S e^{-r_f\tau}N(d_1)-K e^{-r_d\tau}N(d_2),\qquad P=Ke^{-r_d\tau}N(-d_2)-Se^{-r_f\tau}N(-d_1)\\d_1=\frac{\ln(S/K)+(r_d-r_f+\sigma^2/2)\tau}{\sigma\sqrt\tau},\quad d_2=d_1-\sigma\sqrt\tau`

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `spot`* | `number` | required |  |
| `strike`* | `number` | required |  |
| `rate_domestic`* | `number` | required |  |
| `rate_foreign`* | `number` | required |  |
| `sigma`* | `number` | required |  |
| `tau`* | `number` | required |  |
| `option_type` | `string` | `'call'` |  |
| `notional` | `number` | `1.0` |  |

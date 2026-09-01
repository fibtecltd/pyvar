# pyvar-jupyter

`%pyvar` / `%%pyvar` IPython magics and rich HTML display for
[pyvar.com](https://www.pyvar.com)'s risk computation API. Built on top of
[`pyvar-client`](https://pypi.org/project/pyvar-client/) — this package adds
the notebook-ergonomics layer, not a second API client.

## Install

```bash
pip install pyvar-jupyter
```

Installs `pyvar-client` as a dependency automatically.

## Quick start

```python
%load_ext pyvar_jupyter
%pyvar_key eyJ...          # or export PYVAR_API_KEY before starting the kernel

%pyvar market_risk.historical_simulation_var returns=[0.01,-0.02,0.015] portfolio_value=1000000
```

The result renders as a formatted HTML table in the cell output, and is also
returned to `Out[]` — `result["var_abs"]` works on it directly.

## Line magic

Params as space-separated `key=value` tokens, each parsed with
`ast.literal_eval` (so numbers, lists, dicts, booleans, `None` all come
through as their real Python type, not strings). `var.compute` is the one
async function in the whole API (submit + poll, blocking until done) — see
`pyvar_client`'s own `VarNamespace` docstring for why it's handled specially:

```python
%pyvar var.compute returns=[0.01,-0.02,0.015] \
    portfolio_value=1000000 confidence_level=0.99 n_simulations=100000
```

## Cell magic

Same dispatch, params as a JSON object in the cell body — use this over the
line form once params get large or nested (arrays of arrays, nested
objects):

```python
%%pyvar derivatives.heston_stochastic_volatility_model
{
  "spot": 100.0,
  "strike": 105.0,
  "rate": 0.02,
  "tau": 1.0,
  "v0": 0.04,
  "kappa": 2.0,
  "theta": 0.04,
  "sigma": 0.3,
  "rho": -0.7,
  "option_type": "call"
}
```

## No params → discoverability

Calling either form with no parameters prints the function's docstring and
signature instead of making a doomed API call with zero fields — the same
convention `pyvar`'s own CLI uses:

```python
%pyvar market_risk.historical_simulation_var
```
```
historical_simulation_var(*, returns: 'list[float] | list[list[float]]', portfolio_value: 'float', confidence_level: 'float' = 0.99) -> 'dict[str, Any]'

Non-parametric Historical Simulation VaR.

Re-prices the portfolio under each observed historical return and reads the
empirical loss quantile — making no distributional assumption.

Returns:
    The raw API response as a dict.
```

## Display helper (no magics required)

`pyvar_jupyter.show()` wraps any `pyvar_client` result for the same rich
HTML rendering — useful in a loop or a script cell where you're calling
`Client` directly rather than through a magic:

```python
from pyvar_client import Client
import pyvar_jupyter

client = Client(api_key="eyJ...")
result = client.market_risk.historical_simulation_var(
    returns=[0.01, -0.02, 0.015], portfolio_value=1_000_000,
)
pyvar_jupyter.show(result)
```

The wrapped object still behaves like the underlying dict — `result["var_abs"]`,
`.get(...)`, iteration — `show()` only changes how it *renders*.

**Not in v1**: LaTeX formula rendering (the portal's KaTeX treatment,
`portal/pyvar.js`'s `_renderFormula`). That metadata lives in
`portal/functions.json` server-side and isn't exposed through the REST API or
`pyvar_client` yet — pulling it in here would mean either a new network call
per result or a second embedded copy that can drift from the real one. Left
for a follow-up once that metadata has a real client-facing source.

## Session config magics

```python
%pyvar_key eyJ...              # set/replace the API key for this kernel (in-memory only)
%pyvar_base_url http://localhost:8000   # point at a local/dev deployment instead of prod
```

Neither is required if `PYVAR_API_KEY` / `PYVAR_API_BASE_URL` are already set
as environment variables before the kernel starts — same variable names
`pyvar-client`'s own CLI and the `pyvar-mcp` plugin use.

## Examples

Worked notebooks in [`examples/`](examples/):

- [`01_portfolio_var.ipynb`](examples/01_portfolio_var.ipynb) — Monte Carlo
  VaR/CVaR on a synthetic portfolio
- [`02_basel_backtest.ipynb`](examples/02_basel_backtest.ipynb) — Basel
  traffic-light backtest (Kupiec/Christoffersen)
- [`03_derivatives_greeks.ipynb`](examples/03_derivatives_greeks.ipynb) —
  an exotic option pricer with bump-and-reprice Greeks

## Development

```bash
pip install -e ".[dev]"
pytest -v --cov=pyvar_jupyter --cov-report=term-missing
```

No real HTTP calls in the test suite — `httpx.MockTransport` intercepts every
request at the transport layer, same rule `pyvar-client`'s own tests follow.

## License

Apache-2.0. See [LICENSE](LICENSE).

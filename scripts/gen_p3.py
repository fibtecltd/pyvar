"""
scripts/gen_p3.py — P3 route/schema generator.

Introspects every public engine function and emits, per API domain:
  - schemas/{domain}.py   Pydantic v2 Request/Response models
  - api/routes/{domain}.py FastAPI synchronous route handlers

Design decisions (see CLAUDE.md):
  - Engine is the single source of truth. The API layer contains NO business
    logic — it validates input, converts list payloads to NumPy arrays, calls
    the engine wrapper, and serialises the result dict via OrjsonResponse.
  - Routes are synchronous: the analytical engine functions are sub-millisecond
    to low-millisecond. The async Celery+poll pattern (api/routes/var.py) is
    reserved for heavy Monte Carlo (run_monte_carlo_var) and stays untouched.
  - Request models are precisely typed from the engine signature; this is where
    regulatory validators (CLAUDE.md s4.1 confidence levels) are enforced.
  - Response models document the engine return-dict keys (extra='allow' covers
    keys built dynamically that static analysis cannot see). The handler returns
    OrjsonResponse(content=result) directly, so FastAPI skips re-encoding and
    orjson's OPT_SERIALIZE_NUMPY handles any residual NumPy values.

Run:  python scripts/gen_p3.py
"""

from __future__ import annotations

import ast
import importlib
import inspect
import keyword
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# ── Domain → engine module mapping (by module prefix) ───────────────────────────
DOMAINS: dict[str, list[str]] = {
    "market-risk": [
        "montecarlo",
        "var_models",
        "expected_shortfall",
        "stress",
        "greeks",
        "pnl_attribution",
        "backtesting",
        "volatility",
        "frtb",
        "metrics",
    ],
    "credit-risk": [
        "credit_pd_lgd",
        "credit_capital",
        "credit_var",
        "credit_ccr",
        "credit_xva",
        "credit_cds",
        "credit_ifrs9",
        "credit_scoring",
    ],
    "liquidity": [
        "liquidity_ratios",
        "liquidity_cashflow",
        "liquidity_stress",
        "liquidity_funding",
        "liquidity_internal",
    ],
    "operational": [
        "oprisk_lda",
        "oprisk_capital",
        "oprisk_rcsa",
        "oprisk_kri",
        "oprisk_scenario",
        "oprisk_governance",
    ],
    "portfolio": [
        "portfolio_optimisation",
        "portfolio_ratios",
        "portfolio_drawdown",
        "portfolio_attribution",
        "portfolio_factor",
        "portfolio_risk",
        "portfolio_esg",
    ],
    "regulatory": ["reg_basel_capital", "reg_frtb", "reg_mifid_emir", "reg_solvency"],
    "derivatives": [
        "deriv_options_vanilla",
        "deriv_options_exotic",
        "deriv_bonds",
        "deriv_bond_analytics",
        "deriv_curves",
        "deriv_rates",
        "deriv_short_rate",
        "deriv_stoch_vol",
        "deriv_fx",
    ],
    "alm": ["alm_duration", "alm_nii_eve", "alm_irrbb", "alm_behavioural", "alm_ftp"],
}

# Math helpers / already-routed functions to exclude from the public API surface.
EXCLUDE: set[str] = {
    "norm_cdf",
    "norm_pdf",  # deriv_options_vanilla numerical helpers
    "economic_value_helper",  # alm_irrbb internal helper
    "run_monte_carlo_var",  # already exposed via api/routes/var.py
}


def _class_name(func_name: str) -> str:
    """snake_case engine name → PascalCase schema stem."""
    return "".join(p.capitalize() for p in func_name.split("_"))


def _py_type_and_conv(ann: str) -> tuple[str, str]:
    """Map an engine annotation source string → (pydantic type, conversion kind).

    Conversion kinds applied in the route handler:
      ""           pass through unchanged
      "array"      np.asarray(v, float)            (np.ndarray)
      "array_opt"  convert only when not None      (np.ndarray | None)
      "tuple"      tuple(v)                         (tuple[float, ...])
      "maybe_arr"  np.asarray if list else scalar  (float | np.ndarray)
    """
    a = ann.replace(" ", "")
    table = {
        "np.ndarray": ("list[float] | list[list[float]]", "array"),
        "np.ndarray|None": ("list[float] | list[list[float]] | None", "array_opt"),
        "float": ("float", ""),
        "int": ("int", ""),
        "str": ("str", ""),
        "bool": ("bool", ""),
        "float|None": ("float | None", ""),
        "int|None": ("int | None", ""),
        "str|None": ("str | None", ""),
        "bool|None": ("bool | None", ""),
        "list[str]": ("list[str]", ""),
        "list[str]|None": ("list[str] | None", ""),
        "list[float]": ("list[float]", ""),
        "list[float]|None": ("list[float] | None", ""),
        "list[dict]": ("list[dict[str, Any]]", ""),
        "list[list[float]]": ("list[list[float]]", ""),
        "tuple[float,...]": ("list[float]", "tuple"),
        "dict": ("dict[str, Any]", ""),
        "dict|None": ("dict[str, Any] | None", ""),
        "dict[str,Any]": ("dict[str, Any]", ""),
        "float|np.ndarray": ("float | list[float]", "maybe_arr"),
    }
    if a in table:
        return table[a]
    # Unknown annotation: accept anything, no conversion (keeps generation robust).
    return ("Any", "")


def _default_repr(value: Any) -> str | None:
    """Render an inspect default value as a Python source literal, or None."""
    if value is inspect.Parameter.empty:
        return None
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, (int, str)):
        return repr(value)
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, tuple):
        return repr([float(x) if isinstance(x, float) else x for x in value])
    if isinstance(value, (list, dict)):
        return repr(value)
    # Numpy scalar or other → coerce to float if possible, else drop the default.
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return None


def _return_keys(node: ast.FunctionDef, module_ast: ast.Module | None = None) -> list[str]:
    """Static extraction of a function's response-dict keys.

    Beyond a direct ``return {...}`` literal, this also resolves the
    ``result = {...}; ...; result.update(<call>); return result`` idiom used
    throughout the Greeks-bearing MC pricers (asian_option_pricer and every
    function since): a dict literal assigned to a local variable, any
    ``.update()`` calls on that variable -- recursing one level into a
    same-module helper function if the update argument is a call (e.g.
    ``_bump_reprice_greeks``) -- and a final ``return <var>``.

    This is a best-effort static approximation, not real data-flow analysis:
    it collects every dict-literal assignment and every ``.update()`` call
    on a name ANYWHERE in the function regardless of which branch it's in or
    what order it appears in (two passes, so a `.update()` nested inside an
    `if` block is picked up even though `ast.walk`'s BFS order would
    otherwise visit a same-level `return` before descending into that
    branch) -- deliberately over-inclusive (union of all branches) since the
    goal is "every key that COULD appear in the response," which is exactly
    what a Pydantic response model with extra='allow' wants to document.
    More exotic patterns (dict-merge via `{**a, **b}`, `.update(**kwargs)`,
    multi-hop helper chains, keys computed then assigned via subscript like
    `result["x"] = ...`) are not handled and will under-report; a
    function that ends up with zero detected keys still falls back to the
    generic "result" placeholder exactly as before.
    """

    def _literal_dict_keys(d: ast.Dict) -> set[str]:
        return {k.value for k in d.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}

    def _helper_keys(func_name: str) -> set[str]:
        if module_ast is None:
            return set()
        for n in module_ast.body:
            if isinstance(n, ast.FunctionDef) and n.name == func_name:
                return set(_return_keys(n, module_ast))
        return set()

    # Pass 1: every dict-literal assignment and every `.update()` call on a
    # name, anywhere in the function -- order- and branch-independent.
    var_keys: dict[str, set[str]] = {}
    for n in ast.walk(node):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Dict):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    var_keys.setdefault(t.id, set()).update(_literal_dict_keys(n.value))
        elif (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "update"
            and isinstance(n.func.value, ast.Name)
            and n.args
        ):
            var_name = n.func.value.id
            arg = n.args[0]
            if isinstance(arg, ast.Dict):
                var_keys.setdefault(var_name, set()).update(_literal_dict_keys(arg))
            elif isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                var_keys.setdefault(var_name, set()).update(_helper_keys(arg.func.id))

    # Pass 2: every return statement, resolved against the variable map above.
    keys: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Return):
            if isinstance(n.value, ast.Dict):
                keys.update(_literal_dict_keys(n.value))
            elif isinstance(n.value, ast.Name) and n.value.id in var_keys:
                keys.update(var_keys[n.value.id])
    return sorted(keys)


def collect_module(module: str) -> list[dict[str, Any]]:
    """Return per-function metadata for one engine module."""
    path = ROOT / "engine" / f"{module}.py"
    tree = ast.parse(path.read_text())
    mod = importlib.import_module(f"engine.{module}")

    ast_funcs = {
        n.name: n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
    }

    funcs: list[dict[str, Any]] = []
    for name, node in ast_funcs.items():
        if name in EXCLUDE:
            continue
        fn = getattr(mod, name)
        sig = inspect.signature(fn)
        ann = {a.arg: ast.unparse(a.annotation) for a in node.args.args if a.annotation}

        params: list[dict[str, Any]] = []
        for pname, p in sig.parameters.items():
            if pname == "self":
                continue
            pytype, conv = _py_type_and_conv(ann.get(pname, "Any"))
            params.append(
                {
                    "name": pname,
                    "type": pytype,
                    "conv": conv,
                    "default": _default_repr(p.default),
                }
            )

        funcs.append(
            {
                "module": module,
                "name": name,  # endpoint/handler name (may be disambiguated)
                "real": name,  # actual engine attribute name (never changes)
                "cls": _class_name(name),
                "params": params,
                "return_keys": _return_keys(node, tree),
            }
        )
    return funcs


def render_schemas(domain: str, funcs: list[dict[str, Any]]) -> str:
    L: list[str] = []
    L.append(
        f'"""schemas/{domain.replace("-", "_")}.py — auto-generated Pydantic v2 '
        f"contracts for the {domain} domain.\n\n"
        "Generated by scripts/gen_p3.py from engine signatures. Request models are\n"
        "precisely typed and enforce regulatory validators (CLAUDE.md s4). Response\n"
        "models document engine return-dict keys; extra='allow' covers dynamically\n"
        'built keys that static analysis cannot enumerate.\n"""'
    )
    L.append("")
    L.append("from __future__ import annotations")
    L.append("")
    L.append("from typing import Any")
    L.append("")
    needs_validator = any(
        p["name"] in ("confidence_level", "confidence_levels") for f in funcs for p in f["params"]
    )
    if needs_validator:
        L.append("from pydantic import BaseModel, ConfigDict, Field, field_validator")
    else:
        L.append("from pydantic import BaseModel, ConfigDict, Field")
    L.append("")
    L.append("")
    for f in funcs:
        # ── Request ─────────────────────────────────────────────────────────
        L.append(f"class {f['cls']}Request(BaseModel):")
        L.append(f'    """Request parameters for {f["name"]}()."""')
        L.append("")
        # required first, then optional (defaults) — Python arg-order safe.
        req = [p for p in f["params"] if p["default"] is None]
        opt = [p for p in f["params"] if p["default"] is not None]
        if not req and not opt:
            L.append("    pass")
        for p in req:
            L.append(f"    {p['name']}: {p['type']}")
        for p in opt:
            L.append(f"    {p['name']}: {p['type']} = {p['default']}")
        # Regulatory validator: confidence level(s) in [0.90, 0.9999] (CLAUDE.md s4.1)
        names = {p["name"] for p in f["params"]}
        if "confidence_level" in names:
            L.append("")
            L.append('    @field_validator("confidence_level")')
            L.append("    @classmethod")
            L.append("    def _confidence_range(cls, v: float) -> float:")
            L.append("        if v is not None and not (0.90 <= v <= 0.9999):")
            L.append("            raise ValueError(")
            L.append(
                '                f"confidence_level {v} outside regulatory range ' '[0.90, 0.9999]"'
            )
            L.append("            )")
            L.append("        return v")
        if "confidence_levels" in names:
            L.append("")
            L.append('    @field_validator("confidence_levels")')
            L.append("    @classmethod")
            L.append("    def _confidence_levels_range(cls, v: list[float]) -> list[float]:")
            L.append("        for cl in v or []:")
            L.append("            if not (0.90 <= cl <= 0.9999):")
            L.append("                raise ValueError(")
            L.append(
                '                    f"confidence level {cl} outside regulatory '
                'range [0.90, 0.9999]"'
            )
            L.append("                )")
            L.append("        return v")
        L.append("")
        L.append("")
        # ── Response ────────────────────────────────────────────────────────
        L.append(f"class {f['cls']}Response(BaseModel):")
        L.append(f'    """Result of {f["name"]}(). Mirrors the engine return dict."""')
        L.append("")
        L.append('    model_config = ConfigDict(extra="allow", protected_namespaces=())')
        L.append("")
        keys = f["return_keys"] or ["result"]
        for k in keys:
            safe = k
            needs_alias = not k.isidentifier() or keyword.iskeyword(k) or k.startswith("model_")
            if needs_alias:
                safe = "f_" + "".join(c if (c.isalnum() or c == "_") else "_" for c in k)
                L.append(f'    {safe}: Any = Field(default=None, alias="{k}")')
            else:
                L.append(f"    {safe}: Any = Field(default=None)")
        L.append("")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def render_routes(domain: str, funcs: list[dict[str, Any]]) -> str:
    mod_name = domain.replace("-", "_")
    schema_mod = f"schemas.{mod_name}"
    # group engine imports by module; alias to avoid shadowing by handler defs
    by_mod: dict[str, list[tuple[str, str]]] = {}
    for f in funcs:
        by_mod.setdefault(f["module"], []).append((f["real"], f"_e_{f['name']}"))

    L: list[str] = []
    L.append(
        f'"""api/routes/{mod_name}.py — auto-generated FastAPI routes for the '
        f"{domain} domain.\n\n"
        "Generated by scripts/gen_p3.py. Each route validates its request, converts\n"
        "list payloads to NumPy arrays, calls the engine wrapper (the single source\n"
        "of truth), and returns the result dict via OrjsonResponse. No business logic\n"
        'lives here.\n"""'
    )
    L.append("")
    L.append("from __future__ import annotations")
    L.append("")
    L.append("import logging")
    L.append("from typing import Any")
    L.append("")
    L.append("import numpy as np")
    L.append("from fastapi import APIRouter, Depends, HTTPException, status")
    L.append("")
    L.append("from api.middleware.auth import TokenPayload, get_current_user")
    L.append("from api.responses import OrjsonResponse")
    for m in sorted(by_mod):
        names = ", ".join(f"{real} as {alias}" for real, alias in sorted(by_mod[m]))
        L.append(f"from engine.{m} import {names}")
    # schema imports
    cls_imports = []
    for f in funcs:
        cls_imports.append(f"{f['cls']}Request")
        cls_imports.append(f"{f['cls']}Response")
    L.append(f"from {schema_mod} import (")
    for c in sorted(cls_imports):
        L.append(f"    {c},")
    L.append(")")
    L.append("")
    L.append("logger = logging.getLogger(__name__)")
    L.append(f'router = APIRouter(prefix="/{domain}", tags=["{domain}"])')
    L.append("")
    L.append("# Engine input errors → HTTP 422. Explicit tuple (no bare except) covers")
    L.append("# bad numeric domains, singular matrices, and shape/key mismatches.")
    L.append("_INPUT_ERRORS = (")
    L.append("    ValueError,")
    L.append("    TypeError,")
    L.append("    KeyError,")
    L.append("    IndexError,")
    L.append("    ArithmeticError,")
    L.append("    AssertionError,")
    L.append("    np.linalg.LinAlgError,")
    L.append(")")
    L.append("")
    L.append("")
    for f in funcs:
        endpoint = f["name"]
        L.append("@router.post(")
        L.append(f'    "/{endpoint}",')
        L.append(f"    response_model={f['cls']}Response,")
        L.append(f'    summary="{f["name"].replace("_", " ").title()}",')
        L.append(")")
        L.append(f"async def {endpoint}(")
        L.append(f"    body: {f['cls']}Request,")
        L.append("    user: TokenPayload = Depends(get_current_user),")
        L.append(") -> OrjsonResponse:")
        # Per-tier simulation cap (fail fast before queuing/compute) — CLAUDE.md s5.
        if any(p["name"] == "n_simulations" for p in f["params"]):
            L.append("    if body.n_simulations > user.max_simulations:")
            L.append("        raise HTTPException(")
            L.append("            status_code=status.HTTP_403_FORBIDDEN,")
            L.append("            detail=(")
            L.append('                f"Your {user.tier!r} tier allows a maximum of "')
            L.append('                f"{user.max_simulations:,} simulations. "')
            L.append('                f"Requested: {body.n_simulations:,}."')
            L.append("            ),")
            L.append("        )")
        L.append("    kwargs = body.model_dump()")
        # conversions
        for p in f["params"]:
            n = p["name"]

            def _asarray(indent: str, key: str) -> None:
                # Emit a black-compatible (<=100 col) np.asarray assignment.
                line = f'{indent}kwargs["{key}"] = np.asarray(kwargs["{key}"], dtype=np.float64)'
                if len(line) <= 100:
                    L.append(line)
                else:
                    L.append(f'{indent}kwargs["{key}"] = np.asarray(')
                    L.append(f'{indent}    kwargs["{key}"], dtype=np.float64')
                    L.append(f"{indent})")

            if p["conv"] == "array":
                _asarray("    ", n)
            elif p["conv"] == "array_opt":
                L.append(f'    if kwargs["{n}"] is not None:')
                _asarray("        ", n)
            elif p["conv"] == "tuple":
                L.append(f'    kwargs["{n}"] = tuple(kwargs["{n}"])')
            elif p["conv"] == "maybe_arr":
                L.append(f'    if isinstance(kwargs["{n}"], list):')
                _asarray("        ", n)
        L.append("    try:")
        L.append(f"        result: Any = _e_{f['name']}(**kwargs)")
        L.append("    except _INPUT_ERRORS as exc:")
        L.append("        raise HTTPException(")
        L.append("            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,")
        L.append("            detail=str(exc),")
        L.append("        ) from exc")
        L.append("    if not isinstance(result, dict):")
        L.append('        result = {"result": result}')
        L.append("    return OrjsonResponse(content=result)")
        L.append("")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


# Curated happy-path cases per domain: (endpoint, body-literal). Bodies may
# reference the helpers R1, R2, COV, MEAN defined in each generated test module.
# Verified to return HTTP 200 against the live engine.
CURATED: dict[str, list[tuple[str, str]]] = {
    "market-risk": [
        ("conditional_var_es", '{"returns": R1, "portfolio_value": 1e6, "confidence_level": 0.99}'),
        ("garch_11_volatility_forecast", '{"returns": R1}'),
        ("correlation_matrix_historical", '{"returns_matrix": [R1, R2]}'),
        ("traffic_light_backtesting", '{"actual_returns": R1, "var_estimates": [0.02] * len(R1)}'),
    ],
    "credit-risk": [
        ("expected_loss_el_computation", '{"pd": 0.02, "lgd": 0.45, "ead": 1_000_000.0}'),
        ("ifrs_9_12_month_ecl_stage_1", '{"pd_12m": 0.02, "lgd": 0.40, "ead": 1_000_000.0}'),
        (
            "altman_z_score_credit_scoring",
            '{"working_capital": 50.0, "retained_earnings": 40.0, "ebit": 30.0, '
            '"market_value_equity": 80.0, "sales": 120.0, "total_assets": 200.0, '
            '"total_liabilities": 100.0}',
        ),
    ],
    "liquidity": [
        (
            "liquidity_coverage_ratio_lcr",
            '{"hqla": 1000.0, "gross_outflows": 800.0, "gross_inflows": 200.0}',
        ),
        (
            "net_stable_funding_ratio_nsfr",
            '{"available_stable_funding": 900.0, "required_stable_funding": 800.0}',
        ),
    ],
    "operational": [
        ("regulatory_compliance_score", '{"requirements_met": [1.0, 0.0, 1.0, 1.0]}'),
    ],
    "portfolio": [
        ("sharpe_ratio", '{"returns": R1}'),
        ("maximum_drawdown", '{"returns": R1}'),
        ("minimum_variance_portfolio", '{"cov_matrix": COV}'),
        ("mean_variance_optimisation", '{"mean_returns": MEAN, "cov_matrix": COV}'),
    ],
    "regulatory": [
        ("basel_iii_leverage_ratio", '{"tier1_capital": 80.0, "total_exposure": 1000.0}'),
    ],
    "derivatives": [
        (
            "black_scholes_european_option",
            '{"spot": 100.0, "strike": 100.0, "rate": 0.05, "sigma": 0.2, "tau": 1.0}',
        ),
        (
            "bond_pricer_fixed_coupon",
            '{"face_value": 100.0, "coupon_rate": 0.05, "yield_rate": 0.04, "maturity": 5.0}',
        ),
        (
            "monte_carlo_option_pricer",
            '{"spot": 100.0, "strike": 100.0, "rate": 0.05, "sigma": 0.2, "tau": 1.0, '
            '"n_simulations": 20000}',
        ),
    ],
    "alm": [
        (
            "duration_gap_analysis",
            '{"asset_duration": 5.0, "liability_duration": 3.0, "total_assets": 1000.0, '
            '"total_liabilities": 900.0}',
        ),
    ],
}


def render_tests(domain: str, n_routes: int) -> str:
    mod_name = domain.replace("-", "_")
    curated = CURATED.get(domain, [])
    L: list[str] = []
    L.append(
        f'"""tests/test_{mod_name}_api.py — integration tests for the {domain} '
        f"domain.\n\n"
        "Auto-generated by scripts/gen_p3.py. Covers, across the whole domain:\n"
        "  - route registration (count matches the engine surface),\n"
        "  - authentication (every route rejects a missing bearer token),\n"
        "  - input robustness (empty body never 500s — always 200 or 422),\n"
        "  - curated happy paths that exercise the engine and assert HTTP 200.\n"
        '"""'
    )
    L.append("")
    L.append("from __future__ import annotations")
    L.append("")
    L.append("import pytest")
    L.append("from httpx import ASGITransport, AsyncClient")
    L.append("")
    L.append("from api.middleware.auth import create_access_token")
    L.append("from ingestion.fixtures import generate_gbm_returns")
    L.append("from main import create_app")
    L.append("")
    L.append(f'DOMAIN = "{domain}"')
    L.append(f"EXPECTED_ROUTES = {n_routes}")
    L.append("")
    L.append("R1 = generate_gbm_returns(n_obs=252, seed=1).tolist()")
    L.append("R2 = generate_gbm_returns(n_obs=252, seed=2).tolist()")
    L.append("MEAN = [0.08, 0.10, 0.12]")
    L.append("COV = [[0.04, 0.01, 0.0], [0.01, 0.05, 0.01], [0.0, 0.01, 0.06]]")
    L.append("")
    L.append("")
    L.append("@pytest.fixture(scope='module')")
    L.append("def app():")
    L.append("    return create_app()")
    L.append("")
    L.append("")
    L.append("@pytest.fixture")
    L.append("def headers():")
    L.append(
        "    return {\"Authorization\": f\"Bearer {create_access_token('tester', 'enterprise')}\"}"
    )
    L.append("")
    L.append("")
    L.append("def _domain_routes(app) -> list[str]:")
    L.append('    prefix = f"/api/v1/{DOMAIN}/"')
    # app.routes can hold both plain Route objects and _IncludedRouter-style
    # mount wrappers (from app.include_router()) that have no top-level
    # `.path` attribute -- walking the OpenAPI spec instead sidesteps that
    # entirely and is stable across FastAPI/Starlette router-internals changes.
    L.append("    spec = app.openapi()")
    L.append("    return sorted(")
    L.append("        {")
    L.append("            path")
    L.append('            for path, methods in spec.get("paths", {}).items()')
    L.append('            if path.startswith(prefix) and "post" in methods')
    L.append("        }")
    L.append("    )")
    L.append("")
    L.append("")
    L.append("def _client(app) -> AsyncClient:")
    L.append('    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")')
    L.append("")
    L.append("")
    L.append("def test_routes_registered(app):")
    L.append("    assert len(_domain_routes(app)) == EXPECTED_ROUTES")
    L.append("")
    L.append("")
    L.append("@pytest.mark.asyncio")
    L.append("async def test_all_routes_require_auth(app):")
    L.append("    async with _client(app) as client:")
    L.append("        for path in _domain_routes(app):")
    L.append("            resp = await client.post(path, json={})")
    L.append("            assert resp.status_code in (401, 403), path")
    L.append("")
    L.append("")
    L.append("@pytest.mark.asyncio")
    L.append("async def test_empty_body_never_500(app, headers):")
    L.append("    async with _client(app) as client:")
    L.append("        for path in _domain_routes(app):")
    L.append("            resp = await client.post(path, json={}, headers=headers)")
    L.append(
        "            assert resp.status_code in (200, 422), " "f'{path} -> {resp.status_code}'"
    )
    L.append("")
    L.append("")
    if curated:
        L.append("HAPPY_PATHS = [")
        for ep, body in curated:
            L.append(f'    ("{ep}", {body}),')
        L.append("]")
        L.append("")
        L.append("")
        L.append('@pytest.mark.parametrize("endpoint,body", HAPPY_PATHS)')
        L.append("@pytest.mark.asyncio")
        L.append("async def test_happy_path(app, headers, endpoint, body):")
        L.append('    path = f"/api/v1/{DOMAIN}/{endpoint}"')
        L.append("    async with _client(app) as client:")
        L.append("        resp = await client.post(path, json=body, headers=headers)")
        L.append("    assert resp.status_code == 200, f'{path} -> {resp.text[:200]}'")
        L.append("    data = resp.json()")
        L.append("    assert isinstance(data, dict) and data")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def main() -> None:
    summary: dict[str, int] = {}
    for domain, modules in DOMAINS.items():
        funcs: list[dict[str, Any]] = []
        for m in modules:
            funcs.extend(collect_module(m))
        # disambiguate any endpoint-name collisions within the domain
        seen: dict[str, int] = {}
        for f in funcs:
            if f["name"] in seen:
                f["name"] = f"{f['name']}_{f['module']}"
                f["cls"] = _class_name(f["name"])
            seen[f["name"]] = 1
        mod_name = domain.replace("-", "_")
        (ROOT / "schemas" / f"{mod_name}.py").write_text(render_schemas(domain, funcs))
        (ROOT / "api" / "routes" / f"{mod_name}.py").write_text(render_routes(domain, funcs))
        (ROOT / "tests" / f"test_{mod_name}_api.py").write_text(render_tests(domain, len(funcs)))
        summary[domain] = len(funcs)
        print(f"  {domain:14s} {len(funcs):4d} routes")
    print(f"TOTAL: {sum(summary.values())} routes across {len(summary)} domains")


if __name__ == "__main__":
    main()

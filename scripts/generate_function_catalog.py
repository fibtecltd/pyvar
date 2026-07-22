"""
scripts/generate_function_catalog.py — generate portal/functions.json (P8 Task 4/5)

Reasoning:
- Single shared data source for all 385 functions across 8 domains, per the
  P8 lead prompt's architecture clarification: one JSON feeds both the
  Fuse.js search index (Task 4) and the "Try it" panel's dynamic forms
  (Task 5) — no per-function HTML.
- Two sources, both derived from live code, chosen after checking four
  candidates (see PR discussion): pyvar_functions.csv is stale (382 rows vs
  385 real routes — market-risk alone grew by 3 since it was generated);
  the per-page portal/domain-*.html `FUNCTIONS`/`ALL_FNS` arrays are
  inconsistent across domains (credit-risk's matches its real routes at
  100% confidence, but market-risk's is actually credit-risk's content
  copy-pasted — see #152 — and alm's has no descriptions and scrambled
  category tags). Both are unusable as a uniform source across all 8
  domains.
    1. The live OpenAPI schema (main.create_app().openapi()) — generated
       directly from the registered routes and Pydantic models, so it
       cannot drift from what the API actually does. Gives the exact path,
       domain (router tag), and full request parameter schema.
    2. Engine function docstrings (engine/*.py) — every route handler
       imports its engine function under a consistent `_e_<name>` alias
       (see api/routes/*.py), so the real function object (and therefore
       its Google-style docstring) is resolvable by introspecting the
       already-imported route module — no source parsing needed.
- var.py (the flagship VaR demo endpoint), auth.py, and public_data.py are
  excluded: they are infrastructure endpoints, not among the 385 named
  domain functions the catalog is describing.
- Run this whenever routes/schemas/engine docstrings change — it is not
  wired into CI; regenerate and commit portal/functions.json by hand.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# domain router tag -> (display label, portal page, brand colour)
# Colours match the P8 lead prompt's domain colour-coding intent (index.html's
# --green is the brand/primary colour, reused here for Market Risk as the
# flagship domain); other colours read from each domain page's own --svc
# variable EXCEPT domain-market-risk.html, whose --svc is wrong (#152 — it's
# a copy of credit-risk's gold) and is therefore not used as the source here.
DOMAINS: dict[str, dict[str, str]] = {
    "market-risk": {"label": "Market Risk", "page": "domain-market-risk.html", "color": "#00d97e"},
    "credit-risk": {"label": "Credit Risk", "page": "domain-credit-risk.html", "color": "#c8a44a"},
    "liquidity": {"label": "Liquidity Risk", "page": "domain-liquidity-risk.html", "color": "#1a9e72"},
    "operational": {"label": "Operational Risk", "page": "domain-operational-risk.html", "color": "#c44a3a"},
    "portfolio": {"label": "Portfolio Analytics", "page": "domain-portfolio-analytics.html", "color": "#7060d4"},
    "regulatory": {"label": "Regulatory & Compliance", "page": "domain-regulatory.html", "color": "#4a9e22"},
    "derivatives": {"label": "Derivatives & Pricing", "page": "domain-derivatives.html", "color": "#c47a2a"},
    "alm": {"label": "ALM & Balance Sheet", "page": "domain-alm.html", "color": "#6a7a8a"},
}

# router tag -> api/routes/<module>.py, for resolving the _e_<name> engine alias
DOMAIN_MODULES: dict[str, str] = {
    "market-risk": "market_risk",
    "credit-risk": "credit_risk",
    "liquidity": "liquidity",
    "operational": "operational",
    "portfolio": "portfolio",
    "regulatory": "regulatory",
    "derivatives": "derivatives",
    "alm": "alm",
}


def _resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Follow a single $ref into components/schemas; return the resolved schema."""
    ref = schema.get("$ref")
    if not ref:
        return schema
    name = ref.rsplit("/", 1)[-1]
    return components.get(name, {})


def _extract_params(request_schema: dict[str, Any]) -> list[dict[str, Any]]:
    props = request_schema.get("properties", {})
    required = set(request_schema.get("required", []))
    params = []
    for field_name, field_schema in props.items():
        params.append(
            {
                "name": field_name,
                "type": field_schema.get("type", "object"),
                "required": field_name in required,
                "default": field_schema.get("default"),
                "description": field_schema.get("description"),
                "minimum": field_schema.get("minimum"),
                "maximum": field_schema.get("maximum"),
                "exclusiveMinimum": field_schema.get("exclusiveMinimum"),
                "exclusiveMaximum": field_schema.get("exclusiveMaximum"),
            }
        )
    return params


def _engine_docstring(module: Any, function_name: str) -> tuple[str, str]:
    """Returns (one-line summary, full description) from the _e_<name> engine alias."""
    engine_fn = getattr(module, f"_e_{function_name}", None)
    if engine_fn is None:
        return ("", "")
    doc = inspect.getdoc(engine_fn) or ""
    if not doc:
        return ("", "")
    lines = doc.split("\n")
    summary = lines[0].strip()
    # Description: everything before the first Google-style section header,
    # excluding the summary line itself.
    body_lines: list[str] = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith(("Args:", "Returns:", "Raises:")):
            break
        body_lines.append(line)
    description = "\n".join(body_lines).strip()
    return (summary, description)


def generate() -> list[dict[str, Any]]:
    from main import create_app

    app = create_app()
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})

    modules = {tag: importlib.import_module(f"api.routes.{mod}") for tag, mod in DOMAIN_MODULES.items()}

    catalog: list[dict[str, Any]] = []
    unresolved_engine_alias: list[str] = []

    for path, methods in schema.get("paths", {}).items():
        post_op = methods.get("post")
        if post_op is None:
            continue
        tags = post_op.get("tags", [])
        if not tags or tags[0] not in DOMAINS:
            continue
        domain = tags[0]
        function_name = path.rsplit("/", 1)[-1]

        request_body = post_op.get("requestBody", {})
        body_schema = request_body.get("content", {}).get("application/json", {}).get("schema", {})
        request_schema = _resolve_schema(body_schema, components)
        params = _extract_params(request_schema)

        module = modules[domain]
        summary, description = _engine_docstring(module, function_name)
        if not summary:
            unresolved_engine_alias.append(f"{domain}/{function_name}")

        domain_meta = DOMAINS[domain]
        catalog.append(
            {
                "domain": domain,
                "domain_label": domain_meta["label"],
                "domain_page": domain_meta["page"],
                "domain_color": domain_meta["color"],
                "name": function_name,
                "display_name": post_op.get("summary", function_name),
                "path": path,
                "summary": summary or post_op.get("summary", function_name),
                "description": description,
                "params": params,
            }
        )

    catalog.sort(key=lambda f: (f["domain"], f["name"]))

    if unresolved_engine_alias:
        print(
            f"WARNING: {len(unresolved_engine_alias)} function(s) had no resolvable "
            f"_e_<name> engine alias (fell back to the OpenAPI summary only):",
            file=sys.stderr,
        )
        for item in unresolved_engine_alias:
            print(f"  - {item}", file=sys.stderr)

    return catalog


def main() -> None:
    catalog = generate()
    out_path = REPO_ROOT / "portal" / "functions.json"
    out_path.write_text(json.dumps(catalog, indent=2) + "\n")

    by_domain: dict[str, int] = {}
    for fn in catalog:
        by_domain[fn["domain"]] = by_domain.get(fn["domain"], 0) + 1

    print(f"Wrote {len(catalog)} functions to {out_path}")
    for domain, count in sorted(by_domain.items()):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    main()

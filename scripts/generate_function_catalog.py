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
- formula field (P11 item 5, docs/p11-pre-launch-hardening.md §4): merged in
  from scripts/data/function_formulas.json, a separate, hand-reviewed,
  committed file keyed by function name -- NOT derived from the OpenAPI
  schema or docstrings the way every other field here is, because no
  formula/equation data exists anywhere in engine/'s docstrings today (each
  formula had to be derived by reading the actual implementation code,
  domain by domain, and independently verified against it -- a one-time
  sourcing effort, not something this script can regenerate on its own).
  Keeping it in a separate file rather than hardcoded inline here means
  regenerating functions.json for an unrelated reason (a new function, a
  changed parameter) merges the existing formulas back in automatically
  instead of wiping them, and only genuinely new functions need a new
  formula entry written by hand.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
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
    "liquidity": {
        "label": "Liquidity Risk",
        "page": "domain-liquidity-risk.html",
        "color": "#1a9e72",
    },
    "operational": {
        "label": "Operational Risk",
        "page": "domain-operational-risk.html",
        "color": "#c44a3a",
    },
    "portfolio": {
        "label": "Portfolio Analytics",
        "page": "domain-portfolio-analytics.html",
        "color": "#7060d4",
    },
    "regulatory": {
        "label": "Regulatory & Compliance",
        "page": "domain-regulatory.html",
        "color": "#4a9e22",
    },
    "derivatives": {
        "label": "Derivatives & Pricing",
        "page": "domain-derivatives.html",
        "color": "#c47a2a",
    },
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


def _harvest_acronym_casing(catalog: list[dict[str, Any]]) -> dict[str, str]:
    """Derive correct acronym casing (VaR, PD, RCSA, ...) from the engine
    docstrings themselves, restricted to tokens that actually appear in a
    function name — rather than a hand-guessed, hardcoded list that would
    go stale as functions are added. See module docstring.

    A word counts as an acronym candidate if it has >=2 uppercase letters
    (catches both ALL-CAPS like "PD" and mixed like "VaR"/"CreditMetrics").
    All-uppercase candidates longer than 6 characters are dropped — those
    are almost always a normal English word written in caps for emphasis
    in prose (e.g. "REGULATORY"), not a genuine short acronym; mixed-case
    candidates (VaR, OpVaR, CreditMetrics, MiFID, ...) are kept at any
    length since accidental all-caps emphasis is always fully uppercase.

    A candidate immediately adjacent to an underscore in the source text
    (either side) is also dropped: that means it's one fragment of a
    snake_case/CONSTANT_CASE Python identifier this tokenizer split on '_'
    (e.g. "LIMIT" out of ``CRR2_INSTITUTION_ABSOLUTE_LIMIT_EUR``), not a
    standalone acronym written in prose — voting it in would override a
    word's normal Title Case (see the crr2_large_exposure_limit regression
    this guarded against). A short acronym genuinely used in prose, even
    inside an inline-code formula alongside underscored variables (e.g.
    ``KVA = cost_of_capital * ...`` or ``total_xva = CVA + ... + KVA``), has
    no underscore on either side of the acronym itself, so it still votes.
    """
    name_tokens = {tok.lower() for f in catalog for tok in f["name"].split("_")}

    text = "\n".join(f.get("summary", "") + "\n" + f.get("description", "") for f in catalog)
    votes: dict[str, dict[str, int]] = {}
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9]*", text):
        word = m.group(0)
        start, end = m.span()
        if (start > 0 and text[start - 1] == "_") or (end < len(text) and text[end] == "_"):
            continue
        if sum(1 for c in word if c.isupper()) < 2:
            continue
        is_all_upper = word == word.upper()
        if is_all_upper and len(word) > 6:
            continue
        key = word.lower()
        if key not in name_tokens:
            continue
        votes.setdefault(key, {})
        votes[key][word] = votes[key].get(word, 0) + 1

    return {key: max(casings, key=casings.get) for key, casings in votes.items()}


def _display_name(function_name: str, acronym_casing: dict[str, str]) -> str:
    words = []
    for token in function_name.split("_"):
        cased = acronym_casing.get(token.lower())
        words.append(cased if cased else token.capitalize())
    return " ".join(words)


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


FORMULAS_PATH = REPO_ROOT / "scripts" / "data" / "function_formulas.json"


def _load_formulas() -> dict[str, dict[str, Any]]:
    if not FORMULAS_PATH.exists():
        return {}
    return json.loads(FORMULAS_PATH.read_text())


def generate() -> list[dict[str, Any]]:
    from main import create_app

    app = create_app()
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})

    modules = {
        tag: importlib.import_module(f"api.routes.{mod}") for tag, mod in DOMAIN_MODULES.items()
    }

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
                "display_name": "",  # filled in below, once acronym casing is known
                "path": path,
                "summary": summary or post_op.get("summary", function_name),
                "description": description,
                "params": params,
            }
        )

    acronym_casing = _harvest_acronym_casing(catalog)
    for fn in catalog:
        fn["display_name"] = _display_name(fn["name"], acronym_casing)

    formulas = _load_formulas()
    missing_formula: list[str] = []
    for fn in catalog:
        entry = formulas.get(fn["name"])
        fn["formula"] = entry
        if entry is None:
            missing_formula.append(f"{fn['domain']}/{fn['name']}")

    catalog.sort(key=lambda f: (f["domain"], f["name"]))

    if unresolved_engine_alias:
        print(
            f"WARNING: {len(unresolved_engine_alias)} function(s) had no resolvable "
            f"_e_<name> engine alias (fell back to the OpenAPI summary only):",
            file=sys.stderr,
        )
        for item in unresolved_engine_alias:
            print(f"  - {item}", file=sys.stderr)

    if missing_formula:
        print(
            f"WARNING: {len(missing_formula)} function(s) have no entry in "
            f"{FORMULAS_PATH.relative_to(REPO_ROOT)} (formula field will be null) — "
            "add one by hand, following the schema of an existing entry:",
            file=sys.stderr,
        )
        for item in missing_formula:
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

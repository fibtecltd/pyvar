"""scripts/sync_skills.py — render the 8 domain skills in .claude/skills/ from specs.

Reasoning:
- The 8 domain skills (market-risk ... alm) used to be hand-written lists of
  `pyvar.<domain>.<fn>(**params)` stubs. That shape had two real problems:
  nothing in it told Claude how to actually run a function (no key, no URL, no
  client, no parameter names), and the hand-typed function names drifted from
  the API -- 26 of market-risk's 68 names did not match a real endpoint.
- So everything that must be *true* is now derived, never typed:
    * function names, summaries, parameter names/defaults/bounds  <- portal/functions.json
    * parameter types (list vs scalar, enums, min/max items)       <- the live OpenAPI schema
  and only the genuinely editorial content is hand-maintained, in
  scripts/skill_specs/<skill>.json (description, groups, per-function notes,
  worked examples) and scripts/skill_specs/<skill>.tail.md (domain caveats,
  regulatory constants, contributor notes -- copied verbatim).
- Source of truth for the *published* skill stays .claude/skills/<skill>/;
  scripts/generate_plugins.py copies SKILL.md and references/ into plugins/.
  tests/test_skills_sync.py runs this script in --check mode, so a catalog
  change (a new function, a renamed parameter) fails CI until it is re-synced.
- The five arch-* skills are contributor guides, not API guides, and are
  hand-written; this script does not touch them.

Usage:
  python3 scripts/sync_skills.py            # rewrite SKILL.md + references/
  python3 scripts/sync_skills.py --check    # exit 1 if anything is stale
"""

from __future__ import annotations

import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FUNCTIONS_JSON = REPO_ROOT / "portal" / "functions.json"
SPEC_DIR = REPO_ROOT / "scripts" / "skill_specs"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

DOMAIN_SKILLS = (
    "market-risk",
    "credit-risk",
    "liquidity-risk",
    "operational-risk",
    "portfolio-analytics",
    "regulatory",
    "derivatives",
    "alm",
)

BASE_URL = "https://www.pyvar.com"
SIGNUP_URL = f"{BASE_URL}#get-api-key"
_PLACEHOLDER_RE = re.compile(r'"<returns:(\d+)>"')

SETUP_TEMPLATE = """\
## Before you call anything

This skill is a guide to the **live pyvar.com API**. It computes nothing by itself, and every
function needs a pyvar API key. Don't substitute your own numpy/scipy code and present the result
as pyvar output: these are regulatory-grade functions and the user wants pyvar's own numbers.

1. **Find the key.** Look for `PYVAR_API_KEY` in the environment. If the pyvar MCP server is
   connected, its tools (`call_pyvar_function`, `list_pyvar_functions`) already carry the key.
2. **No key? Say so, and walk the user through getting one** (free, about a minute): open
   {signup_url}, then either click "Sign in with Google" (when it is shown) or enter an email and
   click the verification link (valid 24 hours, single use). The page shows the key once. Ask the
   user to copy it and set `PYVAR_API_KEY`. Keys are short-lived (60 minutes by default). On a
   `401 Invalid or expired token`, ask for a fresh one: Google sign-in issues a new key every time,
   whereas the emailed link cannot be reused, so an address that cannot sign in with Google has to
   register a different email.
3. **Call the function** with the request body below (every example in this skill is a real,
   tested request). Use whichever of these is available:
   - Python: `pip install pyvar-client`, then
     `Client(api_key=os.environ["PYVAR_API_KEY"]).{ns}.<function>(**body)`.
   - REST: `POST {base_url}/api/v1/{domain}/<function>` with header
     `Authorization: Bearer $PYVAR_API_KEY` and the body as JSON.
   - MCP: `call_pyvar_function(domain="{domain}", function_name="<function>", params=body)`.
   If you cannot run code or reach the network (for example a sandbox with no internet), give the
   user the exact `curl` command or Python snippet to run themselves instead of guessing a result.
4. **Read the response.** Every function returns one JSON object. Quote the key numbers together
   with the inputs you used (and units: rates and returns are decimals, so 0.02 means 2%).

Errors: `401` bad or expired key; `422` a parameter is wrong (the `detail` field names it: fix it
and retry, never resend the same body); `429` the daily quota is used up (free tier: 10 calls per
day across all pyvar functions; the `Retry-After` header is in seconds): tell the user instead of
retrying in a loop.
"""


def _load_catalog() -> dict[tuple[str, str], dict[str, Any]]:
    entries = json.loads(FUNCTIONS_JSON.read_text())
    return {(e["domain"], e["name"]): e for e in entries}


# ── OpenAPI-derived parameter types ──────────────────────────────────────────


def _render_type(schema: dict[str, Any]) -> str:
    if "anyOf" in schema:
        parts: list[str] = []
        for sub in schema["anyOf"]:
            rendered = _render_type(sub)
            if rendered not in parts:
                parts.append(rendered)
        return " or ".join(parts)
    if "enum" in schema:
        return " or ".join(json.dumps(v) for v in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        return _render_type(schema.get("items", {})) + "[]"
    if kind == "object":
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict) and extra:
            return "{str: " + _render_type(extra) + "}"
        return "object"
    return str(kind or "any")


def _array_bounds(schema: dict[str, Any]) -> str:
    subs = schema.get("anyOf", [schema])
    bits: list[str] = []
    for sub in subs:
        if sub.get("type") == "array":
            if "minItems" in sub:
                bits.append(f"at least {sub['minItems']} items")
            if "maxItems" in sub:
                bits.append(f"at most {sub['maxItems']} items")
            break
    return ", ".join(bits)


def _openapi_param_types() -> dict[str, dict[str, tuple[str, str]]]:
    """path -> param name -> (type string, array-bounds note) from the live app."""
    sys.path.insert(0, str(REPO_ROOT))
    from main import create_app

    spec = create_app().openapi()
    components = spec["components"]["schemas"]
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for path, item in spec["paths"].items():
        post = item.get("post")
        if not post or "requestBody" not in post:
            continue
        schema = post["requestBody"]["content"]["application/json"]["schema"]
        if "$ref" in schema:
            schema = components[schema["$ref"].split("/")[-1]]
        out[path] = {
            name: (_render_type(prop), _array_bounds(prop))
            for name, prop in schema.get("properties", {}).items()
        }
    return out


# ── rendering ────────────────────────────────────────────────────────────────


def _py(value: Any) -> str:
    return repr(value)


def _signature(entry: dict[str, Any]) -> str:
    parts = []
    for p in entry["params"]:
        parts.append(p["name"] if p["required"] else f"{p['name']}={_py(p['default'])}")
    return f"{entry['name']}({', '.join(parts)})"


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line.strip() else "" for line in text.splitlines())


def _format_note(note: str) -> str:
    note = note.strip()
    if note.startswith(">") or "\n" in note:
        return note
    return "Note: " + note[0].upper() + note[1:]


def _frontmatter(spec: dict[str, Any]) -> str:
    desc = textwrap.fill(" ".join(spec["description"].split()), width=92, break_on_hyphens=False)
    desc = textwrap.indent(desc, "  ")
    tags = ", ".join(spec["tags"])
    return (
        "---\n"
        f"name: pyvar-{spec['skill']}\n"
        f"description: >\n{desc}\n"
        f'version: "{spec["version"]}"\n'
        'author: "Fibtec Limited — pyvar.com"\n'
        f"tags: [{tags}]\n"
        "---\n"
    )


def _compact_json(value: Any, indent: int = 0) -> str:
    """JSON with objects expanded but arrays of numbers/strings kept on one line."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        inner = ",\n".join(
            f"{pad}  {json.dumps(k)}: {_compact_json(v, indent + 1)}" for k, v in value.items()
        )
        return "{\n" + inner + "\n" + pad + "}"
    if isinstance(value, list):
        if all(not isinstance(v, (dict, list)) or _is_flat(v) for v in value):
            return "[" + ", ".join(_compact_json(v, indent) for v in value) + "]"
        inner = ",\n".join(f"{pad}  {_compact_json(v, indent + 1)}" for v in value)
        return "[\n" + inner + "\n" + pad + "]"
    return json.dumps(value, ensure_ascii=False)


def _is_flat(value: Any) -> bool:
    return isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value)


def _render_example(spec: dict[str, Any], index: int, ex: dict[str, Any]) -> str:
    lines = [f"### {index}. {ex['title']}", "", ex["intro"], ""]
    for call in ex["calls"]:
        body = _compact_json(call["request"])
        body = _PLACEHOLDER_RE.sub(lambda m: f"[ /* your {m.group(1)} daily log-returns */ ]", body)
        lines += [
            f"`POST /api/v1/{spec['domain']}/{call['function']}`",
            "",
            "```json",
            body,
            "```",
            "",
            "Returns: " + ", ".join(f"`{k}`" for k in call["returns"]) + ".",
            "",
        ]
    if ex.get("takeaway"):
        lines += [ex["takeaway"], ""]
    return "\n".join(lines).rstrip() + "\n"


def render_skill(spec: dict[str, Any], catalog: dict[tuple[str, str], dict[str, Any]]) -> str:
    domain = spec["domain"]
    members = [(g, fn) for g in spec["groups"] for fn in g["functions"]]
    names = [fn for _, fn in members]
    expected = sorted(n for (d, n) in catalog if d == domain)
    if sorted(names) != expected:
        missing = sorted(set(expected) - set(names))
        extra = sorted(set(names) - set(expected))
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise SystemExit(
            f"{spec['skill']}: spec groups disagree with portal/functions.json "
            f"(missing={missing}, unknown={extra}, duplicated={dupes}) -- edit "
            f"scripts/skill_specs/{spec['skill']}.json"
        )

    out = [_frontmatter(spec)]
    out.append(f"# pyvar — {spec['title']}  ({len(names)} functions)\n")
    out.append(spec["tagline"].strip() + "\n")
    out.append(
        SETUP_TEMPLATE.format(
            signup_url=SIGNUP_URL, base_url=BASE_URL, ns=spec["client_ns"], domain=domain
        )
    )
    if spec.get("after_setup_md"):
        out.append(spec["after_setup_md"].strip() + "\n")

    out.append("## Worked examples\n")
    out.append(
        "Each request body below is the same set of keyword arguments for the Python client, the "
        "REST body and the MCP `params`. They were run against the real API.\n"
    )
    for i, ex in enumerate(spec["examples"], 1):
        out.append(_render_example(spec, i, ex))

    out.append(f"## Functions ({len(names)})\n")
    out.append(
        f"Every function is `POST /api/v1/{domain}/<name>`. Required parameters are listed bare, "
        "optional ones with their defaults (`name=default`). Types, bounds and formulas are in "
        "[references/functions.md](references/functions.md): read the entry before calling a "
        "function you have not used yet.\n"
    )
    for group in spec["groups"]:
        out.append(f"### {group['title']}\n")
        if group.get("intro"):
            out.append(group["intro"].strip() + "\n")
        for fn in group["functions"]:
            entry = catalog[(domain, fn)]
            line = f"- `{_signature(entry)}`: {entry['summary'].rstrip('.')}."
            note = spec["notes"].get(fn)
            out.append(line)
            if note:
                out.append(_indent(_format_note(note)))
        out.append("")

    tail = (SPEC_DIR / f"{spec['skill']}.tail.md").read_text().strip()
    out.append(tail + "\n")
    return "\n".join(out).rstrip() + "\n"


def render_reference(
    spec: dict[str, Any],
    catalog: dict[tuple[str, str], dict[str, Any]],
    types: dict[str, dict[str, tuple[str, str]]],
) -> str:
    domain = spec["domain"]
    out = [
        f"# pyvar {spec['title']}: parameter reference\n",
        (
            "Generated from `portal/functions.json` and the live OpenAPI schema by "
            "`scripts/sync_skills.py`: do not edit by hand. Every function is "
            f"`POST /api/v1/{domain}/<name>` with a JSON body of the parameters below; "
            "`*` marks a required parameter.\n"
        ),
    ]
    for group in spec["groups"]:
        out.append(f"## {group['title']}\n")
        for fn in group["functions"]:
            entry = catalog[(domain, fn)]
            ptypes = types.get(entry["path"], {})
            out.append(f"### {fn}\n")
            out.append(f"`POST {entry['path']}`: {entry['summary']}\n")
            desc = (entry.get("description") or "").strip()
            if desc:
                out.append(desc + "\n")
            formula = (entry.get("formula") or {}).get("formula_latex")
            if formula:
                out.append(f"Formula (LaTeX): `{formula}`\n")
            if entry["params"]:
                out.append("| Parameter | Type | Default | Notes |")
                out.append("|---|---|---|---|")
            for p in entry["params"]:
                ptype, bounds = ptypes.get(p["name"], (p["type"], ""))
                notes = []
                if p.get("description"):
                    notes.append(p["description"])
                for key, label in (
                    ("minimum", ">="),
                    ("exclusiveMinimum", ">"),
                    ("maximum", "<="),
                    ("exclusiveMaximum", "<"),
                ):
                    if p.get(key) is not None:
                        notes.append(f"{label} {p[key]}")
                if bounds:
                    notes.append(bounds)
                default = "required" if p["required"] else f"`{_py(p['default'])}`"
                star = "*" if p["required"] else ""
                note_text = "; ".join(notes).replace("|", "\\|")
                out.append(f"| `{p['name']}`{star} | `{ptype}` | {default} | {note_text} |")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _targets() -> list[tuple[Path, str]]:
    catalog = _load_catalog()
    types = _openapi_param_types()
    results: list[tuple[Path, str]] = []
    for skill in DOMAIN_SKILLS:
        spec = json.loads((SPEC_DIR / f"{skill}.json").read_text())
        results.append((SKILLS_DIR / skill / "SKILL.md", render_skill(spec, catalog)))
        results.append(
            (
                SKILLS_DIR / skill / "references" / "functions.md",
                render_reference(spec, catalog, types),
            )
        )
    return results


def main() -> None:
    check = "--check" in sys.argv[1:]
    stale: list[str] = []
    for path, content in _targets():
        current = path.read_text() if path.exists() else None
        if current == content:
            continue
        stale.append(str(path.relative_to(REPO_ROOT)))
        if not check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"wrote {path.relative_to(REPO_ROOT)}")
    if check and stale:
        print("stale (run `python3 scripts/sync_skills.py`):\n  " + "\n  ".join(stale))
        raise SystemExit(1)
    if not stale:
        print("skills are in sync")


if __name__ == "__main__":
    main()

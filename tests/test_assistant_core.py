"""The assistant kernel (assistant/) moved out of scripts/assistant_eval/ with no change of behaviour (PR 1).

Reasoning:
- Production code will import the prompts and graders the measurements used, so the move must change nothing:
  the shims at the old paths are the same module objects (a monkeypatch through either name is seen by both),
  the system prompt is byte-identical, and the graders give identical results on the 576 Phase 0 cases. The
  three hashes below were computed on origin/feat/assistant-eval-typed BEFORE the move.
- The kernel must not reach the network. PR 2 adds the one module allowed to import `anthropic`; until then no
  module under assistant/ may import any network or HTTP library.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO / "scripts" / "assistant_eval"))

import cases as case_builder  # noqa: E402
import graders  # noqa: E402

import assistant  # noqa: E402
import assistant.prompts as prompts  # noqa: E402

# Computed before the move, on the head of feat/assistant-eval-typed (43c577c).
SYSTEM_PROMPT_SHA256 = "181f6a14a32585890e41c32c3c2d861c9e85e0d7fbb4300579a41bf51e0231f7"
PHASE0_CASES_SHA256 = "c57a3b304a54e682fa6766a13da40a6722cbb36fce6f1d4f58edbfdd40fa6f6a"
ORACLE_GRADES_SHA256 = "618397a5ff9fe1db788806ec231dcf093bb847f51d2926fe0b5eccc461f7b057"

MOVED = ["prompts", "graders", "cost", "body_schema", "scrub"]
FORBIDDEN = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib.request",
    "urllib3",
    "http.client",
    "websocket",
    "websockets",
    "anthropic",
    "boto3",
}


@pytest.mark.parametrize("name", MOVED)
def test_the_old_name_is_the_same_module_object_as_the_new_one(name: str) -> None:
    new = importlib.import_module(f"assistant.{name}")
    old = importlib.import_module(name)  # scripts/assistant_eval is on sys.path
    assert old is new
    assert importlib.import_module(f"scripts.assistant_eval.{name}") is new


def test_a_monkeypatch_through_either_name_is_seen_by_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cost

    import assistant.cost

    monkeypatch.setattr(cost, "PROMPT_RATE_CARD_LIMIT", 7)
    assert assistant.cost.PROMPT_RATE_CARD_LIMIT == 7
    monkeypatch.setattr(assistant.cost, "PROMPT_RATE_CARD_LIMIT", 9)
    assert cost.PROMPT_RATE_CARD_LIMIT == 9


def test_the_shims_are_thin_and_the_kernel_files_are_the_real_code() -> None:
    for name in MOVED:
        shim = (REPO / "scripts" / "assistant_eval" / f"{name}.py").read_text()
        assert len(shim.splitlines()) < 25 and "sys.modules[__name__]" in shim
        assert (REPO / "assistant" / f"{name}.py").stat().st_size > 400
    assert (REPO / "assistant" / "records.py").exists()


def test_trim_record_is_the_one_in_assistant_records_and_stays_importable_from_cases() -> None:
    from assistant import records

    assert case_builder.trim_record is records.trim_record
    assert case_builder.DESCRIPTION_LIMIT == records.DESCRIPTION_LIMIT == 1500
    entry = {
        "name": "f",
        "display_name": "F",
        "domain_label": "D",
        "summary": "s",
        "description": "x" * 2000,
        "params": [{"name": "a", "type": "number", "required": True, "default": None}],
    }
    record = records.trim_record(entry)
    assert len(record["description"]) == 1500 and record["parameters"][0]["name"] == "a"
    assert record["formula_latex"] is None and record["domain"] == "D"


def test_the_package_has_a_docstring_and_no_module_imports_a_network_library() -> None:
    """PR 2 adds the one module allowed to import `anthropic`; until then none may."""
    assert assistant.__doc__ and "kernel" in assistant.__doc__
    offenders = []
    for path in sorted((REPO / "assistant").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            for name in names:
                if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    offenders.append(f"{path.relative_to(REPO)}: {name}")
    assert not offenders, offenders


def test_the_prompt_version_and_system_prompt_are_unchanged() -> None:
    assert prompts.PROMPT_VERSION == "v4-2026-11-09"
    digest = hashlib.sha256(prompts.SYSTEM_PROMPT.encode()).hexdigest()
    assert digest == SYSTEM_PROMPT_SHA256


def phase0_cases() -> list[dict[str, Any]]:
    from main import create_app  # the example cases need the live request schemas

    catalogue = case_builder.load_catalogue()
    schemas = case_builder.schemas_from_openapi(create_app().openapi(), catalogue)
    return case_builder.build_cases(catalogue, case_builder.load_specs(), schemas)


def test_the_graders_give_the_same_results_on_the_576_phase_0_oracle_answers() -> None:
    cases = phase0_cases()
    text = "".join(json.dumps(c, sort_keys=True) + "\n" for c in cases)
    assert len(cases) == 576
    assert hashlib.sha256(text.encode()).hexdigest() == PHASE0_CASES_SHA256
    results = sorted(
        ({"id": c["id"], **graders.grade(c, graders.oracle_text(c)).as_dict()} for c in cases),
        key=lambda r: r["id"],
    )
    assert all(r["passed"] for r in results)
    digest = hashlib.sha256(json.dumps(results, sort_keys=True).encode()).hexdigest()
    assert digest == ORACLE_GRADES_SHA256

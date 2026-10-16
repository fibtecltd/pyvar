"""Every worked example printed in a domain skill is a real request that works.

Reasoning:
- The skills tell Claude "these requests were run against the real API". This test
  keeps that sentence true: each example in scripts/skill_specs/*.json is POSTed to
  the real FastAPI app (in-process, a real JWT) and must return 200 with every
  response key the skill documents. A renamed parameter or response field fails here
  before a user's Claude copies a request that no longer works.
- `"<returns:N>"` in a spec stands for N synthetic daily log-returns (the skill prints
  it as a placeholder; the test substitutes the deterministic fixture series).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from api.middleware.auth import create_access_token
from ingestion.fixtures import generate_gbm_returns
from main import create_app

REPO = Path(__file__).resolve().parent.parent
SPEC_DIR = REPO / "scripts" / "skill_specs"
CATALOG = {
    (e["domain"], e["name"]): e for e in json.loads((REPO / "portal/functions.json").read_text())
}
PLACEHOLDER = re.compile(r"<returns:(\d+)>")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        match = PLACEHOLDER.fullmatch(value)
        if match:
            series = generate_gbm_returns(int(match.group(1)), mu=0.0004, sigma=0.011, seed=7)
            return [float(x) for x in series]
        return value
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def _cases() -> list[Any]:
    cases = []
    for spec_path in sorted(SPEC_DIR.glob("*.json")):
        spec = json.loads(spec_path.read_text())
        for i, example in enumerate(spec["examples"], 1):
            for call in example["calls"]:
                cases.append(
                    pytest.param(
                        spec["domain"],
                        call,
                        id=f"{spec['skill']}-ex{i}-{call['function']}",
                    )
                )
    return cases


@pytest.fixture(scope="module")
def token() -> str:
    # enterprise is exempt from the per-user daily quota, so the sweep cannot 429
    return create_access_token("skill-examples", "enterprise")


@pytest.mark.parametrize(("domain", "call"), _cases())
async def test_skill_example_runs_and_returns_the_documented_keys(
    domain: str, call: dict[str, Any], token: str
) -> None:
    entry = CATALOG[(domain, call["function"])]
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://t"
    ) as client:
        response = await client.post(
            entry["path"],
            json=_expand(call["request"]),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    missing = [key for key in call["returns"] if key not in body]
    assert not missing, f"{call['function']} no longer returns {missing}"
    # the request only uses parameters the catalog knows about
    known = {p["name"] for p in entry["params"]}
    assert set(call["request"]) <= known

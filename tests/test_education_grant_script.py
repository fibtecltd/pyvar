"""tests/test_education_grant_script.py — scripts/education_grant.py, the operator's one command (A2 PR 1).

Reasoning:
- The script is a client of the real /internal/admin/education routes. Its HTTP call is replaced by a bridge into
  the REAL application (same process, in-memory SQLite), so what is tested is the pair: the token the script
  signs is the token the API accepts (audience, lifetime, no tier), the script says "confirmed" only when the
  API's own list shows the change, and an API refusal ends in exit code 5 with the API's reason.
- No AWS: the secret comes from stdin (`--secret-stdin`), as in tests/test_api_key_scripts.py, and the secret
  must appear nowhere (not in the ledger, not on stderr, not on stdout).
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.middleware import api_keys as keys_module
from config import get_settings
from main import create_app
from storage.models import ApiKey, Base, BillingEvent, User
from tests.test_api_keys import FakeRedis

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


script = load("education_grant")
cfg = get_settings()
SECRET = "dummy-secret-for-education-tests-0123456789abcdefghijklmnop"
BASE = "http://127.0.0.1:9"


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    """The real app on in-memory SQLite, and a bridge that carries the script's calls into it."""
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[User.__table__, ApiKey.__table__, BillingEvent.__table__]
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.get_running_loop()
    seen: list[dict[str, Any]] = []
    override: dict[str, Any] = {}

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:

        def bridge(method: str, url: str, token: str, body: dict | None = None, timeout: int = 30):
            seen.append({"method": method, "url": url, "token": token})
            if override.get("fake") and method == "POST" and url.endswith("/grant"):
                return 200, override["fake"]  # a lying API: says granted, changes nothing
            path = url[len(BASE) :]
            future = asyncio.run_coroutine_threadsafe(
                http.request(method, path, json=body, headers={"Authorization": f"Bearer {token}"}),
                loop,
            )
            response = future.result(timeout=30)
            return response.status_code, (response.json() if response.content else None)

        monkeypatch.setattr(script, "api_request", bridge)
        with (
            patch.object(cfg, "jwt_secret", SECRET),
            patch.object(cfg, "education_tier_enabled", True),
            patch("api.routes.internal.get_sessionmaker", return_value=maker),
            patch("api.middleware.api_keys.get_sessionmaker", return_value=maker),
            patch.object(keys_module, "_redis", return_value=FakeRedis()),
            patch("api.education_grants.send_tier_change_email"),
        ):
            yield {
                "maker": maker,
                "seen": seen,
                "override": override,
                "ledger": tmp_path / "education.jsonl",
                "monkeypatch": monkeypatch,
            }
    await engine.dispose()


async def add_user(world, name: str, tier: str = "free") -> None:
    async with world["maker"]() as session:
        session.add(
            User(
                external_id=f"ext-{name}",
                email=f"{name}@uni.ac.uk",
                tier=tier,
                email_verified=True,
            )
        )
        await session.commit()


async def run(world, *argv: str, stdin: str = SECRET) -> tuple[int, str, str]:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO(stdin))
    args = [
        *argv,
        "--secret-stdin",
        "--base-url",
        BASE,
        "--ledger",
        str(world["ledger"]),
    ]
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(script.main, args, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def grant_args(name: str = "ada", *extra: str) -> list[str]:
    return [
        "grant",
        "--env",
        "dev",
        "--email",
        f"{name}@uni.ac.uk",
        "--months",
        "6",
        "--cohort",
        "ucl-2026",
        *extra,
    ]


async def test_grant_signs_a_token_the_api_accepts_and_confirms_the_change(world) -> None:
    await add_user(world, "ada")
    code, out, err = await run(world, *grant_args())
    assert code == 0, err
    assert "ada@uni.ac.uk: education access until" in out and "confirmed by the API" in out
    async with world["maker"]() as session:
        user = (await session.execute(select(User))).scalar_one()
    assert user.tier == "education"

    # The token it presented is exactly the shape the API's decoder requires.
    token = world["seen"][0]["token"]
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], audience="pyvar-admin")
    assert claims["aud"] == "pyvar-admin" and "tier" not in claims
    assert claims["exp"] - claims["iat"] == 600 and claims["sub"] and claims["jti"]


async def test_grant_then_list_extend_revoke_end_to_end(world) -> None:
    await add_user(world, "ada")
    assert (await run(world, *grant_args()))[0] == 0

    code, out, _ = await run(world, "list", "--env", "dev")
    assert code == 0 and "active 1 of 25" in out and "ada@uni.ac.uk" in out and "ucl-2026" in out

    code, out, err = await run(
        world,
        "extend",
        "--env",
        "dev",
        "--email",
        "ada@uni.ac.uk",
        "--months",
        "2",
        "--cohort",
        "ucl-2026",
    )
    assert code == 0, err

    code, out, _ = await run(
        world, "revoke", "--env", "dev", "--email", "ada@uni.ac.uk", "--cohort", "ucl-2026"
    )
    assert code == 0 and "back on the Free tier" in out
    async with world["maker"]() as session:
        assert (await session.execute(select(User))).scalar_one().tier == "free"


async def test_suspend_all_needs_its_confirmation_and_then_ends_every_grant(world) -> None:
    await add_user(world, "ada")
    await run(world, *grant_args())
    code, out, err = await run(world, "suspend-all", "--env", "dev")
    assert code == 2 and "--yes-all" in err, (code, out, err)
    assert (
        len(world["seen"]) == 2
    )  # the grant and its confirmation; nothing was sent for the refused command
    code, out, _ = await run(world, "suspend-all", "--env", "dev", "--yes-all")
    assert code == 0 and "ended 1 active grant" in out


async def test_an_api_refusal_ends_in_exit_5_with_the_apis_reason(world) -> None:
    await add_user(world, "ada", tier="pro")
    code, out, err = await run(world, *grant_args())
    assert code == 5
    assert "HTTP 409" in err and "'pro' tier" in err
    assert out == ""
    assert SECRET not in err and world["seen"][0]["token"] not in err


async def test_with_the_flag_off_the_503_is_explained(world) -> None:
    await add_user(world, "ada")
    with patch.object(cfg, "education_tier_enabled", False):
        code, _, err = await run(world, *grant_args())
    assert code == 5 and "HTTP 503" in err and "switched off" in err


async def test_it_does_not_say_confirmed_when_the_list_disagrees(world) -> None:
    await add_user(world, "ada")
    world["override"]["fake"] = {
        "email": "ada@uni.ac.uk",
        "tier": "education",
        "expires_at": "2027-05-01T00:00:00+00:00",
    }
    code, out, err = await run(world, *grant_args())
    assert code == 5 and "could not confirm" in err
    assert "confirmed by the API" not in out
    assert not world["ledger"].exists()  # nothing recorded for a change that did not happen


async def test_the_ledger_records_who_what_and_when_and_never_a_secret_or_token(world) -> None:
    await add_user(world, "ada")
    await run(world, *grant_args(), "--operator", "fibtec-ops")
    lines = [json.loads(line) for line in world["ledger"].read_text().splitlines()]
    assert len(lines) == 1
    record = lines[0]
    assert record["action"] == "grant" and record["env"] == "dev" and record["by"] == "fibtec-ops"
    assert record["cohort"] == "ucl-2026" and record["months"] == 6 and record["expires"]
    raw = world["ledger"].read_text()
    assert SECRET not in raw and world["seen"][0]["token"] not in raw
    assert oct(world["ledger"].stat().st_mode & 0o777) == "0o600"


async def test_the_ledger_never_holds_an_e_mail_address(world) -> None:
    """A file on a laptop that names people is a risk the API's own record does not need
    (docs/plan-education-tier.md section 12): not on a grant, an extension or a revoke."""
    await add_user(world, "ada")
    assert (await run(world, *grant_args()))[0] == 0
    assert (
        await run(
            world,
            "extend",
            "--env",
            "dev",
            "--email",
            "ada@uni.ac.uk",
            "--months",
            "2",
            "--cohort",
            "ucl-2026",
        )
    )[0] == 0
    assert (
        await run(
            world, "revoke", "--env", "dev", "--email", "ada@uni.ac.uk", "--cohort", "ucl-2026"
        )
    )[0] == 0
    raw = world["ledger"].read_text()
    assert len(raw.splitlines()) == 3
    assert "ada" not in raw and "@" not in raw and "uni.ac.uk" not in raw
    assert all("email" not in json.loads(line) for line in raw.splitlines())


# ── guards that never reach the API ───────────────────────────────────────────────────────────────────────


async def test_prod_needs_its_flag_and_no_call_is_made(world) -> None:
    code, _, err = await run(world, "list", "--env", "prod")
    assert code == 2 and "--yes-prod" in err and world["seen"] == []


async def test_a_missing_environment_is_refused(world) -> None:
    code, _, err = await run(world, "list")
    assert code == 2 and "--env is required" in err


@pytest.mark.parametrize("months", ["0", "13"])
async def test_months_outside_the_range_are_refused_before_any_call(world, months) -> None:
    args = grant_args()
    args[args.index("6")] = months
    code, _, err = await run(world, *args)
    assert code == 2 and "between 1 and 12" in err and world["seen"] == []


async def test_a_weak_or_public_secret_is_refused_and_never_echoed(world) -> None:
    for weak in ("weak-secret-xyz", "change-me-in-production"):
        code, out, err = await run(world, "list", "--env", "dev", stdin=weak)
        assert code == 3
        assert "weak-secret-xyz" not in out + err
    assert world["seen"] == []


async def test_the_base_url_may_only_be_loopback(world) -> None:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO(SECRET))
    code = await asyncio.to_thread(
        script.main, ["list", "--env", "dev", "--secret-stdin", "--base-url", "http://example.com"]
    )
    assert code == 2 and world["seen"] == []


async def test_an_operator_label_must_look_like_a_label(world) -> None:
    code, _, err = await run(world, "list", "--env", "dev", "--operator", "a b")
    assert code == 2 and "--operator" in err and world["seen"] == []

"""tests/test_assistant_allow_script.py — scripts/assistant_allow.py, the command that manages who may ask the typed
assistant a question while the allowlist is on.

Reasoning:
- Same harness as tests/test_account_erase_script.py: the script's HTTP call is replaced by a bridge into the REAL
  application (in-process, in-memory SQLite, a fake Redis set), so what is tested is the pair: the token the script
  signs is the token the API accepts, and the script says "allowed" or "removed" only when a second call to the API
  confirms it.
- allow, remove and clear are dry runs unless `--yes`; prod needs `--yes-prod`; and the address, the secret and the
  token appear nowhere in what it prints or records (the ledger holds the account identifier and the set size).
- No AWS: the secret comes from stdin (`--secret-stdin`).
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
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.assistant import allowlist
from api.assistant.store import ALLOW_KEY
from config import get_settings
from main import create_app
from storage.models import Base, User
from tests.test_assistant_allow_admin import FakeSetRedis

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


script = load("assistant_allow")
cfg = get_settings()
SECRET = "dummy-secret-for-allow-tests-0123456789abcdefghijklmnopqrstuvwx"
BASE = "http://127.0.0.1:9"
ADDRESS = "zz-sentinel-allow@uni.ac.uk"
KEY = ALLOW_KEY


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[User.__table__]))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.get_running_loop()
    seen: list[dict[str, Any]] = []
    override: dict[str, Any] = {}
    fake = FakeSetRedis()

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:

        def bridge(method: str, url: str, token: str, body: dict | None = None, timeout: int = 30):
            seen.append({"method": method, "url": url, "token": token, "body": body})
            if override.get("fake_apply") and body and body.get("apply"):
                return 200, override["fake_apply"]  # a lying API: says done, changes nothing
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
            patch("api.routes.internal.get_sessionmaker", return_value=maker),
            patch.object(allowlist, "_redis", return_value=fake),
        ):
            yield {
                "maker": maker,
                "seen": seen,
                "override": override,
                "redis": fake,
                "ledger": tmp_path / "assistant_allow.jsonl",
                "monkeypatch": monkeypatch,
            }
    await engine.dispose()


async def add_user(world, tier: str = "free") -> None:
    async with world["maker"]() as session:
        session.add(User(external_id="ext-ada", email=ADDRESS, tier=tier, email_verified=True))
        await session.commit()


async def run(world, *action: str, env: str = "dev") -> tuple[int, str, str]:
    """Global options first (argparse wants them before the action), then the action and its options."""
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO(SECRET))
    args = [
        "--env",
        env,
        "--secret-stdin",
        "--base-url",
        BASE,
        "--ledger",
        str(world["ledger"]),
        *action,
    ]
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(script.main, args, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


async def test_allow_is_a_dry_run_unless_told_otherwise(world) -> None:
    await add_user(world)
    code, out, err = await run(world, "allow", "--email", ADDRESS)
    assert code == 0 and err == ""
    assert "dry run" in out and "ext-ada" in out and "Add --yes to allow it" in out
    assert world["redis"].sets == {} and not world["ledger"].exists()


async def test_allow_with_yes_adds_the_account_and_confirms_it(world) -> None:
    await add_user(world)
    code, out, err = await run(world, "allow", "--email", ADDRESS, "--yes")
    assert code == 0 and err == ""
    assert out.startswith("allowed: account ext-ada (free)") and "confirmed by the API" in out
    assert world["redis"].sets == {KEY: {"ext-ada"}}


async def test_remove_with_yes_takes_the_account_out_and_confirms_it(world) -> None:
    await add_user(world)
    world["redis"].sets[KEY] = {"ext-ada", "ext-other"}
    code, out, _ = await run(world, "remove", "--email", ADDRESS, "--yes")
    assert code == 0 and out.startswith("removed: account ext-ada") and "1 in the allowlist" in out
    assert world["redis"].sets[KEY] == {"ext-other"}


async def test_list_prints_identifiers_only(world) -> None:
    world["redis"].sets[KEY] = {"ext-b", "ext-a"}
    code, out, _ = await run(world, "list")
    assert code == 0 and "2 account(s)" in out
    assert out.index("ext-a") < out.index("ext-b") and "@" not in out


async def test_clear_is_a_dry_run_then_empties_and_confirms(world) -> None:
    world["redis"].sets[KEY] = {"ext-a", "ext-b"}
    code, out, _ = await run(world, "clear")
    assert code == 0 and "2 account(s) would be removed" in out and "Add --yes" in out
    assert world["redis"].sets[KEY] == {"ext-a", "ext-b"}
    code, out, _ = await run(world, "clear", "--yes")
    assert code == 0 and "cleared: 2 account(s) removed" in out and "the set is empty" in out
    assert world["redis"].sets == {}


async def test_it_says_when_the_allowlist_is_off_in_that_environment(world) -> None:
    world["monkeypatch"].setattr(cfg, "assistant_allowlist_enabled", False)
    _, out, _ = await run(world, "list")
    assert "the allowlist is OFF in this environment" in out
    world["monkeypatch"].setattr(cfg, "assistant_allowlist_enabled", True)
    _, out, _ = await run(world, "list")
    assert "allowlist is OFF" not in out


async def test_the_ledger_names_the_account_not_the_person_and_holds_no_secret(world) -> None:
    await add_user(world)
    await run(world, "allow", "--email", ADDRESS, "--yes")
    (line,) = world["ledger"].read_text().splitlines()
    record = json.loads(line)
    assert record["action"] == "allow" and record["account"] == "ext-ada"
    assert record["members"] == 1 and record["env"] == "dev"
    assert "sentinel" not in line and SECRET not in line and "uni.ac.uk" not in line


async def test_the_address_the_secret_and_the_token_are_never_printed(world) -> None:
    await add_user(world)
    _, out, err = await run(world, "allow", "--email", ADDRESS, "--yes")
    token = world["seen"][0]["token"]
    for text in (out, err):
        assert "sentinel" not in text and SECRET not in text and token not in text


async def test_it_does_not_say_allowed_when_the_api_does_not_show_it(world) -> None:
    await add_user(world)
    world["override"]["fake_apply"] = {
        "action": "allow",
        "applied": True,
        "enabled": True,
        "account_id": "ext-ada",
        "tier": "free",
        "was_allowed": False,
        "members": 1,
        "account_ids": [],
    }
    code, out, err = await run(world, "allow", "--email", ADDRESS, "--yes")
    assert code == 5 and "allowed:" not in out and "does not show it" in err
    assert not world["ledger"].exists()


async def test_an_unknown_address_is_refused_without_echoing_it(world) -> None:
    code, out, err = await run(world, "allow", "--email", ADDRESS, "--yes")
    assert code == 5 and "no account has this address" in err.lower()
    assert "sentinel" not in out + err


async def test_an_unreachable_allowlist_is_refused_and_says_nothing_was_changed(world) -> None:
    await add_user(world)
    world["redis"].down = True
    code, _, err = await run(world, "allow", "--email", ADDRESS, "--yes")
    assert code == 5 and "could not be reached" in err


async def test_prod_needs_its_flag_and_no_call_is_made(world) -> None:
    code, _, err = await run(world, "list", env="prod")
    assert code == 2 and "--yes-prod" in err and world["seen"] == []


async def test_a_weak_secret_is_refused_and_never_echoed(world) -> None:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO("weak-secret-xyz"))
    out, err = io.StringIO(), io.StringIO()
    argv = [
        "--env",
        "dev",
        "--secret-stdin",
        "--base-url",
        BASE,
        "--ledger",
        str(world["ledger"]),
        "list",
    ]
    code = await asyncio.to_thread(script.main, argv, stdout=out, stderr=err)
    assert code == 3 and "weak-secret-xyz" not in out.getvalue() + err.getvalue()
    assert world["seen"] == []


def test_allow_and_remove_need_an_email_and_the_environment_has_no_default() -> None:
    parser = script.build_parser()
    for argv in (["--env", "dev", "allow"], ["--env", "dev", "remove"]):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)

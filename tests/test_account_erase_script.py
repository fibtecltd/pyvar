"""tests/test_account_erase_script.py — scripts/account_erase.py, the command behind "delete your account".

Reasoning:
- Same harness as tests/test_education_grant_script.py: the script's HTTP call is replaced by a bridge into the REAL
  application (in-process, in-memory SQLite), so what is tested is the pair: the token the script signs is the token
  the API accepts, and the script says "erased" only when the API itself no longer matches the address.
- Erasure is irreversible in effect, so: a dry run unless `--yes`; prod needs `--yes-prod`; a paid account is refused
  with the API's reason; and the address, the secret and the token appear nowhere in what it prints or records
  (the ledger holds the account identifier and a count of keys, nothing that names a person).
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

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.middleware import api_keys as keys_module
from api.middleware.api_keys import generate_key
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


script = load("account_erase")
cfg = get_settings()
SECRET = "dummy-secret-for-erase-tests-0123456789abcdefghijklmnopqrstuv"
BASE = "http://127.0.0.1:9"
ADDRESS = "zz-sentinel-erase@uni.ac.uk"


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
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
            seen.append({"method": method, "url": url, "token": token, "body": body})
            if override.get("fake_apply") and body and body.get("apply"):
                return 200, override["fake_apply"]  # a lying API: says erased, changes nothing
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
            patch("api.middleware.api_keys.get_sessionmaker", return_value=maker),
            patch.object(keys_module, "_redis", return_value=FakeRedis()),
        ):
            yield {
                "maker": maker,
                "seen": seen,
                "override": override,
                "ledger": tmp_path / "erasures.jsonl",
                "monkeypatch": monkeypatch,
            }
    await engine.dispose()


async def add_user(world, tier: str = "free", keys: int = 2) -> None:
    async with world["maker"]() as session:
        user = User(external_id="ext-ada", email=ADDRESS, tier=tier, email_verified=True)
        session.add(user)
        await session.flush()
        for index in range(keys):
            _, prefix, digest = generate_key()
            session.add(
                ApiKey(user_id=user.id, name=f"laptop {index}", prefix=prefix, key_hash=digest)
            )
        await session.commit()


async def run(world, *argv: str) -> tuple[int, str, str]:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO(SECRET))
    args = [*argv, "--secret-stdin", "--base-url", BASE, "--ledger", str(world["ledger"])]
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(script.main, args, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def erase_args(*extra: str) -> list[str]:
    return ["--env", "dev", "--email", ADDRESS, *extra]


async def the_user(world) -> User:
    async with world["maker"]() as session:
        return (await session.execute(select(User))).scalar_one()


async def test_it_is_a_dry_run_unless_told_otherwise(world) -> None:
    await add_user(world)
    code, out, err = await run(world, *erase_args())
    assert code == 0, err
    assert "dry run: account ext-ada (free): 2 live key(s) to switch off" in out
    assert "Add --yes to do it" in out
    assert (await the_user(world)).email == ADDRESS and not world["ledger"].exists()
    assert ADDRESS not in out + err


async def test_with_yes_it_erases_confirms_and_lists_what_is_left_to_do(world) -> None:
    await add_user(world)
    code, out, err = await run(world, *erase_args("--yes", "--operator", "fibtec-ops"))
    assert code == 0, err
    assert "erased: account ext-ada" in out and "confirmed by the API" in out
    assert "the company mailbox" in out and "the requests log" in out
    assert "ext-ada" in out  # the handle for searching logs and Sentry
    assert ADDRESS not in out + err

    user = await the_user(world)
    assert user.email is None
    async with world["maker"]() as session:
        keys = list((await session.execute(select(ApiKey))).scalars())
    assert len(keys) == 2 and all(k.revoked_at and k.name == "erased" for k in keys)

    token = world["seen"][0]["token"]
    claims = jwt.decode(token, SECRET, algorithms=["HS256"], audience="pyvar-admin")
    assert claims["aud"] == "pyvar-admin" and "tier" not in claims and claims["sub"] == "fibtec-ops"


async def test_the_ledger_names_the_account_not_the_person_and_holds_no_secret(world) -> None:
    await add_user(world)
    await run(world, *erase_args("--yes", "--operator", "fibtec-ops"))
    raw = world["ledger"].read_text()
    (record,) = [json.loads(line) for line in raw.splitlines()]
    assert record["action"] == "erase" and record["account"] == "ext-ada"
    assert record["keys_revoked"] == 2 and record["by"] == "fibtec-ops" and record["env"] == "dev"
    assert "zz-sentinel" not in raw and "uni.ac.uk" not in raw and "@" not in raw
    assert SECRET not in raw and all(c["token"] not in raw for c in world["seen"])
    assert oct(world["ledger"].stat().st_mode & 0o777) == "0o600"


async def test_it_does_not_say_erased_when_the_address_still_matches(world) -> None:
    await add_user(world)
    world["override"]["fake_apply"] = {
        "account_id": "ext-ada",
        "old_tier": "free",
        "keys_revoked": 2,
        "keys_renamed": 2,
        "stripe_linked": False,
        "google_sign_in": False,
        "applied": True,
    }
    code, out, err = await run(world, *erase_args("--yes"))
    assert code == 5 and "still matches" in err
    assert "erased:" not in out and not world["ledger"].exists()


async def test_a_paid_account_is_refused_with_the_apis_reason(world) -> None:
    await add_user(world, tier="pro")
    code, out, err = await run(world, *erase_args("--yes"))
    assert code == 5 and "HTTP 409" in err and "pro account" in err
    assert out == "" and ADDRESS not in err and (await the_user(world)).email == ADDRESS


async def test_an_unknown_address_is_refused_without_echoing_it(world) -> None:
    code, out, err = await run(world, *erase_args())
    assert code == 5 and "HTTP 404" in err and "no account has this address" in err.lower()
    assert ADDRESS not in out + err


async def test_stripe_and_google_leftovers_are_reported(world) -> None:
    async with world["maker"]() as session:
        session.add(
            User(
                external_id="google:99",
                email=ADDRESS,
                tier="free",
                email_verified=True,
                stripe_customer_id="cus_1",
            )
        )
        await session.commit()
    code, out, _ = await run(world, *erase_args("--yes"))
    assert code == 0
    assert "Stripe: this account was linked to a Stripe customer" in out
    assert "signed up with Google" in out


async def test_prod_needs_its_flag_and_no_call_is_made(world) -> None:
    code, _, err = await run(world, "--env", "prod", "--email", ADDRESS)
    assert code == 2 and "--yes-prod" in err and world["seen"] == []


async def test_a_weak_secret_is_refused_and_never_echoed(world) -> None:
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO("weak-secret-xyz"))
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(
        script.main,
        [*erase_args(), "--secret-stdin", "--base-url", BASE],
        stdout=out,
        stderr=err,
    )
    assert code == 3 and "weak-secret-xyz" not in out.getvalue() + err.getvalue()
    assert world["seen"] == []

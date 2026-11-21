"""tests/script_world.py — a harness that runs an operator script against the REAL application, in process.

Reasoning:
- tests/test_education_grant_script.py and tests/test_account_erase_script.py each carry a copy of this bridge: the
  script's HTTP call (`api_request`) is replaced by a call into the real FastAPI app over an in-memory SQLite
  database, so what is tested is the pair: the token the script signs is the token the API accepts, and what the
  script reports is what the API did. The two scripts added with the six-year clean-up and the data-access export
  (scripts/audit_cleanup.py, scripts/account_export.py) share this one copy instead of making a third and fourth.
- `override` lets a test make the "API" lie or misbehave for one call (a hook that sees the request and may return
  its own answer), which is how "it does not say done when it is not" is proved.
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from api.middleware import api_keys as keys_module
from config import get_settings
from main import create_app
from storage.models import ApiKey, Base, BillingEvent, User, VaRJob
from tests.test_api_keys import FakeRedis

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SECRET = "dummy-secret-for-script-tests-0123456789abcdefghijklmnopqrstuvwxyz"
BASE = "http://127.0.0.1:9"


def load_script(name: str) -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@asynccontextmanager
async def script_world(
    script: ModuleType, tmp_path: Path, monkeypatch: Any, ledger_name: str
) -> AsyncIterator[dict[str, Any]]:
    """Yield {maker, seen, hook, ledger, monkeypatch}; `seen` lists every call the script made.

    `hook`, if a test sets it, is called as hook(body) -> (status, data) | None before the real app is asked;
    a non-None answer replaces the app's.
    """
    cfg = get_settings()
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[User.__table__, ApiKey.__table__, BillingEvent.__table__, VaRJob.__table__],
            )
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    loop = asyncio.get_running_loop()
    seen: list[dict[str, Any]] = []
    state: dict[str, Callable[[dict[str, Any]], tuple[int, Any] | None] | None] = {"hook": None}

    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as http:

        def bridge(method: str, url: str, token: str, body: dict | None = None, timeout: int = 30):
            seen.append({"method": method, "url": url, "token": token, "body": body})
            hook = state["hook"]
            if hook is not None and body is not None:
                answer = hook(body)
                if answer is not None:
                    return answer
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
            world: dict[str, Any] = {
                "maker": maker,
                "seen": seen,
                "state": state,
                "ledger": tmp_path / ledger_name,
                "monkeypatch": monkeypatch,
            }
            yield world
    await engine.dispose()


async def run_script(script: ModuleType, world: dict[str, Any], *argv: str) -> tuple[int, str, str]:
    """Run `script.main` with the secret on stdin, against the harness; return (exit code, stdout, stderr)."""
    world["monkeypatch"].setattr(sys, "stdin", io.StringIO(SECRET))
    args = [*argv, "--secret-stdin", "--base-url", BASE, "--ledger", str(world["ledger"])]
    out, err = io.StringIO(), io.StringIO()
    code = await asyncio.to_thread(script.main, args, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()

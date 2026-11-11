"""/public/config's assistant fields, the bank mount and its Cache-Control header (api/assistant_bank.py).

Reasoning:
- The widget appears only when the setting is on AND a complete bank is on disk, so every other combination
  (no manifest, complete=false, a bad version string, a missing directory, a malformed file, the setting off)
  is a test that the answer is "disabled".
- The mount is exercised through create_app() with the bank directory pointed at a temp directory, over httpx
  as in tests/test_api.py. It must sit before the portal catch-all, must not be a reserved API prefix, and must
  not let a request escape its directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import main as main_module
from api import assistant_bank
from api.routes import public_data as public_data_module

VERSION = "v4-2026-11-09-0dbf72ce"


def write_bank(
    root: Path, *, complete: bool = True, version: str = VERSION, make_dir: bool = True
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(json.dumps({"bank_version": version, "complete": complete}))
    if make_dir and version not in ("", ".", ".."):
        (root / version).mkdir(exist_ok=True)
        (root / version / "some_function.json").write_text(json.dumps({"explain": {"text": "x"}}))


@pytest.fixture
def bank_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "bank"
    monkeypatch.setattr(assistant_bank, "BANK_DIR", root)
    monkeypatch.setattr(main_module, "BANK_DIR", root)
    assistant_bank._cache.clear()
    yield root
    assistant_bank._cache.clear()


@pytest.fixture
def app(bank_root: Path) -> Any:
    return main_module.create_app()


async def get(app: Any, path: str, method: str = "GET", **kwargs: Any) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


async def config(app: Any) -> dict[str, Any]:
    response = await get(app, "/public/config")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_the_assistant_is_off_by_default(app: Any) -> None:
    body = await config(app)
    assert body["assistant_enabled"] is False and body["assistant_bank_version"] == ""
    assert body["google_sign_in_enabled"] is False  # the existing fields are still there


@pytest.mark.asyncio
async def test_the_assistant_is_on_only_with_the_setting_and_a_complete_bank(
    app: Any, bank_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(public_data_module.cfg, "assistant_enabled", True)
    assert (await config(app))["assistant_enabled"] is False  # no manifest yet
    write_bank(bank_root)
    body = await config(app)
    assert body["assistant_enabled"] is True and body["assistant_bank_version"] == VERSION
    monkeypatch.setattr(public_data_module.cfg, "assistant_enabled", False)
    off = await config(app)  # a complete bank does not switch it on by itself
    assert off["assistant_enabled"] is False and off["assistant_bank_version"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"complete": False},
        {"make_dir": False},
        {"version": "../escape"},
        {"version": "has space"},
        {"version": ".."},
        {"version": ""},
    ],
)
async def test_an_unusable_bank_reads_as_disabled(
    app: Any, bank_root: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    monkeypatch.setattr(public_data_module.cfg, "assistant_enabled", True)
    write_bank(bank_root, **kwargs)
    body = await config(app)
    assert body["assistant_enabled"] is False and body["assistant_bank_version"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content", ["not json", "[1, 2]", '{"bank_version": 7, "complete": true}', "{}"]
)
async def test_a_malformed_manifest_reads_as_disabled(
    app: Any, bank_root: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    monkeypatch.setattr(public_data_module.cfg, "assistant_enabled", True)
    bank_root.mkdir(parents=True)
    (bank_root / "manifest.json").write_text(content)
    assert (await config(app))["assistant_enabled"] is False


def test_the_manifest_is_read_again_only_when_it_changes(
    bank_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_bank(bank_root)
    reads: list[Path] = []
    real = assistant_bank._read_version

    def counting(directory: Path) -> str:
        reads.append(directory)
        return real(directory)

    monkeypatch.setattr(assistant_bank, "_read_version", counting)
    assert [assistant_bank.served_bank_version() for _ in range(5)] == [VERSION] * 5
    assert len(reads) == 1  # one read for five requests
    manifest = bank_root / "manifest.json"
    manifest.write_text(json.dumps({"bank_version": VERSION, "complete": False}))
    stat = manifest.stat()
    os.utime(manifest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert assistant_bank.served_bank_version() == ""
    assert len(reads) == 2
    manifest.unlink()
    assert assistant_bank.served_bank_version() == "" and len(reads) == 2  # a stat, no read


def test_a_version_directory_that_is_removed_stops_being_served(bank_root: Path) -> None:
    write_bank(bank_root)
    assert assistant_bank.served_bank_version() == VERSION
    for path in (bank_root / VERSION).iterdir():
        path.unlink()
    (bank_root / VERSION).rmdir()
    assert assistant_bank.served_bank_version() == ""


@pytest.mark.asyncio
async def test_bank_files_carry_a_one_hour_public_cache_header(app: Any, bank_root: Path) -> None:
    write_bank(bank_root)
    response = await get(app, f"/assistant/bank/{VERSION}/some_function.json")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.json() == {"explain": {"text": "x"}}
    head = await get(app, f"/assistant/bank/{VERSION}/some_function.json", method="HEAD")
    assert head.status_code == 200 and head.headers["cache-control"] == "public, max-age=3600"
    again = await get(
        app,
        f"/assistant/bank/{VERSION}/some_function.json",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert again.status_code == 304
    manifest = await get(app, "/assistant/bank/manifest.json")
    assert (
        manifest.status_code == 200 and manifest.headers["cache-control"] == "public, max-age=3600"
    )


@pytest.mark.asyncio
async def test_a_missing_bank_file_or_directory_is_a_plain_404(app: Any, bank_root: Path) -> None:
    missing_dir = await get(app, f"/assistant/bank/{VERSION}/some_function.json")
    assert missing_dir.status_code == 404  # the bank directory does not exist yet
    write_bank(bank_root)
    missing_file = await get(app, f"/assistant/bank/{VERSION}/nope.json")
    assert missing_file.status_code == 404 and "max-age" not in missing_file.headers.get(
        "cache-control", ""
    )


@pytest.mark.asyncio
async def test_a_request_cannot_leave_the_bank_directory(app: Any, bank_root: Path) -> None:
    write_bank(bank_root)
    for path in (
        "/assistant/bank/%2e%2e/%2e%2e/config.py",
        "/assistant/bank/..%2f..%2fconfig.py",
        f"/assistant/bank/{VERSION}/%2e%2e/%2e%2e/%2e%2e/config.py",
    ):
        response = await get(app, path)
        assert response.status_code in (400, 404) and "cfg" not in response.text


@pytest.mark.asyncio
async def test_the_bank_accepts_only_get_and_head(app: Any, bank_root: Path) -> None:
    write_bank(bank_root)
    response = await get(app, f"/assistant/bank/{VERSION}/some_function.json", method="POST")
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_the_rest_of_the_portal_is_still_served_without_the_bank_header(app: Any) -> None:
    for path in ("/pyvar.js", "/assistant.js", "/", "/pyvar.css"):
        response = await get(app, path)
        assert response.status_code == 200, path
        assert "max-age=3600" not in response.headers.get("cache-control", ""), path


def test_the_bank_path_is_not_a_reserved_api_prefix() -> None:
    assert not any(
        "/assistant/bank/x.json".startswith(prefix)
        for prefix in main_module._RESERVED_PATH_PREFIXES
    )
    mounts = [getattr(r, "path", None) for r in main_module.create_app().router.routes]
    assert mounts.index("/assistant/bank") < mounts.index("")  # before the portal catch-all

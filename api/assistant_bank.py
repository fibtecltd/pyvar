"""The portal assistant's answer bank, as the API serves it: a cheap manifest read and a cached static mount.

Reasoning:
- The bank is static files built ahead of time by `python -m assistant.bank` and committed under
  portal/assistant/bank/ (docs/assistant-plan-implementation.md, section 5). The API never calls a model for it.
- `/public/config` tells the widget whether to appear and which bank version to read. It says so only when the
  setting `assistant_enabled` is on AND the manifest exists, says `complete`, and names a directory that is
  there; anything else (no bank yet, a build that stopped half way, a hand-edited manifest) reads as disabled,
  so the widget never shows buttons that lead nowhere. The home page calls /public/config on every load, so the
  manifest is re-read only when its modification time or size changes.
- The version is a path component the browser puts in a URL; it is accepted only if it is made of letters,
  digits, dot, dash and underscore.
- Files under /assistant/bank/<version>/ never change once written (the version is in the path), so they are
  served with `Cache-Control: public, max-age=3600` (the edge's own maximum, config in edge_stack.py); the
  static mount of the portal sets no cache header at all, and without one every read would reach Fargate.
  This mount is registered before the portal catch-all in main.py and is NOT a reserved API prefix.
- A bank that does not exist yet is not an error: the mount does not check its directory at start-up, and a
  request for a missing file is the usual 404 (the widget hides itself on it).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from starlette.responses import Response
from starlette.staticfiles import StaticFiles

BANK_DIR = Path(__file__).resolve().parents[1] / "portal" / "assistant" / "bank"
CACHE_CONTROL = "public, max-age=3600"
_SAFE = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")

_lock = threading.Lock()
_cache: dict[str, tuple[tuple[int, int], str]] = {}


class BankStaticFiles(StaticFiles):
    """StaticFiles that marks every file it serves as cacheable for an hour."""

    async def check_config(self) -> None:
        """Starlette raises on the first request if the directory is missing (`check_dir=False` only skips
        the check at construction). The bank is absent until its first build is committed, and that must be
        a 404 for the widget to read as "nothing here", not a 500."""
        return None

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = CACHE_CONTROL
        return response


def _read_version(bank_dir: Path) -> str:
    """The bank_version of a complete bank under `bank_dir`, else ''. Reads the manifest from disk."""
    try:
        manifest = json.loads((bank_dir / "manifest.json").read_text())
    except (OSError, ValueError):
        return ""
    if not isinstance(manifest, dict) or manifest.get("complete") is not True:
        return ""
    version = manifest.get("bank_version")
    if not isinstance(version, str) or not version or not set(version) <= _SAFE:
        return ""
    if version in (".", "..") or not (bank_dir / version).is_dir():
        return ""
    return version


def served_bank_version(bank_dir: Path | None = None) -> str:
    """The version of the complete bank on disk, or '' if there is none (cached by manifest mtime).

    Args:
        bank_dir: the bank root; defaults to portal/assistant/bank.

    Returns:
        The bank_version string, safe to put in a URL path, or an empty string.
    """
    directory = bank_dir if bank_dir is not None else BANK_DIR
    manifest = directory / "manifest.json"
    try:
        stat = os.stat(manifest)
    except OSError:
        with _lock:
            _cache.pop(str(manifest), None)
        return ""
    stamp = (stat.st_mtime_ns, stat.st_size)
    with _lock:
        hit = _cache.get(str(manifest))
    if hit is not None and hit[0] == stamp and (not hit[1] or (directory / hit[1]).is_dir()):
        return hit[1]
    version = _read_version(directory)
    with _lock:
        _cache[str(manifest)] = (stamp, version)
    return version

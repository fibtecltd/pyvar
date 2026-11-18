"""plugins/mcp/pyvar_mcp/trial.py — the no-sign-up trial: an anonymous installation ticket from pyvar.com.

Reasoning:
- With no API key configured, a first-time user can still get a few results: the first tool call asks pyvar.com
  for a ticket and keeps it in this plugin's own data directory, then runs the call through the trial routes
  (POST /api/v1/trial/..., docs/plan-trial-lane-throttle.md in the pyvar repository). A key always wins: this
  module is used only when no key is set.
- The ticket is requested LAZILY, at the first tool call that needs it (client.py), so starting the server or
  listing its tools never contacts pyvar.com and never writes a file.
- It is requested only where it is safe and expected: inside Claude Code's plugin runtime (CLAUDE_PLUGIN_DATA is
  set, which is also where the ticket is kept) and never when CI is set, where a self-issued ticket would only
  multiply tickets; there a key is required, as before.
- What is stored: one small file, install.json, in the plugin's own data directory, mode 0600 and replaced
  atomically (a temporary file, then os.replace). It holds the ticket (a signed token with no account and no
  tier), its expiry, the issue time and the API address it came from, and nothing else; a ticket from another
  address is ignored. Nothing outside that directory is touched. A lock file beside it keeps two server
  processes from asking for two tickets at once.
- What is sent: the ticket (to pyvar.com only; redirects are not followed, so it cannot be forwarded elsewhere),
  the request body of the function being run, and the allowlisted label "pyvar-mcp/<version>". The first request
  of a new ticket sends nothing but a solved puzzle.
- The proof of work is SHA-256 with a number of leading zero bits (20 normally, about a second). The client is open
  source and a native solver costs cents, so it only slows casual scripts; the server's budgets are what bound
  abuse. A challenge that asks for more than MAX_POW_BITS is refused instead of solved.
- One retry, no more: a refused ticket (401) is deleted and replaced once; a "busy" refusal (429) with a short
  Retry-After is waited out once. Any other refusal is returned to the model with the server's own words, which
  already name the free key.
- Every failure is a TrialError carrying a message a model can relay; nothing here raises a bare exception to the
  MCP layer.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import __version__
from .trial_functions import TRIAL_FUNCTIONS

REGISTER_URL = "https://www.pyvar.com#get-api-key"
CLIENT_ID = f"pyvar-mcp/{__version__}"

TICKET_FILE = "install.json"
LOCK_FILE = "install.lock"
MAX_TICKET_FILE_BYTES = 16_384
REUSE_MARGIN_SECONDS = 300  # a ticket this close to its end is replaced rather than used
LOCK_WAIT_SECONDS = 30.0
LOCK_STALE_SECONDS = 60.0
MAX_POW_BITS = 24  # the server asks for 20, or 24 in attack mode; anything higher is refused
SOLVE_BUDGET_SECONDS = 120.0
MAX_RETRY_AFTER_SECONDS = 10.0  # a longer wait is reported to the model, not slept
REQUEST_TIMEOUT_SECONDS = 30


class TrialError(Exception):
    """The trial cannot give a result. `message` is for the model and the user."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TrialHttpError(TrialError):
    """The trial route answered with a status the client passes through (a 404, 413, 422, 504 ...)."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"pyvar API error (HTTP {status_code}): {body}")
        self.status_code = status_code
        self.body = body


# ── where the trial may run ──────────────────────────────────────────────────────────────────────────────


def _ci_is_set(env: Mapping[str, str]) -> bool:
    return env.get("CI", "").strip().lower() not in ("", "0", "false", "no")


def unavailable_message(env: Mapping[str, str] | None = None) -> str | None:
    """Why the trial cannot be used here, or None when it can."""
    env = os.environ if env is None else env
    if _ci_is_set(env):
        return (
            "PYVAR_API_KEY is not set, and the no-sign-up trial is not used when CI is set. "
            f"Create a free key at {REGISTER_URL} and set PYVAR_API_KEY."
        )
    if not env.get("CLAUDE_PLUGIN_DATA"):
        return (
            "PYVAR_API_KEY is not set. Create a free key at "
            f"{REGISTER_URL} and set it in the plugin settings (the no-sign-up trial runs only "
            "inside Claude Code's plugin runtime)."
        )
    return None


def not_in_trial_message() -> str:
    return (
        f"This function needs a free pyvar API key. Without one, {len(TRIAL_FUNCTIONS)} functions "
        "work, a few calls a day (list_pyvar_functions marks them available_without_key). "
        f"Create a key at {REGISTER_URL} and set it in the plugin settings."
    )


# ── the ticket file ──────────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Ticket:
    """An anonymous installation ticket issued by pyvar.com: no account, no tier."""

    ticket: str
    expires_at: int
    base_url: str


class TicketStore:
    """install.json in the plugin's own data directory, and the lock beside it."""

    def __init__(
        self, directory: Path, base_url: str, clock: Callable[[], float] = time.time
    ) -> None:
        self.directory = directory
        self.base_url = base_url
        self._clock = clock

    @property
    def path(self) -> Path:
        return self.directory / TICKET_FILE

    def load(self) -> Ticket | None:
        """The stored ticket if it is well formed, from this address and not about to expire."""
        try:
            if self.path.stat().st_size > MAX_TICKET_FILE_BYTES:
                return None
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        ticket, expires_at, base_url = (
            data.get("ticket"),
            data.get("expires_at"),
            data.get("base_url"),
        )
        if not (isinstance(ticket, str) and ticket and isinstance(base_url, str)):
            return None
        if not isinstance(expires_at, int) or isinstance(expires_at, bool):
            return None
        if base_url != self.base_url or expires_at - self._clock() < REUSE_MARGIN_SECONDS:
            return None
        return Ticket(ticket=ticket, expires_at=expires_at, base_url=base_url)

    def save(self, ticket: Ticket) -> None:
        """Write the ticket atomically with mode 0600."""
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "ticket": ticket.ticket,
            "expires_at": ticket.expires_at,
            "issued_at": int(self._clock()),
            "base_url": ticket.base_url,
        }
        temporary = self.directory / f"{TICKET_FILE}.{os.getpid()}.tmp"
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    @contextlib.contextmanager
    def lock(self, wait_seconds: float = LOCK_WAIT_SECONDS) -> Iterator[None]:
        """Exclusive across processes: a lock file created with O_EXCL, taken over if it is stale.

        Raises:
            TrialError: another process held it for the whole wait.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        lock_path = self.directory / LOCK_FILE
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    # A file's modification time is wall-clock time, whatever clock the store was given.
                    if time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS:
                        lock_path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise TrialError(
                        "Another pyvar-mcp process is setting up the trial; try again in a moment."
                    ) from None
                time.sleep(0.05)
                continue
            os.close(descriptor)
            break
        try:
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()


# ── proof of work ────────────────────────────────────────────────────────────────────────────────────────


def solve(challenge: str, bits: int, budget_seconds: float = SOLVE_BUDGET_SECONDS) -> str:
    """A nonce for which SHA-256 of "<challenge>:<nonce>" has `bits` leading zero bits.

    Raises:
        TrialError: the budget ran out first.
    """
    target = 1 << (256 - bits)
    prefix = hashlib.sha256(f"{challenge}:".encode())
    deadline = time.monotonic() + budget_seconds
    counter = 0
    while True:
        nonce = format(counter, "x")
        candidate = prefix.copy()
        candidate.update(nonce.encode())
        if int.from_bytes(candidate.digest(), "big") < target:
            return nonce
        counter += 1
        if counter % 8192 == 0 and time.monotonic() > deadline:
            raise TrialError("Solving the sign-up puzzle took too long; try again shortly.")


# ── the network ──────────────────────────────────────────────────────────────────────────────────────────


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A ticket goes to pyvar.com and nowhere else, so a redirect is an error, never followed."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _open(request: urllib.request.Request, timeout: float) -> Any:
    return _OPENER.open(request, timeout=timeout)  # nosec B310 -- fixed https base_url


def _post(
    url: str, payload: dict[str, Any], bearer: str | None = None
) -> tuple[int, dict[str, str], str]:
    """POST JSON; returns (status, lower-cased headers, body text). A non-2xx answer is a result, not an error."""
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("X-Pyvar-Client", CLIENT_ID)
    if bearer is not None:
        request.add_header("Authorization", f"Bearer {bearer}")
    try:
        with _open(request, REQUEST_TIMEOUT_SECONDS) as response:
            return int(response.status), _headers(response.headers), response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, _headers(exc.headers), exc.read().decode()
    except urllib.error.URLError as exc:
        raise TrialError(f"Cannot reach pyvar.com: {exc.reason}") from exc


def _headers(raw: Any) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in raw.items()} if raw is not None else {}


def _json(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _retry_after(headers: Mapping[str, str]) -> float | None:
    try:
        return max(0.0, float(headers.get("retry-after", "")))
    except ValueError:
        return None


def _when(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} seconds"
    if seconds < 5400:
        return f"{round(seconds / 60)} minutes"
    return f"{round(seconds / 3600)} hours"


def _refused(detail: str, headers: Mapping[str, str]) -> TrialError:
    """The server's own words (they name the free key), and when it may work again."""
    wait = _retry_after(headers)
    hint = f" It may work again in about {_when(wait)}." if wait and wait > 10 else ""
    return TrialError(f"{detail}{hint}")


# ── the session ──────────────────────────────────────────────────────────────────────────────────────────


class TrialSession:
    """Runs whitelisted functions through the trial routes, getting and renewing the ticket as needed."""

    def __init__(
        self,
        base_url: str,
        store: TicketStore,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url
        self.store = store
        self._sleep = sleep

    @classmethod
    def from_env(cls, base_url: str, env: Mapping[str, str] | None = None) -> TrialSession:
        """A session for this plugin's data directory.

        Raises:
            TrialError: the trial cannot be used here (CI is set, or this is not Claude Code's plugin runtime).
        """
        env = os.environ if env is None else env
        reason = unavailable_message(env)
        if reason is not None:
            raise TrialError(reason)
        return cls(base_url, TicketStore(Path(env["CLAUDE_PLUGIN_DATA"]), base_url))

    def call(self, function_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run one whitelisted function.

        Raises:
            TrialError: not on the trial list, the trial is busy or spent, pyvar.com is unreachable, or a
                function-level answer (TrialHttpError: 404, 413, 422, 504).
        """
        if function_name not in TRIAL_FUNCTIONS:
            raise TrialError(not_in_trial_message())
        url = f"{self.base_url}/api/v1/trial/run/{function_name}"
        for attempt in (0, 1):
            ticket = self.store.load() or self._bootstrap()
            status, headers, body = _post(url, params, bearer=ticket.ticket)
            if status == 200:
                try:
                    result = json.loads(body)
                except ValueError as exc:
                    raise TrialError("pyvar.com returned a result that is not JSON.") from exc
                return result if isinstance(result, dict) else {"result": result}
            detail = _json(body)
            if status == 401 and attempt == 0 and detail.get("code") == "trial_ticket_invalid":
                self.store.clear()  # an expired or unknown ticket: replace it once
                continue
            if status == 429:
                wait = _retry_after(headers)
                if attempt == 0 and wait is not None and wait <= MAX_RETRY_AFTER_SECONDS:
                    self._sleep(wait)
                    continue
                raise _refused(str(detail.get("detail", "The no-sign-up trial is busy.")), headers)
            raise TrialHttpError(status, body)
        raise TrialError("The no-sign-up trial did not answer; try again shortly.")  # unreachable

    def _bootstrap(self) -> Ticket:
        """Ask pyvar.com for a ticket (a challenge, its solution) and store it. Under the lock."""
        with self.store.lock():
            existing = self.store.load()  # another process may have finished while this one waited
            if existing is not None:
                return existing
            status, headers, body = _post(f"{self.base_url}/api/v1/trial/challenge", {})
            if status != 200:
                raise _refused(
                    str(_json(body).get("detail", f"pyvar.com answered HTTP {status}.")), headers
                )
            challenge = _json(body)
            text, bits = challenge.get("challenge"), challenge.get("bits")
            if (
                not isinstance(text, str)
                or not isinstance(bits, int)
                or not 1 <= bits <= MAX_POW_BITS
            ):
                raise TrialError("pyvar.com sent a sign-up puzzle this plugin will not solve.")
            nonce = solve(text, bits)
            status, headers, body = _post(
                f"{self.base_url}/api/v1/trial/ticket", {"challenge": text, "nonce": nonce}
            )
            issued = _json(body)
            ticket, expires_at = issued.get("ticket"), issued.get("expires_at")
            if status != 200 or not isinstance(ticket, str) or not isinstance(expires_at, int):
                raise _refused(
                    str(issued.get("detail", f"pyvar.com answered HTTP {status}.")), headers
                )
            stored = Ticket(ticket=ticket, expires_at=expires_at, base_url=self.base_url)
            self.store.save(stored)
            return stored

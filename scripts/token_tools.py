"""scripts/token_tools.py: the parts the token mint and revoke commands share.

Reasoning:
- Four commands (mint_internal_token, revoke_internal_token, mint_api_key, revoke_api_key) need the
  same few things: read an environment's signing secret without exposing it, sign an HS256 token,
  keep an append-only ledger of what was issued and revoked, and call the pyvar API. They live here
  once so a fix to secret handling is made in one place.
- Nothing here prints a secret, a token or an API key. Errors never contain them.
- The HTTP helper talks only to the environment's own address, or to loopback for tests; a typo in
  a base URL must not be able to send a token to another host.
- Standard library only, like the commands that use it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ENVS = ("dev", "prod")
DEFAULT_REGION = "eu-west-1"
MIN_SECRET_LENGTH = 32
PUBLIC_DEFAULT_SECRET = "change-me-in-production"  # config.py's fallback; never a real secret
API_BASE_URLS = {"dev": "https://dev.pyvar.com", "prod": "https://www.pyvar.com"}
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
LEDGER_ENV = "PYVAR_TOKEN_LEDGER"
KEY_LEDGER_ENV = "PYVAR_KEY_LEDGER"
USER_AGENT = "pyvar-token-tools/1.0"
ACCOUNT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:@-]{3,128}$")
SESSION_TTL_SECONDS = 600


class ToolError(Exception):
    """A refusal or failure, with the exit code the command should end with.

    Codes: 2 refused by a guard or bad arguments; 3 the secret could not be read or is unusable;
    4 done, but not enforced by the API; 5 the API refused or could not be reached.
    """

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


# ── tokens ──────────────────────────────────────────────────────────────────────


def b64url(raw: bytes) -> str:
    """Base64url without padding, as JWTs use."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Inverse of b64url."""
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_token(
    secret: str,
    *,
    sub: str,
    tier: str,
    ttl_seconds: int,
    now: int | None = None,
    jti: str | None = None,
) -> str:
    """Sign an HS256 JWT with `sub`, `tier`, `iat`, `exp` and, if given, `jti`.

    Args:
        secret: The environment's signing secret.
        sub: Subject claim: a label (or an account id) that identifies the holder.
        tier: Tier claim (internal, enterprise, pro or free).
        ttl_seconds: Lifetime in seconds; always becomes an `exp` claim.
        now: Issue time as a Unix timestamp (defaults to the current time).
        jti: A unique token id. The API ignores it today; a future revocation list would key on it.

    Returns:
        The compact token string.
    """
    issued = int(time.time()) if now is None else now
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims: dict[str, Any] = {"sub": sub, "tier": tier, "iat": issued, "exp": issued + ttl_seconds}
    if jti:
        claims["jti"] = jti
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{b64url(signature)}"


def decode_unverified(token: str) -> dict[str, Any]:
    """Read a token's claims WITHOUT checking its signature.

    Raises:
        ToolError: if the text is not a three-part JWT with a JSON object as payload.
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise ToolError("not a JWT: expected three dot-separated parts")
    try:
        claims = json.loads(b64url_decode(parts[1]))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ToolError("not a JWT: the payload is not valid JSON") from exc
    if not isinstance(claims, dict):
        raise ToolError("not a JWT: the payload is not a JSON object")
    return claims


def fingerprint(token: str) -> str:
    """First 12 hex characters of the token's SHA-256: enough to tell tokens apart in a ledger."""
    return hashlib.sha256(token.encode()).hexdigest()[:12]


# ── the signing secret ──────────────────────────────────────────────────────────


def check_secret(secret: str) -> str:
    """Return the stripped secret, or refuse one that is empty, short or the public default.

    Raises:
        ToolError: if the secret is unusable.
    """
    cleaned = secret.strip()
    if cleaned == PUBLIC_DEFAULT_SECRET:
        raise ToolError("the secret is the public default; refusing to sign with it", 3)
    if len(cleaned) < MIN_SECRET_LENGTH:
        raise ToolError(f"the secret is shorter than {MIN_SECRET_LENGTH} characters; refusing", 3)
    return cleaned


def read_secret_from_aws(env: str, region: str) -> str:
    """Read `pyvar/<env>/jwt-secret` with the AWS CLI; the value never appears in an argument.

    Raises:
        ToolError: if the CLI is missing, the call fails or returns nothing.
    """
    command = [
        "aws",
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        f"pyvar/{env}/jwt-secret",
        "--region",
        region,
        "--query",
        "SecretString",
        "--output",
        "text",
    ]
    try:
        done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, capture_output=True, text=True, timeout=60, check=False
        )
    except FileNotFoundError as exc:
        raise ToolError("the AWS CLI ('aws') is not installed or not on PATH", 3) from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError("the AWS CLI did not answer within 60 s", 3) from exc
    if done.returncode != 0:
        reason = done.stderr.strip().splitlines()[-1:] or ["no message"]
        raise ToolError(f"could not read the secret for {env}: {reason[0][:300]}", 3)
    return done.stdout


def require_env(env: str | None, yes_prod: bool) -> str:
    """The chosen environment, after the two guards every command shares.

    Raises:
        ToolError: if no environment was named, or prod was named without the flag.
    """
    if env is None:
        raise ToolError("--env is required (dev or prod); there is no default")
    if env == "prod" and not yes_prod:
        raise ToolError("acting on prod needs --yes-prod")
    return env


# ── time ────────────────────────────────────────────────────────────────────────


def iso(timestamp: int) -> str:
    """UTC time as ISO 8601 with a trailing Z."""
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> int:
    """Inverse of iso() (also accepts a +00:00 suffix and fractional seconds)."""
    cleaned = text.strip().replace("Z", "+00:00")
    return int(datetime.fromisoformat(cleaned).timestamp())


# ── the ledger ──────────────────────────────────────────────────────────────────


def ledger_path(explicit: str | None, env_var: str, default_name: str) -> Path:
    """Where a ledger lives: the explicit path, else the environment variable, else ~/.pyvar/."""
    chosen = explicit or os.environ.get(env_var)
    return Path(chosen) if chosen else Path.home() / ".pyvar" / default_name


def append_ledger(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON line; create the folder 0700 and the file 0600. Never holds a secret."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_ledger(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Every readable record of a ledger, and how many lines could not be read.

    A missing file is an empty ledger. Damaged lines are counted, not fatal: a ledger is a
    convenience for the operator, never the thing that decides what the API accepts.
    """
    if not path.exists():
        return [], 0
    records: list[dict[str, Any]] = []
    skipped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except ValueError:
            skipped += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            skipped += 1
    return records, skipped


# ── the API ─────────────────────────────────────────────────────────────────────


def base_url_for(env: str, override: str | None = None) -> str:
    """The API address for an environment; an override is accepted only for loopback (tests).

    Raises:
        ToolError: if the override points anywhere but http://127.0.0.1 or http://localhost.
    """
    if override is None:
        return API_BASE_URLS[env]
    parsed = urllib.parse.urlparse(override)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ToolError("--base-url is only accepted for http://127.0.0.1 or http://localhost")
    return override.rstrip("/")


def api_request(
    method: str, url: str, token: str, body: dict[str, Any] | None = None, timeout: int = 30
) -> tuple[int, Any]:
    """Call the API with a bearer token; return (status, parsed JSON or None).

    Raises:
        ToolError: (code 5) if the host cannot be reached. The token is never put in a message.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" and parsed.hostname not in LOOPBACK_HOSTS:
        raise ToolError("refusing to send a token over anything but https", 5)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - checked above
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/json")
    request.add_header("User-Agent", USER_AGENT)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        # The scheme and host were checked above: https, or a loopback host only.
        with urllib.request.urlopen(
            request, timeout=timeout
        ) as response:  # noqa: S310  # nosec B310
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ToolError(f"could not reach {parsed.hostname}: {type(exc).__name__}", 5) from exc
    try:
        return status, (json.loads(raw) if raw else None)
    except ValueError:
        return status, None


def session_token(
    env: str,
    *,
    account_id: str | None,
    token_env_var: str | None,
    region: str = DEFAULT_REGION,
    secret_stdin: bool = False,
) -> str:
    """A session token that may manage one account's API keys.

    Exactly one source: `account_id` (the account's `external_id`, the `sub` of its session
    tokens), for which a 10-minute session token is signed with the environment's secret; or
    `token_env_var`, the name of an environment variable holding a session token the account
    already has (for example the one the portal keeps after sign-in).

    Raises:
        ToolError: if neither or both sources are given, the variable is empty or holds an
            expired or malformed token, the id looks wrong, or the secret is unusable.
    """
    if bool(account_id) == bool(token_env_var):
        raise ToolError("give exactly one of --account-id and --session-token-env")
    if token_env_var:
        token = os.environ.get(token_env_var, "").strip()
        if not token:
            raise ToolError(f"${token_env_var} is empty or not set")
        expires = decode_unverified(token).get("exp")
        if isinstance(expires, int) and expires <= int(time.time()):
            raise ToolError(f"the token in ${token_env_var} has expired; sign in again")
        return token
    assert account_id is not None
    if not ACCOUNT_ID_PATTERN.match(account_id):
        raise ToolError("--account-id must be 3-128 characters of letters, digits and . _ : @ -")
    raw = sys.stdin.read() if secret_stdin else read_secret_from_aws(env, region)
    secret = check_secret(raw)
    return sign_token(secret, sub=account_id, tier="free", ttl_seconds=SESSION_TTL_SECONDS)


def explain_api_failure(status: int, action: str) -> ToolError:
    """A ToolError (code 5) in plain words for an unexpected API status."""
    reasons = {
        401: "the session token was refused: expired, or signed with another environment's secret",
        403: "no verified account has that id (or the session was refused)",
        404: "not found for this account",
        409: "the account's key limit is reached (5 active keys): revoke one first",
        422: "the API rejected the request as invalid",
        429: "rate limited: wait a minute and try again",
        503: "the API's key store is unavailable: try again later",
    }
    return ToolError(f"{action}: HTTP {status}: {reasons.get(status, 'unexpected answer')}", 5)

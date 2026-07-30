"""
storage/redis_client.py — shared Redis connection-string helper

Reasoning:
- Extracted from api/routes/caching.py (originally P7's result-cache module) so
  api/middleware/rate_limit.py (#146) can reuse the exact same fix rather than
  duplicating it: the `limits` library's RedisStorage calls redis.from_url()
  under the hood, same as caching.py's own async client, so it hits the
  identical ssl_cert_reqs bug documented below.
- storage/ is already the home for the other shared backend clients
  (session.py for Postgres, s3.py for S3) — this is the same pattern, not a
  new one.
- Deliberately just the URL string, not a constructed client: caching.py needs
  an async client (redis.asyncio), the rate limiter needs a sync one (plain
  redis, via the `limits` library) — the two callers construct different
  client types from the same corrected URL.
"""

from __future__ import annotations

import os
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from config import get_settings

cfg = get_settings()


def redis_url() -> str:
    """Same connection string Celery uses for CELERY_RESULT_BACKEND — reused, not duplicated.

    CELERY_RESULT_BACKEND's ssl_cert_reqs=CERT_NONE query param is written in
    Kombu's convention (kombu.utils.url.parse_ssl_cert_reqs accepts both
    "CERT_NONE" and "none"). redis.asyncio.from_url() does not coerce
    ssl_cert_reqs at all, and — despite kwargs normally overriding URL values —
    its own docs and code confirm querystring values win over explicit kwargs
    for from_url(), so passing the real enum as a kwarg is silently clobbered
    by this uppercase string. Rewriting the query param itself is the only
    fix: SSLConnection's CERT_REQS dict is lowercase-only ("none"/"optional"/
    "required"), so the uppercase string otherwise reaches it unchanged and
    raises RedisError("Invalid SSL Certificate Requirements Flag: CERT_NONE").

    Applies equally to the plain (sync) `redis` client the `limits` library's
    RedisStorage builds via redis.from_url() — same querystring, same bug.
    """
    raw = os.environ.get("CELERY_RESULT_BACKEND", cfg.redis_url)
    parsed = urlsplit(raw)
    query = parse_qs(parsed.query)
    if "ssl_cert_reqs" in query:
        query["ssl_cert_reqs"] = [query["ssl_cert_reqs"][0].lower().removeprefix("cert_")]
        parsed = parsed._replace(query=urlencode(query, doseq=True))
    return urlunsplit(parsed)

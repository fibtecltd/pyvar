"""
storage/session.py — Async SQLAlchemy engine and session factory

Reasoning:
- The application talks to Aurora SV2 over asyncpg (cfg.postgres_dsn is a
  postgresql+asyncpg:// URL). This module is the single place that owns the
  async engine and the sessionmaker, so callers never construct their own.
- Created LAZILY (first use), not at import time: importing this module must
  never require a reachable database — that keeps unit tests and `alembic`
  offline runs from paying a connection cost, and avoids import-time failures
  when DB_* env vars are absent (e.g. tooling contexts).
- create_async_engine() itself opens no connections; the pool connects on first
  query. pool_pre_ping=True quietly recycles connections dropped by Aurora's
  scale-to-zero / idle timeouts rather than surfacing a stale-connection error.
- Pool is intentionally small: today the only writer is the fire-and-forget
  usage-tracking middleware, whose inserts run off the request hot path.

NOTE: this is the first runtime DB-session layer in the codebase — until now the
ORM models (VaRJob, users) existed only for migrations and were never written to
by application code. Keep DB usage funnelled through get_sessionmaker().
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine
    if _engine is None:
        cfg = get_settings()
        _engine = create_async_engine(
            cfg.postgres_dsn,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=1800,  # recycle connections every 30 min (Aurora idle safety)
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async sessionmaker, creating it on first use."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker

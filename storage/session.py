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
- Pool is intentionally small: the writers on this async engine are the
  fire-and-forget usage-tracking middleware and the var_jobs submission INSERT
  in api/routes/var.py (issue #118), both of which run in the FastAPI event
  loop's request path (or just after it).

- The Celery worker (tasks/var_task.py) is a separate, synchronous process
  (prefork pool) — it cannot share the async engine above. asyncpg connections
  are bound to the event loop that opened them, so driving the async
  sessionmaker from sync Celery code via asyncio.run() per task would open a
  fresh event loop on every call and silently defeat connection pooling (and
  risk cross-loop errors on reused connections). get_sync_sessionmaker() gives
  the worker its own small synchronous engine over psycopg2 instead — the same
  sync driver Alembic already uses for migrations (CLAUDE.md §3.3), just now
  also used at runtime for the var_jobs completion UPDATE.

NOTE: this is the first runtime DB-session layer in the codebase — until now the
ORM models (VaRJob, users) existed only for migrations and were never written to
by application code. FastAPI code should use get_sessionmaker(); the Celery
worker should use get_sync_sessionmaker(). Keep DB usage funnelled through one
of these two factories rather than constructing engines ad hoc.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

_sync_engine: Engine | None = None
_sync_sessionmaker: sessionmaker[Session] | None = None


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


def _sync_postgres_dsn() -> str:
    """cfg.postgres_dsn with the driver swapped from asyncpg to psycopg2.

    Same host/credentials, different driver — the same split Alembic already
    relies on (async at runtime, sync psycopg2 for offline migration scripts).
    """
    return get_settings().postgres_dsn.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def get_sync_engine() -> Engine:
    """Return the process-wide sync engine, creating it on first use.

    For the Celery worker only — see the module docstring for why the worker
    cannot share the async engine above.
    """
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            _sync_postgres_dsn(),
            pool_size=2,
            max_overflow=2,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _sync_engine


def get_sync_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide sync sessionmaker, creating it on first use."""
    global _sync_sessionmaker
    if _sync_sessionmaker is None:
        _sync_sessionmaker = sessionmaker(get_sync_engine(), expire_on_commit=False)
    return _sync_sessionmaker

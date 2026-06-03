"""
main.py — FastAPI application factory and entry point

Reasoning:
- create_app() factory pattern (rather than a module-level app instance)
  makes the app testable: tests can call create_app() with overridden
  settings without touching global state.
- OrjsonResponse is set as the default_response_class so all routes
  automatically use orjson serialisation without per-route decoration.
- The /health endpoint is unauthenticated — used by load balancers and
  Kubernetes liveness probes.
- Lifespan context manager (replacing deprecated @app.on_event) handles
  startup/shutdown: DB connection pool warmup, Numba JIT warmup, etc.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.responses import OrjsonResponse
from api.routes.var import router as var_router
from config import get_settings
from observability.setup import setup_observability

cfg = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""

    # Warm up the Numba JIT compiler with a tiny dummy run.
    # First call compiles; subsequent calls hit the cache.
    # Without warmup, the first real request pays the ~2s compilation cost.
    import numpy as np

    from engine.montecarlo import run_monte_carlo_var

    dummy_returns = np.random.randn(30) * 0.01
    run_monte_carlo_var(dummy_returns, portfolio_value=1.0, n_simulations=1_000, seed=0)

    yield

    # Shutdown: close DB connections, flush Sentry, etc.


def create_app() -> FastAPI:
    app = FastAPI(
        title="pyvar.com",
        version="0.1.0",
        description="Open-source financial & risk computation platform. Monte Carlo VaR and beyond.",
        docs_url="/docs",
        redoc_url="/redoc",
        default_response_class=OrjsonResponse,
        lifespan=lifespan,
    )

    # ── Observability (Prometheus + Sentry + structlog) ─────────────────────
    setup_observability(app)

    # ── CORS ────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if cfg.debug else ["https://pyvar.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──────────────────────────────────────────────────────────────
    app.include_router(var_router, prefix=cfg.api_v1_prefix)

    # ── Health check ────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "app": cfg.app_name, "env": cfg.app_env}

    return app


app = create_app()

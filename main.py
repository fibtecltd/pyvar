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
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match, Mount
from starlette.types import Scope

from api.middleware.rate_limit import enforce_compute_rate_limit, enforce_public_rate_limit
from api.middleware.usage import usage_tracking_middleware
from api.responses import OrjsonResponse
from api.routes.alm import router as alm_router
from api.routes.auth import router as auth_router
from api.routes.credit_risk import router as credit_risk_router
from api.routes.derivatives import router as derivatives_router
from api.routes.internal import router as internal_router
from api.routes.liquidity import router as liquidity_router
from api.routes.market_risk import router as market_risk_router
from api.routes.operational import router as operational_router
from api.routes.portfolio import router as portfolio_router
from api.routes.public_data import router as public_data_router
from api.routes.regulatory import router as regulatory_router
from api.routes.var import router as var_router
from config import get_settings
from observability.setup import setup_observability

cfg = get_settings()

PORTAL_DIR = Path(__file__).resolve().parent / "portal"

# Paths owned by real app routes, never the static portal — kept in sync with
# every prefix used in the app.include_router(...) calls below, plus the
# unprefixed system endpoints (/health, /docs, /redoc, /openapi.json,
# /metrics) FastAPI/Instrumentator register directly.
_RESERVED_PATH_PREFIXES = (
    cfg.api_v1_prefix,
    "/public",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
)


class _PortalStaticMount(Mount):
    """Starlette's plain Mount matches ANY HTTP method for its path prefix —
    it has no concept of "wrong method", only "wrong path". Since this mount
    is registered at "/" (matching every path) and LAST (after every real
    API route), Starlette's routing always prefers its Match.FULL over an
    earlier route's Match.PARTIAL (right path, wrong method) — so a
    wrong-method request to a real route (e.g. GET on the POST-only
    /api/v1/var/compute) silently falls through to this mount's static file
    lookup instead of that route's own auth/405 logic, and returns a
    misleading "file not found" 404 (or, for non-GET/HEAD methods,
    StaticFiles' own blanket 405 — also not the real route's response).

    Returning Match.NONE for reserved prefixes here lets Starlette correctly
    fall back to whatever the real API routes' own matching produces
    instead: their own 405 for a wrong method, or its own default 404 if
    truly no route matches at all.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and scope["path"].startswith(_RESERVED_PATH_PREFIXES):
            return Match.NONE, {}
        return super().matches(scope)


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

    # ── Usage telemetry ──────────────────────────────────────────────────────
    # Records one api_usage row per /api/v1/* request, off the hot path.
    app.middleware("http")(usage_tracking_middleware)

    # ── CORS ────────────────────────────────────────────────────────────────
    # task #42: allow_origins used to pick between ["*"] and
    # ["https://pyvar.com"] based on cfg.debug, which nothing ever sets
    # False in any real deployment -- both dev and prod were confirmed live
    # to reflect an attacker-controlled Origin header back with
    # access-control-allow-credentials: true. cors_allowed_origins
    # (config.py) is the explicit per-environment replacement. No
    # allow_credentials: auth here is Bearer-JWT-in-header only (see
    # api/middleware/auth.py) -- nothing in this app sets a cookie, so
    # credentialed CORS serves no purpose and is exactly what made the
    # wildcard-reflection above actually exploitable.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──────────────────────────────────────────────────────────────
    app.include_router(auth_router, prefix=cfg.api_v1_prefix)

    # Service-only ("internal" tier) endpoints — never called by a human/
    # browser. No enforce_compute_rate_limit dependency: not a compute
    # endpoint, and "internal" tier is already unconditionally exempt from
    # rate limiting regardless (api/middleware/rate_limit.py::_EXEMPT_TIERS).
    app.include_router(internal_router, prefix=cfg.api_v1_prefix)

    # Rate limiting (#146): var_router applies enforce_compute_rate_limit
    # itself, at the POST /compute route only (api/routes/var.py) — var_router
    # also contains GET /result/{task_id}, a cheap result poll that must never
    # share the same daily compute-dispatch quota. The 8 domain routers below
    # are POST-only (one endpoint per engine function, no polling pattern), so
    # a single router-level dependency correctly covers all of them without
    # decorating any of their 386 individual endpoint functions — see
    # api/middleware/rate_limit.py's module docstring for why a per-endpoint
    # decorator couldn't give the intended account-wide daily quota anyway.
    app.include_router(var_router, prefix=cfg.api_v1_prefix)
    compute_rate_limit = [Depends(enforce_compute_rate_limit)]
    for domain_router in (
        market_risk_router,
        credit_risk_router,
        liquidity_router,
        operational_router,
        portfolio_router,
        regulatory_router,
        derivatives_router,
        alm_router,
    ):
        app.include_router(domain_router, prefix=cfg.api_v1_prefix, dependencies=compute_rate_limit)

    # No prefix — matches portal/pyvar.js's `${API_BASE}/public/...` fetches.
    # Unauthenticated, so a separate per-IP (not per-user) limit.
    app.include_router(public_data_router, dependencies=[Depends(enforce_public_rate_limit)])

    # ── Health check ────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"], include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "app": cfg.app_name, "env": cfg.app_env}

    # ── Portal (static site) ─────────────────────────────────────────────────
    # Mounted last and at "/". html=True serves portal/index.html at "/" and
    # portal's other .html files (domain-*.html, dashboard.html) at their own
    # filename. Uses _PortalStaticMount, not app.mount()/plain Mount — see its
    # docstring: a plain Mount at "/" would silently swallow wrong-method
    # requests to real API/system routes registered above instead of letting
    # their own 405/404 logic run.
    app.router.routes.append(
        _PortalStaticMount("/", app=StaticFiles(directory=PORTAL_DIR, html=True), name="portal")
    )

    return app


app = create_app()

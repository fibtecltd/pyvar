"""
observability/setup.py — Prometheus + Sentry + structlog initialisation

Reasoning:
- Observability is wired at startup in main.py via setup_observability(app).
- Prometheus: prometheus-fastapi-instrumentator auto-instruments all routes
  with request latency histograms, request counts, and error rates.
  Custom histogram tracks VaR computation duration separately from HTTP latency.
- Sentry: captures unhandled exceptions from both FastAPI handlers and
  Celery workers with full stack traces and request context.
- structlog: structured JSON logging gives searchable, filterable logs
  in production log aggregators (Datadog, Loki, CloudWatch).
  Replaces stdlib logging with a processor chain that adds timestamp,
  log level, and any extra= fields as top-level JSON keys.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import structlog
from prometheus_client import Histogram
from prometheus_fastapi_instrumentator import Instrumentator

from config import get_settings

cfg = get_settings()

# ── Custom Prometheus metrics ─────────────────────────────────────────────────

VAR_COMPUTATION_DURATION = Histogram(
    name="pyvar_computation_duration_seconds",
    documentation="Duration of Monte Carlo VaR computation in the Celery worker",
    labelnames=["confidence_level", "horizon_days"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

VAR_SIMULATION_COUNT = Histogram(
    name="pyvar_simulation_count",
    documentation="Number of Monte Carlo paths per computation",
    buckets=[1_000, 10_000, 100_000, 250_000, 500_000, 1_000_000],
)


@contextmanager
def track_computation(
    confidence_level: float, horizon_days: int, n_simulations: int
) -> Generator[None, None, None]:
    """
    Context manager for Celery tasks to record computation timing and path count.
    Usage:
        with track_computation(0.99, 1, 100_000):
            result = run_monte_carlo_var(...)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        VAR_COMPUTATION_DURATION.labels(
            confidence_level=str(confidence_level),
            horizon_days=str(horizon_days),
        ).observe(duration)
        VAR_SIMULATION_COUNT.observe(n_simulations)


# ── Sentry ────────────────────────────────────────────────────────────────────


def setup_sentry() -> None:
    """Initialise Sentry SDK if DSN is configured. No-op in development."""
    if not cfg.sentry_dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=cfg.sentry_dsn,
        environment=cfg.app_env,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            CeleryIntegration(monitor_beat_tasks=True),
            SqlalchemyIntegration(),
        ],
        traces_sample_rate=0.1 if cfg.app_env == "production" else 1.0,
        send_default_pii=False,
    )


# ── structlog ─────────────────────────────────────────────────────────────────


def setup_logging() -> None:
    """
    Configure structlog for structured JSON output in production,
    pretty console output in development.
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if cfg.app_env == "development":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(cfg.log_level)),
        logger_factory=structlog.PrintLoggerFactory(),
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(cfg.log_level)


# ── FastAPI instrumentation ───────────────────────────────────────────────────


def _patch_pfi_routing() -> None:
    """Patch prometheus_fastapi_instrumentator to handle _IncludedRouter objects.

    FastAPI adds _IncludedRouter objects to app.routes for mounted sub-routers.
    These lack a .path attribute, so the PFI routing module crashes with
    AttributeError when it tries to resolve route names for metrics labels.
    """
    try:
        import prometheus_fastapi_instrumentator.routing as _pfi_routing
        from starlette.routing import Match

        def _safe_get_route_name(
            scope: dict,  # type: ignore[type-arg]
            routes: list,  # type: ignore[type-arg]
            route_name: str | None = None,
        ) -> str | None:
            for route in routes:
                match, child_scope = route.matches(scope)
                if match == Match.FULL:
                    path = getattr(route, "path", None)
                    if path is not None:
                        return str(path)
                    sub_routes = getattr(route, "routes", [])
                    if sub_routes:
                        result = _safe_get_route_name(child_scope, sub_routes, route_name)
                        if result is not None:
                            return result
                elif match == Match.PARTIAL:
                    sub_routes = getattr(route, "routes", [])
                    if sub_routes:
                        result = _safe_get_route_name(child_scope, sub_routes, route_name)
                        if result is not None:
                            return result
            return route_name

        _pfi_routing._get_route_name = _safe_get_route_name
    except Exception:  # noqa: BLE001 # nosec B110
        pass


def setup_observability(app: Any) -> None:
    """
    Wire up all observability components to the FastAPI app.
    Called once in main.py on startup.
    """
    setup_logging()
    setup_sentry()
    _patch_pfi_routing()

    Instrumentator(
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics")

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


def _resolve_sentry_dsn() -> str:
    """Resolve the Sentry DSN to actually use.

    Workers already get SENTRY_DSN as a pre-populated env var --
    scripts/fetch-config.sh fetches it into secrets.env before the process
    starts, so cfg.sentry_dsn is already set and this returns immediately.

    The API tier deliberately does NOT get it via ECS's native `secrets={}`
    injection (see api_stack.py's comment above sentry_secret) -- that
    mechanism has no "optional" mode, so a secret that becomes unreadable
    would fail every new Fargate task launch outright and could block prod
    deploys entirely over an observability nice-to-have. Fetched here
    instead, at application startup, where a failure degrades gracefully.

    Only attempts the fetch when actually running in a real ECS task
    (cfg.ecs_container_metadata_uri_v4 set -- AWS injects this
    automatically). Local dev and CI never have this secret and must never
    attempt a real AWS call: CI's test job runs with APP_ENV=test, not
    "development", so gating on the app_env string instead of real ECS
    presence would have let a real Secrets Manager call slip into test runs.
    """
    if cfg.sentry_dsn:
        return cfg.sentry_dsn
    if not cfg.ecs_container_metadata_uri_v4:
        return ""
    try:
        import boto3

        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=f"pyvar/{cfg.app_env}/sentry-dsn")
        return str(response.get("SecretString") or "")
    except Exception:
        return ""


def setup_sentry() -> None:
    """Initialise Sentry SDK if a valid DSN is configured. No-op in development,
    and no-op (never a crash) on a malformed DSN -- Sentry is optional
    observability and must never become a startup dependency for the API or
    worker fleet.
    """
    dsn = _resolve_sentry_dsn()
    if not dsn or dsn == "None":
        # The literal string "None" is a known `aws secretsmanager
        # get-secret-value --query SecretString --output text` quirk when a
        # secret was created as SecretBinary instead of SecretString -- an
        # easy mistake for a secret created outside CDK. Treat it the same as
        # "not configured" rather than handing an invalid DSN to the SDK.
        return

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=cfg.app_env,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                CeleryIntegration(monitor_beat_tasks=True),
                SqlalchemyIntegration(),
            ],
            # task #45 -- was compared against "production" (long form),
            # but api_stack.py injects APP_ENV=cfg.env_name, which is the
            # SHORT form CDK actually uses everywhere ("dev"/"staging"/
            # "prod" -- see cfg.app_env's own docstring in config.py, added
            # for the identical mismatch in cors_allowed_origins/
            # public_base_url, tasks #42/#43). Comparing against the long
            # form meant this was always False in every real deployment, so
            # prod silently sampled 100% of traces instead of the intended
            # 10% -- a cost/volume issue, not a correctness one, but the
            # exact bug class this whole task chain has been hunting.
            traces_sample_rate=0.1 if cfg.app_env == "prod" else 1.0,
            send_default_pii=False,
        )
    except Exception:
        # setup_logging() always runs before setup_sentry() (both call sites
        # -- main.py's setup_observability() and worker.py's module-level
        # calls -- order it that way), so stdlib logging is already
        # configured here.
        # No part of `dsn` is logged, even redacted -- CodeQL's
        # py/clear-text-logging-sensitive-data taint tracking flags any
        # value *derived* from a secret-bearing source reaching a log call,
        # not just the raw secret itself, so a masked-but-still-DSN-derived
        # string (e.g. scheme+host+path) still trips it. `exc_info=True`
        # already gives the real diagnostic detail (including, from the
        # SDK's own exception message, what was wrong with the DSN) without
        # this function needing to echo any of it back out itself.
        logging.getLogger(__name__).warning(
            "Sentry initialisation failed -- continuing without it",
            exc_info=True,
        )


# ── structlog ─────────────────────────────────────────────────────────────────


#  Real deployed app_env values -- the SHORT forms CDK actually injects
# (api_stack.py sets APP_ENV=cfg.env_name), not the long forms
# "development"/"production" cfg.app_env's own default/docstring implies.
# Shared here because setup_logging() below needs "is this any real AWS
# deployment" as a set (dev/staging/prod all log to CloudWatch and all
# want JSON), unlike setup_sentry()'s traces_sample_rate gate (task #45),
# which only cares about "prod" specifically.
_DEPLOYED_APP_ENVS = ("dev", "staging", "prod")


def setup_logging() -> None:
    """
    Configure structlog for structured JSON output in any real AWS
    deployment (dev/staging/prod -- all ship logs to CloudWatch, which
    JSON keeps searchable/filterable), pretty console output otherwise
    (local dev, CI).
    """
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        # Without this, logger.exception()/exc_info=True renders as a bare
        # repr of the exception + a non-serialisable traceback object (e.g.
        # "server:RedisError", "<traceback object at 0x...>") instead of the
        # actual message and formatted stack — the real cause is invisible
        # in CloudWatch no matter how descriptive the raised exception is.
        structlog.processors.format_exc_info,
    ]

    # task #46 -- was `if cfg.app_env == "development"`, comparing against
    # the long form. Deployed dev's real app_env ("dev") never matched, so
    # deployed dev got JSONRenderer only by accident of that mismatch, not
    # by deliberate design -- correct in outcome (see docstring above), but
    # a coincidence away from silently flipping to ConsoleRenderer (ANSI
    # escape codes, unreadable in CloudWatch's log viewer) if config.py's
    # app_env default or docstring were ever "corrected" to match its own
    # stated long-form convention without knowing about this coupling.
    # Explicit now: JSON for every real deployment, console for everything
    # else -- including CI's "test", a deliberate behaviour improvement
    # (previously "test" also fell to JSONRenderer by the same accident;
    # pretty console output is strictly more readable for a human
    # inspecting a failed CI run's logs, and nothing asserts on the
    # previous renderer choice -- grepped tests/test_observability.py).
    if cfg.app_env in _DEPLOYED_APP_ENVS:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(cfg.log_level)),
        # stdlib.LoggerFactory(), not PrintLoggerFactory(): add_logger_name
        # above (a stdlib-logging processor) reads logger.name, which a
        # PrintLogger doesn't have — every structlog call anywhere in the
        # app crashed with AttributeError once this ran (#149 uncovered it:
        # nothing had exercised a real, unmocked structlog call before).
        # LoggerFactory() is also what makes wrap_for_formatter meaningful at
        # all — it hands off to the ProcessorFormatter + handler wired below,
        # which PrintLoggerFactory bypasses entirely.
        logger_factory=structlog.stdlib.LoggerFactory(),
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
